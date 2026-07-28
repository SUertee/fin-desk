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
    TEAM_CAPABILITY_DEFINITIONS,
    TOOL_CAPABILITY_DEFINITIONS,
)
from app.runtime.execution import (
    ExecutionPlan,
    PlanStep,
    ToolObservation,
    ToolRegistry,
    ToolSpec,
    build_execution_plan,
)
from app.runtime.orchestration.factory import build_finance_runtime
from app.runtime.policy.runtime_policy import evaluate_runtime_policy


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
    runtime = build_finance_runtime()
    runtime_tool_names = {spec.name for spec in runtime.tool_registry.available()}

    assert runtime_tool_names <= set(TOOL_CAPABILITY_DEFINITIONS)
    assert set(TOOL_CAPABILITY_DEFINITIONS) - runtime_tool_names == {
        "get_vibe_market_data"
    }
    assert set(SPECIALIST_CAPABILITY_DEFINITIONS) == set(REGISTRY)
    assert {
        item.descriptor.capability_id
        for item in runtime.capability_catalog.list()
        if item.descriptor.kind == "team"
    } == set(TEAM_CAPABILITY_DEFINITIONS)


def test_duplicate_capability_ids_are_rejected():
    entry = _entry("test.duplicate")

    with pytest.raises(ValueError, match="Duplicate capability id"):
        CapabilityCatalog([entry, entry])


def test_duplicate_tool_names_are_rejected():
    spec = ToolSpec(
        name="duplicate_tool",
        description="Duplicate registration test.",
        executor=lambda _payload: None,
    )

    with pytest.raises(ValueError, match="Duplicate tool name"):
        ToolRegistry([spec, spec])


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
            PlanStep(
                step_type="handoff",
                capability_id="test.review",
                depends_on=("test.query",),
                parallel_safe=True,
            ),
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
    assert bound.handoff_steps[0].depends_on == ("test.query",)
    assert bound.handoff_steps[0].parallel_safe is True


def test_planner_emits_semantic_capability_ids_only():
    runtime = build_finance_runtime()
    plan = build_execution_plan(
        ["finance.expense_review"],
        RuntimePolicyResult(
            complexity="moderate",
            risk_level="medium",
            required_specialists=["expense_analyst"],
            audit_required=True,
            max_tool_calls=6,
        ),
        runtime.capability_catalog,
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


def test_planner_expands_team_into_existing_specialist_plan():
    runtime = build_finance_runtime()
    policy = evaluate_runtime_policy(
        ["team.monthly_finance_review"],
        runtime.capability_catalog,
    )

    plan = build_execution_plan(
        ["team.monthly_finance_review"],
        policy,
        runtime.capability_catalog,
    )

    assert plan.handoff_capability_ids == [
        "finance.expense_review",
        "finance.budget_coaching",
        "finance.audit_review",
    ]
    assert "team.monthly_finance_review" not in plan.capability_ids
    assert "finance.expense_snapshot" in plan.tool_capability_ids
    assert "finance.budget_snapshot" in plan.tool_capability_ids
    expense, budget, audit = [
        step for step in plan.steps if step.step_type == "handoff"
    ]
    assert expense.depends_on == (
        "finance.context",
        "finance.expense_snapshot",
        "finance.anomaly_summary",
        "finance.import_quality",
    )
    assert budget.depends_on == (
        "finance.context",
        "finance.expense_snapshot",
        "finance.budget_snapshot",
        "finance.cashflow_summary",
        "finance.import_quality",
    )
    assert expense.parallel_safe is True
    assert budget.parallel_safe is True
    assert audit.depends_on == (
        "finance.expense_review",
        "finance.budget_coaching",
    )
    assert audit.parallel_safe is False


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


def test_known_disabled_tool_is_projected_without_implementation():
    status = CapabilityRuntimeStatus(
        enabled=False,
        available=False,
        reason="Disabled by configuration",
    )
    catalog = CapabilityCatalog.from_registries(
        ToolRegistry([]),
        {},
        optional_tool_statuses={"get_vibe_market_data": status},
    )

    item = catalog.list()[0]
    resolution = CapabilityResolver(catalog).resolve(
        item.descriptor.capability_id,
        granted_capabilities={item.descriptor.capability_id},
    )

    assert item.descriptor.source == "mcp"
    assert item.status.enabled is False
    assert catalog.get(item.descriptor.capability_id).implementation is None
    assert resolution.status == "disabled"


@pytest.mark.asyncio
async def test_developer_route_is_read_only_and_secret_free(monkeypatch):
    class FakeHealth:
        async def vibe_market_data_status(self):
            return CapabilityRuntimeStatus(enabled=False, available=False)

    monkeypatch.setattr(
        capabilities_route,
        "get_capability_runtime",
        lambda: build_finance_runtime(),
    )
    monkeypatch.setattr(
        capabilities_route,
        "get_capability_health_service",
        lambda: FakeHealth(),
    )

    payload = (await capabilities_route.list_capabilities()).model_dump(mode="json")
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
