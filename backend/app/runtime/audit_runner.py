"""Audit decision helpers for delegated finance analysis."""

from __future__ import annotations

from app.models.runtime import RuntimePolicyResult
from app.tools.audit_tools import build_audit_review


def should_run_audit(
    policy: RuntimePolicyResult,
    *,
    specialists_used: list[str] | None = None,
    tool_error: bool = False,
    data_limited: bool = False,
) -> bool:
    return (
        policy.audit_required
        or bool(specialists_used)
        or tool_error
        or data_limited
    )


def build_runtime_audit_review(
    policy: RuntimePolicyResult,
    context: dict,
    specialist_payloads: dict | None = None,
) -> dict:
    merged_context = {**context, "runtime_policy": policy.model_dump()}
    return build_audit_review(merged_context, specialist_payloads)
