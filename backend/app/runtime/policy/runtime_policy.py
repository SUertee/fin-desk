"""Deterministic policy derived from requested capability descriptors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.team_expansion import expand_team_capabilities

if TYPE_CHECKING:
    from app.runtime.capabilities.catalog import CapabilityCatalog


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def evaluate_runtime_policy(
    capability_ids: tuple[str, ...] | list[str],
    catalog: "CapabilityCatalog",
) -> RuntimePolicyResult:
    """Convert untrusted capability requests into bounded runtime policy."""

    expanded_capability_ids = expand_team_capabilities(capability_ids, catalog)
    descriptors = []
    for capability_id in expanded_capability_ids:
        entry = catalog.get(capability_id)
        assert entry is not None
        descriptors.append(entry.descriptor)

    risk_level = max(
        (item.risk_level for item in descriptors),
        key=lambda value: _RISK_ORDER[value],
        default="low",
    )
    specialists = [
        item.owner
        for item in descriptors
        if item.kind == "agent" and item.owner != "auditor"
    ]
    specialists = list(dict.fromkeys(specialists))
    audit_required = bool(specialists) or risk_level != "low"
    requested_count = len(descriptors)
    if risk_level == "high" or requested_count >= 4:
        complexity = "complex"
        max_tool_calls = 12
    elif audit_required or requested_count >= 2:
        complexity = "moderate"
        max_tool_calls = 8
    else:
        complexity = "simple"
        max_tool_calls = 4

    return RuntimePolicyResult(
        complexity=complexity,
        risk_level=risk_level,
        required_specialists=specialists,
        audit_required=audit_required,
        allow_market_context="market.context_review" in expanded_capability_ids,
        max_tool_calls=max_tool_calls,
        max_deliberation_rounds=1 if specialists else 0,
    )
