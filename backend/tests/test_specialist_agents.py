import sys
from types import SimpleNamespace

from app.agents.specialists.analysis_agent import build_analysis_agent
from app.models.analysis import AnalysisAgentOutput


class FakeAgent:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs["name"]
        FakeAgent.created.append(self)

def test_analysis_agent_uses_typed_output_contract(monkeypatch):
    FakeAgent.created = []
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(Agent=FakeAgent))

    agent = build_analysis_agent()

    assert agent.kwargs["name"] == "Finance Analysis Specialist"
    assert agent.kwargs["output_type"] is AnalysisAgentOutput
