from __future__ import annotations

from app.agents.cfo.decision import (
    CapabilityRequest,
    CfoDecisionResult,
    CfoTurnDecision,
)


class StaticDecisionEngine:
    def __init__(self, decision: CfoTurnDecision | None, *, status: str = "called"):
        self.result = CfoDecisionResult(status=status, decision=decision)

    async def decide(self, *args, **kwargs) -> CfoDecisionResult:
        return self.result


def execute(*capability_ids: str) -> StaticDecisionEngine:
    return StaticDecisionEngine(
        CfoTurnDecision(
            action="execute",
            capability_requests=[
                CapabilityRequest(capability_id=capability_id)
                for capability_id in capability_ids
            ],
        )
    )


def direct(reply: str) -> StaticDecisionEngine:
    return StaticDecisionEngine(CfoTurnDecision(action="direct_response", reply=reply))


def clarify(reply: str) -> StaticDecisionEngine:
    return StaticDecisionEngine(CfoTurnDecision(action="ask_clarification", reply=reply))
