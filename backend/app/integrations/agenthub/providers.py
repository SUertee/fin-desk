"""Read-only providers projecting FinDesk internals onto the Hub protocol."""

from __future__ import annotations

from typing import Any

from app.connectors.postgres.run_ledger_store import (
    get_agent_run_record_db,
    list_agent_run_records_db,
)
from app.gateways.agent_gateway.adapters.a2a_protocol import to_a2a_agent_card
from app.gateways.agent_gateway.agent_profile import (
    FINANCE_AGENT_ID,
    build_finance_agent_profile,
)
from app.runtime.capabilities import get_capability_health_service
from app.runtime.capabilities.definitions import (
    SPECIALIST_CAPABILITY_DEFINITIONS,
    TOOL_CAPABILITY_DEFINITIONS,
)
from app.runtime.observability.steps_projection import project_steps

SCHEMA_VERSION = "0.1"
DEFAULT_USER_ID = "demo"


def _capability_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for definition in (
        list(TOOL_CAPABILITY_DEFINITIONS.values())
        + list(SPECIALIST_CAPABILITY_DEFINITIONS.values())
    ):
        descriptor = definition.descriptor(
            fallback_description=definition.title,
        )
        entries.append(
            {
                "capability_id": descriptor.capability_id,
                "kind": descriptor.kind,
                "title": descriptor.title,
                "description": descriptor.description,
                "risk_level": descriptor.risk_level,
                "execution_mode": descriptor.execution_mode,
                "input_contract": descriptor.input_contract,
                "output_contract": descriptor.output_contract,
            }
        )
    return entries


def build_manifest() -> dict[str, Any]:
    profile = build_finance_agent_profile()
    return {
        "schema_version": SCHEMA_VERSION,
        "identity": {
            "agent_id": profile.agent_id,
            "name": profile.name,
            "version": profile.version,
            "owner": profile.owner,
            "kind": "team",
        },
        "purpose": {
            "role": profile.description,
            "goals": [c.description for c in profile.capabilities],
        },
        "capabilities": _capability_entries(),
        "policy": {
            "execution_modes": ["read_only", "analysis"],
            "notes": ["No trade execution; audit review gates recommendations."],
        },
        "resources": {
            "protocols": profile.supported_protocols,
            "entrypoint": profile.default_entrypoint,
        },
        "topology": {
            "team_id": profile.agent_id,
            "roster_ref": "/agent-gateway/roster",
        },
        "runtime": {"environment": "self-hosted", "protocols": ["http"]},
        "state_ref": "/agent-gateway/state",
        "control_tier_claims": ["catalogued", "observable", "invokable"],
    }


def build_roster() -> dict[str, Any]:
    members = [{"id": "cfo", "role": "CFO orchestrator", "risk_level": "low"}]
    edges: list[dict[str, str]] = []
    for specialist, definition in SPECIALIST_CAPABILITY_DEFINITIONS.items():
        members.append(
            {
                "id": specialist,
                "role": definition.title,
                "risk_level": definition.risk_level,
            }
        )
        edges.append({"from": "cfo", "to": specialist, "kind": "delegation"})
    edges.append({"from": "auditor", "to": "*", "kind": "review_gate"})
    return {
        "schema_version": SCHEMA_VERSION,
        "team_id": FINANCE_AGENT_ID,
        "supervisor": "cfo",
        "members": members,
        "edges": edges,
    }


async def build_state(user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    market_status = await get_capability_health_service().vibe_market_data_status()
    latest = list_agent_run_records_db(user_id, limit=1)
    return {
        "schema_version": SCHEMA_VERSION,
        "online": True,
        "health": [
            {
                "component": "investment.external_market_history",
                "available": bool(market_status.available),
                "reason": market_status.reason,
                "checked_at": (
                    market_status.checked_at.isoformat()
                    if market_status.checked_at
                    else None
                ),
            }
        ],
        "active_runs": 0,
        "last_run_at": latest[0]["created_at"] if latest else None,
    }


def build_runs(
    since: str | None = None,
    *,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 20,
) -> dict[str, Any]:
    summaries = list_agent_run_records_db(
        user_id,
        limit=max(1, min(limit, 100)),
        created_from=since,
    )
    # ledger returns newest-first; the feed is oldest-first for cursor semantics
    summaries = sorted(summaries, key=lambda row: row["created_at"])
    events: list[dict[str, Any]] = []
    for summary in summaries:
        record = get_agent_run_record_db(summary["request_id"])
        steps = project_steps(record) if record else []
        events.append(
            {
                "run_id": summary["request_id"],
                "agent": "cfo",
                "status": "failed" if summary.get("error_type") else "completed",
                "started_at": summary["created_at"],
                "steps": steps,
            }
        )
    cursor = summaries[-1]["created_at"] if summaries else since
    return {"schema_version": SCHEMA_VERSION, "cursor": cursor, "events": events}


def build_agent_card() -> dict[str, Any]:
    profile = build_finance_agent_profile()
    card = to_a2a_agent_card(profile)
    card.setdefault("protocolVersion", "0.3.0")
    card.setdefault(
        "skills",
        [
            {
                "id": capability.name,
                "name": capability.title,
                "description": capability.description,
                "examples": capability.examples,
            }
            for capability in profile.capabilities
        ],
    )
    return card
