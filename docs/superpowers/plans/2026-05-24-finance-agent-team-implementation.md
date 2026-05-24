# Finance Agent Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first end-to-end version of the personal finance agent team with a DeepAgents-ready backend runtime boundary and a unified Finance OS frontend experience.

**Architecture:** Keep FastAPI, the existing `/chat` route, and the current LangGraph graph as a fallback. Add a `FinanceTeamRuntime` abstraction that can choose `deepagents` or `langgraph` by feature flag, normalize structured agent output, and feed a redesigned React agent team panel. The frontend keeps the existing dashboard data flow while replacing the plain AI sidebar with a calmer, structured agent team interface.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, LangChain/LangGraph, LangChain DeepAgents, React 18, Vite, TypeScript, Recharts, lucide-react.

---

## File Structure

Backend files:

- Create `server/models/agent_data.py`: typed Pydantic models for structured agent output.
- Modify `server/models/chat.py`: use the new `FinanceAgentData` type for `ChatResponse.data`.
- Create `server/agents/finance_tools.py`: deterministic finance summarization helpers that agents can use through bounded wrappers.
- Create `server/agents/deep_agent_factory.py`: DeepAgents factory, prompts, subagent specs, and guarded `deepagents` import.
- Create `server/agents/deep_runtime.py`: `FinanceTeamRuntime` with feature flag routing, DeepAgents invocation, output normalization, and LangGraph fallback.
- Modify `server/agents/orchestrator.py`: delegate to `FinanceTeamRuntime` while preserving `handle_message(...)`.
- Modify `server/requirements.txt`: add `deepagents` and `pytest`.
- Create `server/tests/test_agent_data.py`: model and normalization tests.
- Create `server/tests/test_finance_tools.py`: deterministic finance tool tests.
- Create `server/tests/test_deep_runtime.py`: runtime routing and fallback tests.

Frontend files:

- Create `client/src/types/financeAgent.ts`: shared structured response types matching backend shape.
- Modify `client/src/services/supabaseApi.ts`: add `sendChatMessage(...)`.
- Modify `client/src/types/agents.tsx`: align agent roster with CFO, Expense Analyst, Budget Coach, Auditor, Market Scout.
- Create `client/src/components/AgentResponse.tsx`: render reply, findings, actions, and audit status.
- Create `client/src/components/AgentTeamPanel.tsx`: replacement for `AiSidebar`.
- Create `client/src/components/OperatingSummary.tsx`: unified operating summary row.
- Modify `client/src/components/Header.tsx`: calmer Finance OS header language and spacing.
- Modify `client/src/App.tsx`: integrate `OperatingSummary` and `AgentTeamPanel`.
- Modify `client/src/styles/globals.css` or existing component classes only if a shared style token is needed.

Verification:

- Backend unit tests via `python -m pytest server/tests -q`.
- Frontend build via `npm run build` from `client/`.
- Manual browser verification at desktop and mobile widths.

---

### Task 1: Add Structured Agent Data Contract

**Files:**

- Create: `server/models/agent_data.py`
- Modify: `server/models/chat.py`
- Test: `server/tests/test_agent_data.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_agent_data.py`:

```python
from models.agent_data import (
    AgentAction,
    AgentAudit,
    AgentFinding,
    FinanceAgentData,
    SummaryCard,
    normalize_finance_agent_data,
)
from models.chat import ChatResponse


def test_finance_agent_data_accepts_expected_sections():
    data = FinanceAgentData(
        summary_cards=[
            SummaryCard(
                label="Budget risk",
                value="Low",
                status="good",
                note="Spending is below the monthly target.",
            )
        ],
        findings=[
            AgentFinding(
                agent="expense_analyst",
                title="Dining increased",
                evidence=["Dining spend is 18% above the prior average."],
            )
        ],
        actions=[
            AgentAction(
                title="Set a dining alert",
                rationale="The category is the main monthly variance.",
                effort="low",
                impact="medium",
            )
        ],
        audit=AgentAudit(
            confidence=0.82,
            status="verified",
            warnings=[],
        ),
    )

    dumped = data.model_dump()

    assert dumped["summary_cards"][0]["status"] == "good"
    assert dumped["findings"][0]["agent"] == "expense_analyst"
    assert dumped["actions"][0]["effort"] == "low"
    assert dumped["audit"]["confidence"] == 0.82


def test_normalize_finance_agent_data_discards_invalid_sections():
    normalized = normalize_finance_agent_data(
        {
            "summary_cards": [{"label": "Cash flow", "value": "+1200", "status": "good"}],
            "findings": [{"agent": "auditor", "title": "Data limited", "evidence": []}],
            "actions": [{"title": "Broken action", "rationale": "Missing effort and impact"}],
            "audit": {"confidence": 2.5, "status": "verified", "warnings": []},
        }
    )

    assert normalized is not None
    assert len(normalized.summary_cards or []) == 1
    assert len(normalized.findings or []) == 1
    assert normalized.actions is None
    assert normalized.audit is None


def test_chat_response_accepts_finance_agent_data():
    data = FinanceAgentData(
        audit=AgentAudit(
            confidence=0.5,
            status="data_limited",
            warnings=["Only 30 days of transactions were available."],
        )
    )

    response = ChatResponse(
        reply="本月现金流稳定，但数据样本有限。",
        agent_used="cfo",
        data=data,
    )

    assert response.data.audit.status == "data_limited"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
python -m pytest tests/test_agent_data.py -q
```

Expected: fail because `models.agent_data` does not exist.

- [ ] **Step 3: Implement the model contract**

Create `server/models/agent_data.py`:

```python
"""
Structured data returned by the finance agent team.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


SummaryStatus = Literal["neutral", "good", "watch", "risk"]
EffortLevel = Literal["low", "medium", "high"]
ImpactLevel = Literal["low", "medium", "high"]
AuditStatus = Literal["verified", "needs_review", "data_limited"]


class SummaryCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    status: SummaryStatus = "neutral"
    note: str | None = None


class AgentFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str
    title: str
    evidence: list[str] = Field(default_factory=list)


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    rationale: str
    effort: EffortLevel
    impact: ImpactLevel


class AgentAudit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confidence: float = Field(ge=0.0, le=1.0)
    status: AuditStatus
    warnings: list[str] = Field(default_factory=list)


class FinanceAgentData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary_cards: list[SummaryCard] | None = None
    findings: list[AgentFinding] | None = None
    actions: list[AgentAction] | None = None
    audit: AgentAudit | None = None


def _normalize_list(model: type[BaseModel], value: object) -> list[BaseModel] | None:
    if not isinstance(value, list):
        return None

    items: list[BaseModel] = []
    for raw_item in value:
        try:
            items.append(model.model_validate(raw_item))
        except ValidationError:
            continue

    return items or None


def normalize_finance_agent_data(value: object) -> FinanceAgentData | None:
    if isinstance(value, FinanceAgentData):
        return value
    if not isinstance(value, dict):
        return None

    audit = None
    try:
        audit = AgentAudit.model_validate(value.get("audit"))
    except ValidationError:
        audit = None

    normalized = FinanceAgentData(
        summary_cards=_normalize_list(SummaryCard, value.get("summary_cards")),
        findings=_normalize_list(AgentFinding, value.get("findings")),
        actions=_normalize_list(AgentAction, value.get("actions")),
        audit=audit,
    )

    if not any(
        [
            normalized.summary_cards,
            normalized.findings,
            normalized.actions,
            normalized.audit,
        ]
    ):
        return None

    return normalized
```

Modify `server/models/chat.py`:

```python
"""
Chat-related Pydantic models: request and response.
"""

from typing import Optional

from pydantic import BaseModel

from models.agent_data import FinanceAgentData


class ChatRequest(BaseModel):
    message: str
    user_id: str = "demo"


class ChatResponse(BaseModel):
    reply: str
    agent_used: Optional[str] = None
    data: Optional[FinanceAgentData] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd server
python -m pytest tests/test_agent_data.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/models/agent_data.py server/models/chat.py server/tests/test_agent_data.py
git commit -m "feat: add finance agent data contract"
```

---

### Task 2: Add Deterministic Finance Agent Tools

**Files:**

- Create: `server/agents/finance_tools.py`
- Test: `server/tests/test_finance_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_finance_tools.py`:

```python
from agents.finance_tools import (
    build_budget_snapshot,
    build_expense_snapshot,
    build_finance_context_payload,
)


TRANSACTIONS = [
    {
        "date": "2026-05-01",
        "month": "2026-05",
        "description": "Salary",
        "category": "Income",
        "amount": 20000,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-02",
        "month": "2026-05",
        "description": "Restaurant A",
        "category": "Dining",
        "amount": -300,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-03",
        "month": "2026-05",
        "description": "Rent",
        "category": "Housing",
        "amount": -5000,
        "currency": "CNY",
        "is_duplicate": False,
    },
    {
        "date": "2026-05-03",
        "month": "2026-05",
        "description": "Rent duplicate",
        "category": "Housing",
        "amount": -5000,
        "currency": "CNY",
        "is_duplicate": True,
    },
]


def test_build_expense_snapshot_excludes_duplicates():
    snapshot = build_expense_snapshot(TRANSACTIONS, [])

    assert snapshot["transaction_count"] == 3
    assert snapshot["expense_total"] == 5300
    assert snapshot["income_total"] == 20000
    assert snapshot["net_total"] == 14700
    assert snapshot["top_categories"][0]["category"] == "Housing"


def test_build_budget_snapshot_uses_monthly_income():
    snapshot = build_budget_snapshot(
        {"monthly_income": 20000, "financial_goals": ["save more"]},
        TRANSACTIONS,
        [],
    )

    assert snapshot["monthly_income"] == 20000
    assert snapshot["expense_ratio"] == 0.265
    assert snapshot["status"] == "good"


def test_build_finance_context_payload_limits_transactions():
    payload = build_finance_context_payload(
        user_id="demo",
        profile={"name": "Demo", "monthly_income": 20000},
        transactions=TRANSACTIONS,
        monthly_totals=[],
        chat_history=[{"role": "user", "content": "hello"}],
    )

    assert payload["user_id"] == "demo"
    assert payload["profile"]["name"] == "Demo"
    assert len(payload["transactions_sample"]) == 3
    assert payload["expense_snapshot"]["expense_total"] == 5300
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
python -m pytest tests/test_finance_tools.py -q
```

Expected: fail because `agents.finance_tools` does not exist.

- [ ] **Step 3: Implement deterministic finance helpers**

Create `server/agents/finance_tools.py`:

```python
"""
Bounded finance helpers for agent use.

These functions do not query the database directly. The API layer/runtime passes
profile, transaction, and monthly-total context in explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.anomalies import detect_anomalies
from services.summaries import build_category_summary


def _active_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in transactions if not t.get("is_duplicate")]


def _round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def build_expense_snapshot(
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
) -> dict[str, Any]:
    active = _active_transactions(transactions)
    income_total = 0.0
    expense_total = 0.0
    by_category: dict[str, float] = defaultdict(float)

    for txn in active:
        amount = txn.get("amount")
        if not isinstance(amount, (int, float)):
            continue

        if amount > 0:
            income_total += float(amount)
            continue

        spend = abs(float(amount))
        expense_total += spend
        by_category[txn.get("category") or "Uncategorized"] += spend

    top_categories = sorted(
        [
            {"category": category, "amount": _round_money(amount)}
            for category, amount in by_category.items()
        ],
        key=lambda item: item["amount"],
        reverse=True,
    )[:8]

    anomalies = detect_anomalies(active)
    category_summary = build_category_summary(active)

    return {
        "transaction_count": len(active),
        "income_total": _round_money(income_total),
        "expense_total": _round_money(expense_total),
        "net_total": _round_money(income_total - expense_total),
        "top_categories": top_categories,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:10],
        "category_summary": category_summary,
        "monthly_totals": monthly_totals,
    }


def build_budget_snapshot(
    profile: dict[str, Any],
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
) -> dict[str, Any]:
    expense_snapshot = build_expense_snapshot(transactions, monthly_totals)
    monthly_income = float(profile.get("monthly_income") or 0)
    expense_total = float(expense_snapshot["expense_total"])
    expense_ratio = round(expense_total / monthly_income, 3) if monthly_income > 0 else None

    if expense_ratio is None:
        status = "data_limited"
    elif expense_ratio <= 0.5:
        status = "good"
    elif expense_ratio <= 0.8:
        status = "watch"
    else:
        status = "risk"

    return {
        "monthly_income": _round_money(monthly_income),
        "expense_total": expense_snapshot["expense_total"],
        "net_total": expense_snapshot["net_total"],
        "expense_ratio": expense_ratio,
        "status": status,
        "financial_goals": profile.get("financial_goals") or [],
    }


def build_finance_context_payload(
    user_id: str,
    profile: dict[str, Any],
    transactions: list[dict[str, Any]],
    monthly_totals: list[dict[str, Any]],
    chat_history: list[dict[str, Any]],
) -> dict[str, Any]:
    active = _active_transactions(transactions)
    return {
        "user_id": user_id,
        "profile": profile,
        "transactions_sample": active[:80],
        "monthly_totals": monthly_totals,
        "chat_history": chat_history[-10:],
        "expense_snapshot": build_expense_snapshot(active, monthly_totals),
        "budget_snapshot": build_budget_snapshot(profile, active, monthly_totals),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd server
python -m pytest tests/test_finance_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/agents/finance_tools.py server/tests/test_finance_tools.py
git commit -m "feat: add deterministic finance agent tools"
```

---

### Task 3: Add FinanceTeamRuntime With LangGraph Fallback

**Files:**

- Create: `server/agents/deep_runtime.py`
- Modify: `server/agents/orchestrator.py`
- Test: `server/tests/test_deep_runtime.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_deep_runtime.py`:

```python
import pytest

from agents.deep_runtime import FinanceTeamRuntime


class FakeLangGraphRunner:
    async def ainvoke(self, state):
        return {
            "final_reply": "fallback reply",
            "agent_used": "general",
            "agent_data": {
                "audit": {
                    "confidence": 0.4,
                    "status": "data_limited",
                    "warnings": ["fallback used"],
                }
            },
        }


@pytest.mark.asyncio
async def test_runtime_uses_langgraph_when_flag_is_langgraph(monkeypatch):
    monkeypatch.setenv("FINANCE_AGENT_RUNTIME", "langgraph")
    runtime = FinanceTeamRuntime(langgraph_runner=FakeLangGraphRunner())

    result = await runtime.handle(
        user_id="demo",
        message="hello",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["reply"] == "fallback reply"
    assert result["agent_used"] == "general"
    assert result["data"].audit.status == "data_limited"


@pytest.mark.asyncio
async def test_runtime_falls_back_when_deepagents_fails(monkeypatch):
    monkeypatch.setenv("FINANCE_AGENT_RUNTIME", "deepagents")

    class FailingRuntime(FinanceTeamRuntime):
        async def _invoke_deepagents(self, context):
            raise RuntimeError("deepagents unavailable")

    runtime = FailingRuntime(langgraph_runner=FakeLangGraphRunner())

    result = await runtime.handle(
        user_id="demo",
        message="hello",
        profile={"name": "Demo"},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert result["reply"] == "fallback reply"
    assert result["agent_used"] == "general"
    assert result["data"].audit.warnings == ["fallback used"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
python -m pytest tests/test_deep_runtime.py -q
```

Expected: fail because `agents.deep_runtime` does not exist.

- [ ] **Step 3: Implement runtime boundary**

Create `server/agents/deep_runtime.py`:

```python
"""
Runtime boundary for the finance agent team.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agents.finance_tools import build_finance_context_payload
from models.agent_data import FinanceAgentData, normalize_finance_agent_data

logger = logging.getLogger(__name__)


class FinanceTeamRuntime:
    def __init__(self, langgraph_runner: Any):
        self.langgraph_runner = langgraph_runner

    async def handle(
        self,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        context = build_finance_context_payload(
            user_id=user_id,
            profile=profile,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
        )
        context["message"] = message

        runtime = os.getenv("FINANCE_AGENT_RUNTIME", "langgraph").lower()
        if runtime == "deepagents":
            try:
                return await self._invoke_deepagents(context)
            except Exception:
                logger.exception("DeepAgents runtime failed; falling back to LangGraph")

        return await self._invoke_langgraph(
            user_id=user_id,
            message=message,
            profile=profile,
            transactions=transactions,
            monthly_totals=monthly_totals,
            chat_history=chat_history,
        )

    async def _invoke_deepagents(self, context: dict[str, Any]) -> dict[str, Any]:
        from agents.deep_agent_factory import invoke_finance_deep_agent

        result = await invoke_finance_deep_agent(context)
        data = normalize_finance_agent_data(result.get("data"))
        return {
            "reply": result.get("reply") or "I could not produce a finance summary.",
            "agent_used": result.get("agent_used") or "cfo",
            "data": data,
        }

    async def _invoke_langgraph(
        self,
        user_id: str,
        message: str,
        profile: dict[str, Any],
        transactions: list[dict[str, Any]],
        monthly_totals: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = {
            "user_id": user_id,
            "message": message,
            "profile": profile,
            "transactions": transactions,
            "monthly_totals": monthly_totals,
            "chat_history": chat_history,
            "routed_agent": "",
            "refined_query": "",
            "agent_reply": "",
            "agent_data": None,
            "needs_advisor_review": False,
            "advisor_comment": "",
            "final_reply": "",
            "agent_used": "",
        }
        result = await self.langgraph_runner.ainvoke(state)
        data = normalize_finance_agent_data(result.get("agent_data"))
        return {
            "reply": result.get("final_reply") or result.get("agent_reply") or "",
            "agent_used": result.get("agent_used") or "general",
            "data": data,
        }
```

Modify `server/agents/orchestrator.py`:

```python
"""
Orchestrator Agent - stable public entrypoint for finance chat.
"""

import logging

from agents.deep_runtime import FinanceTeamRuntime
from agents.graph import build_agent_graph
from services.memory import get_chat_history, save_message
from services.user_store import get_profile

logger = logging.getLogger(__name__)

_graph = build_agent_graph()
_runtime = FinanceTeamRuntime(langgraph_runner=_graph)


async def handle_message(
    user_id: str,
    message: str,
    transactions: list[dict] | None = None,
    monthly_totals: list[dict] | None = None,
) -> dict:
    profile = get_profile(user_id)
    chat_history = get_chat_history(user_id)
    try:
        result = await _runtime.handle(
            user_id=user_id,
            message=message,
            profile=profile.model_dump(),
            transactions=transactions or [],
            monthly_totals=monthly_totals or [],
            chat_history=chat_history,
        )
    except Exception:
        logger.exception("Finance runtime failed for user=%s", user_id)
        return {
            "reply": "Sorry, something went wrong. Please try again.",
            "agent_used": "error",
            "data": None,
        }

    save_message(user_id, "user", message)
    save_message(user_id, "assistant", result["reply"])
    logger.info(
        "Handled message for user=%s, agent=%s",
        user_id,
        result.get("agent_used", "general"),
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd server
python -m pytest tests/test_deep_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run backend tests accumulated so far**

Run:

```bash
cd server
python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/agents/deep_runtime.py server/agents/orchestrator.py server/tests/test_deep_runtime.py
git commit -m "feat: add finance team runtime boundary"
```

---

### Task 4: Add DeepAgents Factory Behind Guarded Import

**Files:**

- Create: `server/agents/deep_agent_factory.py`
- Modify: `server/requirements.txt`
- Test: `server/tests/test_deep_agent_factory.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_deep_agent_factory.py`:

```python
import pytest

from agents import deep_agent_factory


def test_build_subagents_contains_finance_team_members():
    names = {subagent["name"] for subagent in deep_agent_factory.build_finance_subagents()}

    assert names == {
        "expense_analyst",
        "budget_coach",
        "auditor",
        "market_scout",
    }


def test_extract_text_reply_handles_deepagents_messages():
    result = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "final answer"},
        ]
    }

    assert deep_agent_factory.extract_text_reply(result) == "final answer"


@pytest.mark.asyncio
async def test_invoke_finance_deep_agent_raises_clear_error_without_package(monkeypatch):
    monkeypatch.setattr(deep_agent_factory, "create_deep_agent", None)

    with pytest.raises(RuntimeError, match="deepagents package is not installed"):
        await deep_agent_factory.invoke_finance_deep_agent(
            {
                "message": "health check",
                "profile": {"name": "Demo"},
                "expense_snapshot": {},
                "budget_snapshot": {},
                "transactions_sample": [],
                "monthly_totals": [],
                "chat_history": [],
            }
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server
python -m pytest tests/test_deep_agent_factory.py -q
```

Expected: fail because `agents.deep_agent_factory` does not exist.

- [ ] **Step 3: Implement guarded DeepAgents factory**

Create `server/agents/deep_agent_factory.py`:

```python
"""
LangChain DeepAgents factory for the finance team.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from deepagents import create_deep_agent
except Exception:
    create_deep_agent = None


CFO_SYSTEM_PROMPT = """You are the CFO agent for a personal finance operating system.

Your job:
- Coordinate the finance agent team.
- Use specialist subagents when the question needs expense analysis, budget coaching, audit review, or market context.
- Give concise answers in the user's language.
- Always separate conclusion, evidence, and actions.
- Do not present risky investment guidance as certainty.

Return a final answer that can be read directly by the user.
"""


def build_finance_subagents() -> list[dict[str, Any]]:
    return [
        {
            "name": "expense_analyst",
            "description": "Analyzes spending, category changes, anomalies, merchants, and duplicate-sensitive totals.",
            "system_prompt": "You are Expense Analyst. Return concise findings with specific evidence from the provided finance context. Focus on spending, categories, anomalies, and merchant concentration.",
        },
        {
            "name": "budget_coach",
            "description": "Turns finance context into budget limits, behavior interventions, reminders, and low-friction next actions.",
            "system_prompt": "You are Budget Coach. Return practical budget and behavior recommendations. Keep actions specific, low-friction, and tied to evidence.",
        },
        {
            "name": "auditor",
            "description": "Reviews finance answers for evidence quality, overconfidence, data limitations, and risky claims.",
            "system_prompt": "You are Auditor. Review claims for factual support, data limitations, and risk. Return confidence from 0 to 1 plus warnings.",
        },
        {
            "name": "market_scout",
            "description": "Provides lightweight market or macro context when relevant, with conservative risk framing.",
            "system_prompt": "You are Market Scout. Provide market context only when it is relevant. Avoid direct investment instructions. Always include limitations.",
        },
    ]


def extract_text_reply(result: dict[str, Any]) -> str:
    messages = result.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                content = message.get("content")
                if isinstance(content, str):
                    return content
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content

    output = result.get("output") or result.get("content")
    if isinstance(output, str):
        return output

    return ""


def _build_prompt(context: dict[str, Any]) -> str:
    payload = {
        "user_message": context["message"],
        "profile": context.get("profile", {}),
        "expense_snapshot": context.get("expense_snapshot", {}),
        "budget_snapshot": context.get("budget_snapshot", {}),
        "monthly_totals": context.get("monthly_totals", []),
        "transactions_sample": context.get("transactions_sample", []),
        "recent_chat_history": context.get("chat_history", []),
    }
    return (
        "Analyze this personal finance request. Use the finance team subagents when useful.\n"
        "After the narrative answer, include a compact JSON block with keys: "
        "summary_cards, findings, actions, audit.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _parse_embedded_data(reply: str) -> dict[str, Any] | None:
    start = reply.rfind("{")
    end = reply.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def invoke_finance_deep_agent(context: dict[str, Any]) -> dict[str, Any]:
    if create_deep_agent is None:
        raise RuntimeError("deepagents package is not installed")

    model = os.getenv("DEEPAGENTS_MODEL") or os.getenv("OPENAI_MODEL") or "openai:gpt-4o-mini"
    agent = create_deep_agent(
        model=model,
        system_prompt=CFO_SYSTEM_PROMPT,
        subagents=build_finance_subagents(),
        name="finance-cfo",
    )
    result = await agent.ainvoke({"messages": [{"role": "user", "content": _build_prompt(context)}]})
    reply = extract_text_reply(result)
    return {
        "reply": reply,
        "agent_used": "cfo",
        "data": _parse_embedded_data(reply),
    }
```

Modify `server/requirements.txt` by adding:

```text
deepagents>=0.0.1
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
cd server
python -m pytest tests/test_deep_agent_factory.py -q
```

Expected: all tests pass without requiring the `deepagents` package to be importable.

- [ ] **Step 5: Run backend tests**

Run:

```bash
cd server
python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/agents/deep_agent_factory.py server/requirements.txt server/tests/test_deep_agent_factory.py
git commit -m "feat: add guarded deepagents factory"
```

---

### Task 5: Add Frontend Agent Types And Chat API

**Files:**

- Create: `client/src/types/financeAgent.ts`
- Modify: `client/src/services/supabaseApi.ts`
- Modify: `client/src/types/agents.tsx`

- [ ] **Step 1: Add shared structured response types**

Create `client/src/types/financeAgent.ts`:

```ts
export type SummaryStatus = "neutral" | "good" | "watch" | "risk";
export type EffortLevel = "low" | "medium" | "high";
export type ImpactLevel = "low" | "medium" | "high";
export type AuditStatus = "verified" | "needs_review" | "data_limited";

export type SummaryCard = {
  label: string;
  value: string;
  status?: SummaryStatus;
  note?: string | null;
};

export type AgentFinding = {
  agent: string;
  title: string;
  evidence: string[];
};

export type AgentAction = {
  title: string;
  rationale: string;
  effort: EffortLevel;
  impact: ImpactLevel;
};

export type AgentAudit = {
  confidence: number;
  status: AuditStatus;
  warnings: string[];
};

export type FinanceAgentData = {
  summary_cards?: SummaryCard[] | null;
  findings?: AgentFinding[] | null;
  actions?: AgentAction[] | null;
  audit?: AgentAudit | null;
};

export type ChatResponse = {
  reply: string;
  agent_used?: string | null;
  data?: FinanceAgentData | null;
};
```

- [ ] **Step 2: Add chat API helper**

Append to `client/src/services/supabaseApi.ts`:

```ts
import type { ChatResponse } from "../types/financeAgent";

export async function sendChatMessage(
  userId: string,
  message: string
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as ChatResponse;
}
```

If TypeScript complains about import ordering, move the new type import next to the existing import at the top:

```ts
import type { AnalysisRunRow, TransactionRow } from "../types/db";
import type { ChatResponse } from "../types/financeAgent";
```

- [ ] **Step 3: Replace frontend agent roster**

Replace `client/src/types/agents.tsx` with:

```tsx
import type { ReactNode } from "react";
import {
  BadgeCheck,
  ChartNoAxesCombined,
  ClipboardCheck,
  Landmark,
  LineChart,
} from "lucide-react";

export type AgentType =
  | "cfo"
  | "expense_analyst"
  | "budget_coach"
  | "auditor"
  | "market_scout";

export type AgentMeta = {
  id: AgentType;
  label: string;
  shortLabel: string;
  summary: string;
  promptPrefix: string;
  badgeClass: string;
  icon: ReactNode;
};

export const AGENTS: AgentMeta[] = [
  {
    id: "cfo",
    label: "CFO",
    shortLabel: "CFO",
    summary: "统一入口，协调团队并输出优先级决策。",
    promptPrefix: "[CFO] ",
    badgeClass: "bg-[#172026] text-white",
    icon: <Landmark className="h-4 w-4" />,
  },
  {
    id: "expense_analyst",
    label: "Expense Analyst",
    shortLabel: "Expense",
    summary: "分析支出结构、类别变化、异常和重复交易。",
    promptPrefix: "[Expense Analyst] ",
    badgeClass: "bg-[#4b8078] text-white",
    icon: <ChartNoAxesCombined className="h-4 w-4" />,
  },
  {
    id: "budget_coach",
    label: "Budget Coach",
    shortLabel: "Budget",
    summary: "把预算压力转成低摩擦行动和提醒规则。",
    promptPrefix: "[Budget Coach] ",
    badgeClass: "bg-[#6f7f62] text-white",
    icon: <ClipboardCheck className="h-4 w-4" />,
  },
  {
    id: "auditor",
    label: "Auditor",
    shortLabel: "Audit",
    summary: "检查证据、风险、过度自信和数据限制。",
    promptPrefix: "[Auditor] ",
    badgeClass: "bg-[#5f6f78] text-white",
    icon: <BadgeCheck className="h-4 w-4" />,
  },
  {
    id: "market_scout",
    label: "Market Scout",
    shortLabel: "Market",
    summary: "提供轻量市场和宏观背景，保持风险克制。",
    promptPrefix: "[Market Scout] ",
    badgeClass: "bg-[#7b6f58] text-white",
    icon: <LineChart className="h-4 w-4" />,
  },
];
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add client/src/types/financeAgent.ts client/src/services/supabaseApi.ts client/src/types/agents.tsx
git commit -m "feat: add frontend finance agent contract"
```

---

### Task 6: Replace AI Sidebar With Agent Team Panel

**Files:**

- Create: `client/src/components/AgentResponse.tsx`
- Create: `client/src/components/AgentTeamPanel.tsx`
- Modify: `client/src/App.tsx`

- [ ] **Step 1: Create structured agent response renderer**

Create `client/src/components/AgentResponse.tsx`:

```tsx
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  CircleDot,
} from "lucide-react";
import type { FinanceAgentData } from "../types/financeAgent";

type AgentResponseProps = {
  content: string;
  data?: FinanceAgentData | null;
};

const auditLabel = {
  verified: "Verified",
  needs_review: "Needs review",
  data_limited: "Data limited",
};

export function AgentResponse({ content, data }: AgentResponseProps) {
  const audit = data?.audit ?? null;

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[#dfe5e3] bg-white px-3 py-3 text-sm leading-relaxed text-[#24302c]">
        {content}
      </div>

      {data?.findings && data.findings.length > 0 && (
        <section className="rounded-xl border border-[#dfe5e3] bg-[#f8faf9] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#172026]">
            <CircleDot className="h-3.5 w-3.5 text-[#4b8078]" />
            Findings
          </div>
          <div className="space-y-2">
            {data.findings.map((finding, index) => (
              <div key={`${finding.agent}-${index}`} className="text-xs text-[#53615d]">
                <div className="font-medium text-[#24302c]">{finding.title}</div>
                {finding.evidence.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {finding.evidence.map((item, evidenceIndex) => (
                      <li key={evidenceIndex}>- {item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {data?.actions && data.actions.length > 0 && (
        <section className="rounded-xl border border-[#dfe5e3] bg-white p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#172026]">
            <CheckCircle2 className="h-3.5 w-3.5 text-[#4b8078]" />
            Actions
          </div>
          <div className="space-y-2">
            {data.actions.map((action, index) => (
              <div key={`${action.title}-${index}`} className="text-xs">
                <div className="font-medium text-[#24302c]">{action.title}</div>
                <div className="mt-0.5 text-[#53615d]">{action.rationale}</div>
                <div className="mt-1 text-[11px] text-[#75827e]">
                  Effort {action.effort} · Impact {action.impact}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {audit && (
        <div className="flex items-center justify-between rounded-xl border border-[#dfe5e3] bg-[#f8faf9] px-3 py-2 text-xs text-[#53615d]">
          <div className="flex items-center gap-2">
            {audit.status === "verified" ? (
              <BadgeCheck className="h-3.5 w-3.5 text-[#4b8078]" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-[#947348]" />
            )}
            <span>{auditLabel[audit.status]}</span>
          </div>
          <span>{Math.round(audit.confidence * 100)}% confidence</span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create AgentTeamPanel**

Create `client/src/components/AgentTeamPanel.tsx`:

```tsx
import React, { useMemo, useState } from "react";
import { PanelRightClose, Send, X } from "lucide-react";
import { sendChatMessage } from "../services/supabaseApi";
import { AGENTS, type AgentType } from "../types/agents";
import type { ChatResponse } from "../types/financeAgent";
import { AgentResponse } from "./AgentResponse";

interface AgentTeamPanelProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
}

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; response?: ChatResponse };

export function AgentTeamPanel({ isOpen, onClose, userId }: AgentTeamPanelProps) {
  const [activeAgent, setActiveAgent] = useState<AgentType>("cfo");
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const activeMeta = useMemo(
    () => AGENTS.find((agent) => agent.id === activeAgent) ?? AGENTS[0],
    [activeAgent]
  );

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || isSending) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: prompt }]);
    setIsSending(true);

    try {
      const response = await sendChatMessage(userId, `${activeMeta.promptPrefix}${prompt}`);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.reply,
          response,
        },
      ]);
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: error?.message ?? "Request failed. Check the server.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <aside className="fixed right-0 top-0 z-40 flex h-screen w-[430px] flex-col border-l border-[#dfe5e3] bg-[#f7f8f8] shadow-[0_18px_60px_rgba(23,32,38,0.12)]">
      <div className="border-b border-[#dfe5e3] bg-white px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[#172026]">Agent Team</div>
            <div className="mt-1 text-xs text-[#697571]">
              CFO coordinates specialist analysis and audit review.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-[#697571] transition-colors hover:bg-[#eef2f1] hover:text-[#172026]"
            title="Close Agent Team"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="border-b border-[#dfe5e3] bg-white px-5 py-3">
        <div className="grid grid-cols-5 gap-2">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              type="button"
              onClick={() => setActiveAgent(agent.id)}
              className={`rounded-xl border px-2 py-2 text-left transition-colors ${
                activeAgent === agent.id
                  ? "border-[#4b8078] bg-[#eef5f3]"
                  : "border-[#dfe5e3] bg-white hover:bg-[#f7f8f8]"
              }`}
              title={agent.label}
            >
              <div
                className={`mb-1 flex h-7 w-7 items-center justify-center rounded-lg ${agent.badgeClass}`}
              >
                {agent.icon}
              </div>
              <div className="truncate text-[11px] font-medium text-[#24302c]">
                {agent.shortLabel}
              </div>
            </button>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-[#dfe5e3] bg-[#f8faf9] px-3 py-2">
          <div className="text-xs font-medium text-[#24302c]">{activeMeta.label}</div>
          <div className="mt-0.5 text-xs text-[#697571]">{activeMeta.summary}</div>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="rounded-xl border border-[#dfe5e3] bg-white p-4 text-sm text-[#53615d]">
            Ask the CFO for a monthly health check, or choose a specialist for a narrower review.
          </div>
        ) : (
          messages.map((message, index) =>
            message.role === "user" ? (
              <div
                key={index}
                className="ml-10 rounded-xl bg-[#172026] px-3 py-2 text-sm leading-relaxed text-white"
              >
                {message.content}
              </div>
            ) : (
              <AgentResponse
                key={index}
                content={message.content}
                data={message.response?.data}
              />
            )
          )
        )}
        {isSending && <div className="text-xs text-[#697571]">Analyzing...</div>}
      </div>

      <div className="border-t border-[#dfe5e3] bg-white p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={`Ask ${activeMeta.label}...`}
            className="min-w-0 flex-1 rounded-xl border border-[#ccd6d3] bg-white px-3 py-2 text-sm text-[#172026] outline-none transition focus:border-[#4b8078] focus:ring-2 focus:ring-[#d9e9e5]"
          />
          <button
            type="submit"
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#172026] text-white transition-colors hover:bg-[#24302c] disabled:opacity-60"
            disabled={isSending}
            title="Send"
          >
            <Send className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#dfe5e3] text-[#697571] transition-colors hover:bg-[#f7f8f8]"
            title="Collapse panel"
          >
            <PanelRightClose className="h-4 w-4" />
          </button>
        </form>
      </div>
    </aside>
  );
}
```

- [ ] **Step 3: Integrate the new panel in App**

In `client/src/App.tsx`, replace:

```tsx
import { AiSidebar } from "./components/AiSidebar";
```

with:

```tsx
import { AgentTeamPanel } from "./components/AgentTeamPanel";
```

Replace the bottom panel usage:

```tsx
<AiSidebar
  isOpen={isSidebarOpen}
  onClose={() => setIsSidebarOpen(false)}
/>
```

with:

```tsx
<AgentTeamPanel
  isOpen={isSidebarOpen}
  onClose={() => setIsSidebarOpen(false)}
  userId={userId}
/>
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/AgentResponse.tsx client/src/components/AgentTeamPanel.tsx client/src/App.tsx
git commit -m "feat: add finance agent team panel"
```

---

### Task 7: Add Operating Summary And Calm Header

**Files:**

- Create: `client/src/components/OperatingSummary.tsx`
- Modify: `client/src/components/Header.tsx`
- Modify: `client/src/App.tsx`

- [ ] **Step 1: Create OperatingSummary**

Create `client/src/components/OperatingSummary.tsx`:

```tsx
type OperatingSummaryItem = {
  label: string;
  value: string;
  note: string;
  status?: "neutral" | "good" | "watch" | "risk";
};

type OperatingSummaryProps = {
  items: OperatingSummaryItem[];
};

const statusClass = {
  neutral: "border-[#dfe5e3] bg-white",
  good: "border-[#cfe2dc] bg-[#f4faf8]",
  watch: "border-[#e3d6bd] bg-[#fbf8f1]",
  risk: "border-[#e7c7c2] bg-[#fbf4f3]",
};

export function OperatingSummary({ items }: OperatingSummaryProps) {
  return (
    <section className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-xl border px-4 py-4 ${statusClass[item.status ?? "neutral"]}`}
        >
          <div className="text-xs font-medium text-[#697571]">{item.label}</div>
          <div className="mt-2 text-2xl font-semibold tracking-normal text-[#172026]">
            {item.value}
          </div>
          <div className="mt-1 text-xs text-[#697571]">{item.note}</div>
        </div>
      ))}
    </section>
  );
}
```

- [ ] **Step 2: Update Header visual language**

Replace the return block in `client/src/components/Header.tsx` with:

```tsx
return (
  <header className="border-b border-[#dfe5e3] bg-white">
    <div className="flex items-center justify-between px-8 py-4">
      <div>
        <div className="text-lg font-semibold text-[#172026]">Finance OS</div>
        <div className="mt-0.5 text-xs text-[#697571]">
          Personal finance operations and agent review
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleUpload}
          className="flex items-center gap-2 rounded-xl border border-[#ccd6d3] bg-white px-4 py-2 text-sm text-[#24302c] transition-colors hover:bg-[#f7f8f8] disabled:opacity-60"
          disabled={isUploading}
        >
          <Upload className="h-4 w-4" />
          {isUploading ? "Uploading" : "Upload Statement"}
        </button>

        <div className="hidden items-center gap-3 border-l border-[#dfe5e3] pl-4 md:flex">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#eef2f1]">
            <User className="h-4 w-4 text-[#53615d]" />
          </div>
          <span className="text-sm text-[#53615d]">Demo profile</span>
        </div>

        <button
          onClick={onToggleSidebar}
          className="flex items-center gap-2 rounded-xl bg-[#172026] px-3 py-2 text-sm text-white transition-colors hover:bg-[#24302c]"
          title={isSidebarOpen ? "Close Agent Team" : "Open Agent Team"}
        >
          {isSidebarOpen ? (
            <PanelRightClose className="h-4 w-4" />
          ) : (
            <PanelRightOpen className="h-4 w-4" />
          )}
          <span>Agent Team</span>
        </button>
      </div>
    </div>
  </header>
);
```

- [ ] **Step 3: Add summary items in App**

In `client/src/App.tsx`, add:

```tsx
import { OperatingSummary } from "./components/OperatingSummary";
```

Add this memo before `return`:

```tsx
const primaryCurrency = summaryByCurrency[0]?.currency ?? "CNY";
const primarySummary = summaryByCurrency[0];
const budgetStatus =
  monthlyIncome > 0 && currentMonthExpense / monthlyIncome > 0.8
    ? "risk"
    : monthlyIncome > 0 && currentMonthExpense / monthlyIncome > 0.5
      ? "watch"
      : "good";
const duplicateCount = txs.filter((t) => t.is_duplicate).length;

const operatingSummaryItems = [
  {
    label: "Cash flow",
    value: primarySummary ? `${primarySummary.net.toLocaleString()} ${primaryCurrency}` : "—",
    note: "Income minus expenses in loaded data",
    status: primarySummary && primarySummary.net >= 0 ? "good" : "watch",
  },
  {
    label: "Expenses",
    value: primarySummary ? `${primarySummary.expense.toLocaleString()} ${primaryCurrency}` : "—",
    note: "Duplicate transactions excluded",
    status: "neutral",
  },
  {
    label: "Budget risk",
    value: monthlyIncome > 0 ? `${Math.round((currentMonthExpense / monthlyIncome) * 100)}%` : "—",
    note: "Current month spend vs income",
    status: budgetStatus,
  },
  {
    label: "Data quality",
    value: `${duplicateCount}`,
    note: "Potential duplicates flagged",
    status: duplicateCount > 0 ? "watch" : "good",
  },
] as const;
```

Replace:

```tsx
<MetricsCards items={summaryByCurrency} />
<IncomeSummary monthlyIncome={monthlyIncome} currentMonthExpense={currentMonthExpense} />
```

with:

```tsx
<OperatingSummary items={operatingSummaryItems} />
<MetricsCards items={summaryByCurrency} />
<IncomeSummary
  monthlyIncome={monthlyIncome}
  currentMonthExpense={currentMonthExpense}
/>
```

- [ ] **Step 4: Update page background**

In `client/src/App.tsx`, change:

```tsx
<div className="min-h-screen bg-gray-50 flex">
```

to:

```tsx
<div className="flex min-h-screen bg-[#f7f8f8]">
```

Change:

```tsx
<main className="flex-1 px-8 py-6">
```

to:

```tsx
<main className="flex-1 px-8 py-6">
```

No further change is needed for `main`; keep the line stable.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/OperatingSummary.tsx client/src/components/Header.tsx client/src/App.tsx
git commit -m "feat: refine finance dashboard shell"
```

---

### Task 8: Final Verification

**Files:**

- Inspect all changed files.
- No new implementation files expected in this task.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd server
python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Start local services**

If the backend dependencies are installed:

```bash
cd server
uvicorn app:app --reload --host 0.0.0.0 --port 18000
```

In a second terminal:

```bash
cd client
npm run dev
```

Expected:

- FastAPI serves `http://localhost:18000/health`.
- Vite serves a local frontend URL.

- [ ] **Step 4: Browser verification**

Open the Vite URL and verify:

- The page uses the Calm Operating System direction.
- Header text is calm and unified.
- Operating summary cards fit at desktop width.
- Agent Team panel opens and closes.
- Agent roster has CFO, Expense, Budget, Audit, and Market.
- Sending a chat message calls `/chat`.
- If `FINANCE_AGENT_RUNTIME=langgraph`, chat still works through the fallback path.
- No visible text overlaps in the header, summary cards, agent cards, chat input, or table area.

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional uncommitted changes remain. If verification generated build artifacts under ignored directories, leave them ignored.

---

## Self-Review

Spec coverage:

- DeepAgents architecture: covered by Tasks 3 and 4.
- LangGraph fallback: covered by Task 3 tests.
- Structured output contract: covered by Task 1 and Task 5.
- Deterministic finance tools: covered by Task 2.
- Finance OS frontend direction: covered by Tasks 6 and 7.
- Verification: covered by Task 8.

Type consistency:

- Backend uses `summary_cards`, `findings`, `actions`, and `audit`.
- Frontend `FinanceAgentData` uses the same property names.
- Runtime returns `reply`, `agent_used`, and `data`, matching `ChatResponse`.

Scope control:

- Authentication, external account writes, full investment advisory, and database schema changes are not included in this phase.
