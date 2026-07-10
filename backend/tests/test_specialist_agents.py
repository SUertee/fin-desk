import sys
from types import SimpleNamespace

from app.agents.cfo.agent import build_cfo_agent
from app.agents.specialists import (
    OPENAI_SPECIALIST_TOOL_NAMES,
    build_finance_specialist_agent_tools,
)
from app.agents.specialists.contracts import SpecialistAgentOutput
from app.agents.specialists.analysis_agent import build_analysis_agent
from app.agents.specialists.expense_analyst_agent import build_expense_analyst_agent
from app.models.analysis import AnalysisAgentOutput


class FakeAgent:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs["name"]
        FakeAgent.created.append(self)

    def as_tool(self, *, tool_name, tool_description):
        return {
            "tool_name": tool_name,
            "tool_description": tool_description,
            "agent_name": self.name,
        }


def test_specialist_agent_uses_typed_output_contract(monkeypatch):
    FakeAgent.created = []
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(Agent=FakeAgent))

    agent = build_expense_analyst_agent()

    assert agent.kwargs["name"] == "Expense Analyst"
    assert agent.kwargs["output_type"] is SpecialistAgentOutput
    assert "spending" in agent.kwargs["handoff_description"].lower()


def test_analysis_agent_uses_typed_output_contract(monkeypatch):
    FakeAgent.created = []
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(Agent=FakeAgent))

    agent = build_analysis_agent()

    assert agent.kwargs["name"] == "Finance Analysis Specialist"
    assert agent.kwargs["output_type"] is AnalysisAgentOutput


def test_specialist_agents_are_exposed_as_cfo_tools(monkeypatch):
    FakeAgent.created = []
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(Agent=FakeAgent))

    tools = build_finance_specialist_agent_tools()

    assert [tool["tool_name"] for tool in tools] == OPENAI_SPECIALIST_TOOL_NAMES
    assert [tool["agent_name"] for tool in tools] == [
        "Expense Analyst",
        "Budget Coach",
        "Finance Auditor",
    ]


def test_cfo_agent_includes_finance_tools_and_specialist_agent_tools(monkeypatch):
    FakeAgent.created = []
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(Agent=FakeAgent))

    cfo = build_cfo_agent(tools=["get_finance_context"])

    tool_names = [
        tool["tool_name"] if isinstance(tool, dict) else tool
        for tool in cfo.kwargs["tools"]
    ]
    assert tool_names == ["get_finance_context", *OPENAI_SPECIALIST_TOOL_NAMES]
