"""Capability catalog contracts, projection, resolution, and API boundaries."""

import json

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.agents.specialists import REGISTRY
from app.models.runtime import RuntimePolicyResult
from app.routes import capabilities as capabilities_route
from app.runtime.capabilities import (
    CapabilityBindingError,
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityEntry,
    CapabilityImplementationReference,
    CapabilityResolver,
    CapabilityRuntimeStatus,
    bind_execution_plan,
)
from app.runtime.capabilities.definitions import (
    SPECIALIST_CAPABILITY_DEFINITIONS,
    TOOL_CAPABILITY_DEFINITIONS,
)
from app.runtime.execution import (
    AgentContext,
    ExecutionPlan,
    PlanStep,
    ToolObservation,
    ToolRegistry,
    ToolSpec,
    build_execution_plan,
)
from app.runtime.orchestration.finance_runtime import FinanceRuntime


def _descriptor(capability_id: str, *, kind: str = "tool") -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        kind=kind,
        title="Test capability",
        description="Bounded test capability.",
        owner="tests",
        risk_level="low",
        execution_mode="read_only",
        input_contract="TestInput",
        output_contract="TestOutput",
    )


def _entry(
    capability_id: str,
    *,
    enabled: bool = True,
    available: bool = True,
    kind: str = "tool",
    registry_name: str = "test_tool",
) -> CapabilityEntry:
    return CapabilityEntry(
        descriptor=_descriptor(capability_id, kind=kind),
        status=CapabilityRuntimeStatus(
            enabled=enabled,
            available=available,
            reason="test status" if not enabled or not available else "",
        ),
        implementation=CapabilityImplementationReference(
            capability_id=capability_id,
            kind=kind,
            registry_name=registry_name,
        ),
    )


def test_descriptor_is_strict_and_frozen():
    descriptor = _descriptor("test.read_only")

    with pytest.raises(ValidationError):
        descriptor.title = "Changed"
    with pytest.raises(ValidationError):
        CapabilityDescriptor.model_validate(
            descriptor.model_dump() | {"executor": "not allowed"}
        )


def test_registry_projection_is_sorted_and_does_not_execute():
    calls = {"tool": 0, "agent": 0}

    def tool_executor(_payload):
        calls["tool"] += 1
        return ToolObservation(
            tool_name="get_finance_context", success=True, agent="cfo"
        )

    def specialist_executor(_input):
        calls["agent"] += 1
        raise AssertionError("Catalog listing must not execute specialists")

    catalog = CapabilityCatalog.from_registries(
        ToolRegistry(
            [
                ToolSpec(
                    name="get_finance_context",
                    description="Build finance context.",
                    executor=tool_executor,
                )
            ]
        ),
        {"expense_analyst": specialist_executor},
    )

    ids = [item.descriptor.capability_id for item in catalog.list()]
    assert ids == sorted(ids)
    assert ids == ["finance.context", "finance.expense_review"]
    assert calls == {"tool": 0, "agent": 0}


def test_registry_order_does_not_change_catalog_order():
    def tool_executor(_payload):
        raise AssertionError("Catalog listing must not execute tools")

    def specialist_executor(_input):
        raise AssertionError("Catalog listing must not execute specialists")

    tool_specs = [
        ToolSpec(
            name="get_finance_context",
            description="Build finance context.",
            executor=tool_executor,
        ),
        ToolSpec(
            name="query_transactions",
            description="Query transactions.",
            executor=tool_executor,
        ),
    ]
    specialist_names = ["expense_analyst", "budget_coach"]

    first = CapabilityCatalog.from_registries(
        ToolRegistry(tool_specs),
        {name: specialist_executor for name in specialist_names},
    )
    second = CapabilityCatalog.from_registries(
        ToolRegistry(list(reversed(tool_specs))),
        {name: specialist_executor for name in reversed(specialist_names)},
    )

    first_ids = [item.descriptor.capability_id for item in first.list()]
    second_ids = [item.descriptor.capability_id for item in second.list()]
    assert first_ids == second_ids == sorted(first_ids)


def test_current_registry_definitions_have_exact_coverage():
    runtime_tool_names = {
        spec.name for spec in FinanceRuntime().tool_registry.available()
    }

    assert runtime_tool_names <= set(TOOL_CAPABILITY_DEFINITIONS)
    assert set(TOOL_CAPABILITY_DEFINITIONS) - runtime_tool_names == {
        "get_vibe_market_data"
    }
    assert set(SPECIALIST_CAPABILITY_DEFINITIONS) == set(REGISTRY)


def test_duplicate_capability_ids_are_rejected():
    entry = _entry("test.duplicate")

    with pytest.raises(ValueError, match="Duplicate capability id"):
        CapabilityCatalog([entry, entry])


@pytest.mark.parametrize(
    ("capability_id", "entry", "grants", "expected_status"),
    [
        ("test.missing", None, set(), "unknown"),
        (
            "test.disabled",
            _entry("test.disabled", enabled=False),
            {"test.disabled"},
            "disabled",
        ),
        (
            "test.unavailable",
            _entry("test.unavailable", available=False),
            {"test.unavailable"},
            "unavailable",
        ),
        ("test.denied", _entry("test.denied"), set(), "disallowed"),
        ("test.allowed", _entry("test.allowed"), {"test.allowed"}, "resolved"),
    ],
)
def test_resolver_returns_typed_results(capability_id, entry, grants, expected_status):
    catalog = CapabilityCatalog([entry] if entry is not None else [])

    result = CapabilityResolver(catalog).resolve(
        capability_id,
        granted_capabilities=grants,
    )

    assert result.status == expected_status
    assert (result.reference is not None) is (expected_status == "resolved")


def test_plan_binding_resolves_semantic_ids_to_existing_registry_names():
    plan = ExecutionPlan(
        steps=[
            PlanStep(step_type="tool", capability_id="test.query"),
            PlanStep(step_type="handoff", capability_id="test.review"),
            PlanStep(step_type="compose"),
        ],
    )
    catalog = CapabilityCatalog(
        [
            _entry("test.query", registry_name="query_transactions"),
            _entry(
                "test.review",
                kind="agent",
                registry_name="expense_analyst",
            ),
        ]
    )

    bound = bind_execution_plan(
        plan,
        CapabilityResolver(catalog),
        granted_capabilities={"test.query", "test.review"},
    )

    assert bound.tool_names == ["query_transactions"]
    assert bound.handoff_names == ["expense_analyst"]
    assert bound.selected_agents == ("cfo", "expense_analyst")


def test_planner_emits_semantic_capability_ids_only():
    plan = build_execution_plan(
        AgentContext(
            request_id="req-plan",
            user_id="demo",
            entrypoint="chat",
            message="Analyze my spending",
            transactions=[{"amount": -20, "category": "shopping"}],
        ),
        RuntimePolicyResult(
            complexity="moderate",
            risk_level="medium",
            required_specialists=["expense_analyst"],
            audit_required=True,
            max_tool_calls=6,
        ),
    )

    assert "finance.expense_snapshot" in plan.tool_capability_ids
    assert plan.handoff_capability_ids == [
        "finance.expense_review",
        "finance.audit_review",
    ]
    assert all("." in capability_id for capability_id in plan.capability_ids)
    assert all(
        implementation_name not in plan.capability_ids
        for implementation_name in (
            "get_expense_snapshot",
            "expense_analyst",
            "auditor",
        )
    )
    assert plan.steps[-1].step_type == "compose"
    assert plan.steps[-1].capability_id is None


@pytest.mark.parametrize(
    ("entry", "grants", "expected_status"),
    [
        (None, {"test.blocked"}, "unknown"),
        (_entry("test.blocked", enabled=False), {"test.blocked"}, "disabled"),
        (
            _entry("test.blocked", available=False),
            {"test.blocked"},
            "unavailable",
        ),
        (_entry("test.blocked"), set(), "disallowed"),
        (
            _entry("test.blocked", kind="agent", registry_name="expense_analyst"),
            {"test.blocked"},
            "disallowed",
        ),
    ],
)
def test_plan_binding_fails_closed(entry, grants, expected_status):
    plan = ExecutionPlan(
        steps=[PlanStep(step_type="tool", capability_id="test.blocked")],
    )
    catalog = CapabilityCatalog([entry] if entry is not None else [])

    with pytest.raises(CapabilityBindingError) as caught:
        bind_execution_plan(
            plan,
            CapabilityResolver(catalog),
            granted_capabilities=grants,
        )

    assert caught.value.status == expected_status


def test_developer_route_is_read_only_and_secret_free(monkeypatch):
    catalog = CapabilityCatalog([_entry("test.visible")])
    monkeypatch.setattr(
        capabilities_route,
        "get_capability_catalog",
        lambda: catalog,
    )

    payload = capabilities_route.list_capabilities().model_dump(mode="json")
    encoded = json.dumps(payload).lower()
    api_routes = [
        route
        for route in capabilities_route.router.routes
        if isinstance(route, APIRoute)
    ]

    assert [route.methods for route in api_routes] == [{"GET"}]
    assert set(payload) == {"capabilities"}
    assert set(payload["capabilities"][0]) == {"descriptor", "status"}
    for forbidden in (
        "credential",
        "api_key",
        "command",
        "endpoint",
        "executor",
        "prompt",
    ):
        assert forbidden not in encoded
