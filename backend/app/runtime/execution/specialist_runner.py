"""Unified specialist handoff execution.

One place owns dispatch, input assembly, output-contract validation, latency
measurement, and failure mapping for every specialist handoff. Specialist
implementations are resolved from `agents/specialists.REGISTRY`, which is
also the seam where an LLM-backed implementation can replace a deterministic
one without touching the orchestrator, contracts, traces, or evals.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.agents.specialists import REGISTRY, SpecialistRun
from app.agents.specialists.contracts import (
    SpecialistAgentOutput,
    SpecialistInput,
)
from app.models.runtime import RuntimePolicyResult
from app.runtime.execution.handoff import HandoffRequest, HandoffResult

logger = logging.getLogger(__name__)


class SpecialistRunner:
    def __init__(self, registry: dict[str, SpecialistRun] | None = None):
        self.registry = registry if registry is not None else REGISTRY

    def run(
        self,
        request: HandoffRequest,
        *,
        policy: RuntimePolicyResult | None = None,
    ) -> HandoffResult:
        started = perf_counter()
        implementation = self.registry.get(request.to_agent)
        if implementation is None:
            return HandoffResult(
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                status="failed",
                error_message=f"Unknown specialist: {request.to_agent}",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        try:
            specialist_input = self._assemble_input(request, policy)
            output = implementation(specialist_input)
            validated = SpecialistAgentOutput.model_validate(output)
            return HandoffResult(
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                status="completed",
                output=validated.model_dump(mode="json"),
                confidence=validated.confidence,
                limitations=validated.limitations,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            logger.warning(
                "Specialist handoff failed: %s -> %s (%s)",
                request.from_agent,
                request.to_agent,
                exc,
            )
            return HandoffResult(
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                status="failed",
                error_message=str(exc),
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    @staticmethod
    def _assemble_input(
        request: HandoffRequest,
        policy: RuntimePolicyResult | None,
    ) -> SpecialistInput:
        evidence: dict[str, Any] = request.evidence or {}
        prior_outputs: dict[str, SpecialistAgentOutput] = {}
        # Auditor-style requests wrap peer outputs beside the finance context;
        # validate them once here so implementations receive typed peers.
        raw_peers = evidence.get("specialists")
        if isinstance(raw_peers, dict):
            prior_outputs = {
                key: SpecialistAgentOutput.model_validate(value)
                for key, value in raw_peers.items()
            }
            evidence = evidence.get("finance_context") or {
                key: value for key, value in evidence.items() if key != "specialists"
            }
        return SpecialistInput(
            task=request.task,
            evidence=evidence,
            artifact_refs=request.artifact_refs,
            allowed_tools=request.allowed_tools,
            constraints=list(request.constraints),
            budget=request.budget,
            policy=policy.model_dump() if policy is not None else {},
            prior_outputs=prior_outputs,
        )
