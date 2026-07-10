from types import SimpleNamespace

import pytest

from app.gateways.agent_gateway.agent_profile import build_finance_agent_profile
from app.gateways.agent_gateway.inbound_gateway import InboundAgentGateway
from app.gateways.agent_gateway.task_contracts import AgentTaskRequest, AgentTaskResponse
from app.gateways.agent_gateway.task_store import AgentTaskStore
from app.routes import agent_gateway as agent_gateway_route


class FakeFinanceRuntime:
    def __init__(self):
        self.calls = []

    async def handle(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "reply": "CFO review complete",
            "agent_used": "cfo",
            "data": {"audit": {"status": "verified"}},
        }


def test_finance_agent_profile_exposes_domain_capabilities():
    profile = build_finance_agent_profile()

    assert profile.agent_id == "personal-finance-cfo"
    assert profile.domain == "personal_finance"
    assert profile.default_entrypoint == "/agent-gateway/tasks"
    assert {capability.name for capability in profile.capabilities} == {
        "spending_review",
        "budget_plan",
        "cashflow_forecast",
        "financial_safety_audit",
        "statement_import_review",
    }


@pytest.mark.asyncio
async def test_inbound_agent_gateway_translates_task_into_finance_runtime():
    runtime = FakeFinanceRuntime()
    store = AgentTaskStore()
    gateway = InboundAgentGateway(
        runtime=runtime,
        task_store=store,
        profile_loader=lambda user_id: SimpleNamespace(
            model_dump=lambda: {"user_id": user_id, "monthly_income": 5000}
        ),
        transactions_loader=lambda user_id, limit: [
            {"description": "Coffee", "amount": -25, "category": "Dining"}
        ],
        analysis_run_loader=lambda user_id: {
            "monthly_totals": [{"month": "2026-06", "net": 3600}]
        },
        chat_history_loader=lambda user_id: [{"role": "user", "content": "old"}],
    )

    response = await gateway.submit_task(
        AgentTaskRequest(
            task_id="task-1",
            user_id="demo",
            requester_agent="career-agent",
            capability="spending_review",
            message="Review my spending before I make a career decision.",
            context={"decision_window": "2 months"},
            correlation_id="corr-1",
        )
    )

    assert response.ok is True
    assert response.task_id == "task-1"
    assert response.status == "completed"
    assert response.reply == "CFO review complete"
    assert response.artifacts["runtime"] == "self_hosted"
    assert store.get("task-1") == response
    assert runtime.calls[0]["user_id"] == "demo"
    assert runtime.calls[0]["profile"]["monthly_income"] == 5000
    assert runtime.calls[0]["transactions"][0]["category"] == "Dining"
    assert runtime.calls[0]["monthly_totals"][0]["net"] == 3600
    assert runtime.calls[0]["chat_history"][0]["content"] == "old"
    assert "External agent task: spending_review" in runtime.calls[0]["message"]
    assert "career-agent" in runtime.calls[0]["message"]


@pytest.mark.asyncio
async def test_agent_gateway_route_submit_uses_gateway(monkeypatch):
    class FakeGateway:
        def __init__(self):
            self.req = None

        async def submit_task(self, req):
            self.req = req
            return AgentTaskResponse(
                ok=True,
                task_id="task-2",
                status="completed",
                capability=req.capability,
                reply="done",
            )

        def get_task(self, task_id):
            return None

    gateway = FakeGateway()
    monkeypatch.setattr(agent_gateway_route, "_gateway", gateway)

    response = await agent_gateway_route.submit_agent_task(
        AgentTaskRequest(capability="budget_plan", message="Build a plan.")
    )

    assert response.task_id == "task-2"
    assert response.capability == "budget_plan"
    assert gateway.req.message == "Build a plan."


def test_agent_gateway_route_get_task_returns_404(monkeypatch):
    class EmptyGateway:
        def get_task(self, task_id):
            return None

    monkeypatch.setattr(agent_gateway_route, "_gateway", EmptyGateway())

    response = agent_gateway_route.get_agent_task("missing")

    assert response.status_code == 404
