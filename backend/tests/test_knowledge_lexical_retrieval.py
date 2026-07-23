from contextlib import contextmanager
from datetime import date

import pytest
from pydantic import ValidationError

from app.connectors.postgres import knowledge_store
from app.knowledge import (
    KnowledgeFilters,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    build_knowledge_evidence,
)
from app.knowledge.markdown_ingestion import DEFAULT_CORPUS, parse_markdown_file
from app.knowledge.retrieval import lexical_terms
from app.models.runtime import RuntimePolicyResult
from app.runtime.execution import build_execution_plan
from app.runtime.orchestration.factory import build_finance_runtime
from app.runtime.policy.runtime_policy import evaluate_runtime_policy
from tests.cfo_decision_fakes import execute


def _artifact(*, as_of: date = date(2026, 7, 21)):
    bundle = parse_markdown_file(DEFAULT_CORPUS / "au-emergency-fund.md")
    return build_knowledge_evidence(
        bundle.document,
        bundle.chunks[1],
        retrieval_method="lexical",
        score=6.0,
        as_of=as_of,
    )


def _row(*, score: float = 6.0):
    bundle = parse_markdown_file(DEFAULT_CORPUS / "au-emergency-fund.md")
    document = bundle.document
    chunk = bundle.chunks[1]
    return (
        document.document_id,
        document.title,
        document.source_url,
        document.source_authority,
        document.source_type,
        document.jurisdiction,
        document.language,
        document.source_updated_at,
        document.reviewed_at,
        document.review_after,
        document.tags,
        document.content_hash,
        chunk.chunk_id,
        chunk.ordinal,
        chunk.heading,
        chunk.content,
        chunk.content_hash,
        score,
    )


class RetrievalCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statement = ""
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params):
        self.statement = statement
        self.params = params

    def fetchall(self):
        return self.rows


class RetrievalConnection:
    def __init__(self, rows):
        self.cursor_instance = RetrievalCursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_query_contract_is_strict_and_bounded():
    with pytest.raises(ValidationError):
        KnowledgeQuery(text="policy", top_k=11)
    with pytest.raises(ValidationError):
        KnowledgeQuery.model_validate({"text": "policy", "sql": "DROP TABLE"})


def test_lexical_terms_are_bounded_and_bilingual():
    english, cjk = lexical_terms("How should I build an emergency fund 应急基金存多少")

    assert "emergency" in english
    assert "fund" in english
    assert "应急" in cjk
    assert "基金" in cjk
    assert len(cjk) <= 12


def test_postgres_retriever_projects_typed_evidence_and_bound_filters(monkeypatch):
    connection = RetrievalConnection([_row()])

    @contextmanager
    def fake_conn():
        yield connection

    monkeypatch.setattr(knowledge_store, "get_conn", fake_conn)
    query = KnowledgeQuery(
        text="应急基金怎么准备",
        as_of=date(2026, 7, 21),
        filters=KnowledgeFilters(
            jurisdictions=["AU"],
            source_types=["official_guidance"],
            tags=["emergency fund"],
        ),
    )

    result = knowledge_store.retrieve_knowledge_lexical_db(query)

    assert result.match_status == "matched"
    assert result.artifacts[0].document_id == "au-emergency-fund"
    assert result.artifacts[0].freshness == "current"
    assert "ANY(%s::text[])" in connection.cursor_instance.statement
    assert "应急基金怎么准备" not in connection.cursor_instance.statement
    assert connection.cursor_instance.params[-1] == 4


def test_postgres_retriever_returns_explicit_no_match(monkeypatch):
    connection = RetrievalConnection([])

    @contextmanager
    def fake_conn():
        yield connection

    monkeypatch.setattr(knowledge_store, "get_conn", fake_conn)

    result = knowledge_store.retrieve_knowledge_lexical_db(
        KnowledgeQuery(text="火星房产税规则")
    )

    assert result == KnowledgeRetrievalResult(
        query="火星房产税规则", match_status="no_match", artifacts=[]
    )


def test_planner_executes_only_requested_knowledge_ledger_or_market_capabilities():
    base_policy = RuntimePolicyResult(
        complexity="moderate",
        risk_level="low",
        required_specialists=["budget_coach"],
        audit_required=True,
        max_tool_calls=6,
    )
    runtime = build_finance_runtime()
    knowledge = build_execution_plan(
        ["knowledge.lexical_search"], base_policy, runtime.capability_catalog
    )
    ledger = build_execution_plan(
        ["finance.query_transactions"], base_policy, runtime.capability_catalog
    )
    market = build_execution_plan(
        ["market.context_review"],
        base_policy.model_copy(update={"required_specialists": ["market_context"]}),
        runtime.capability_catalog,
    )

    assert "knowledge.lexical_search" in knowledge.tool_capability_ids
    assert "knowledge.lexical_search" not in ledger.tool_capability_ids
    assert "knowledge.lexical_search" not in market.tool_capability_ids


def test_emergency_fund_is_budget_guidance_not_investment_research():
    runtime = build_finance_runtime()
    policy = evaluate_runtime_policy(
        ["finance.budget_coaching", "knowledge.lexical_search"],
        runtime.capability_catalog,
    )

    assert "budget_coach" in policy.required_specialists
    assert "investment_research" not in policy.required_specialists


@pytest.mark.asyncio
async def test_runtime_uses_bounded_knowledge_and_records_citations(monkeypatch):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime as runtime_module
    from app.runtime.orchestration.factory import build_finance_runtime

    class FakeRetriever:
        def __init__(self):
            self.queries = []

        def retrieve(self, query):
            self.queries.append(query)
            artifact = _artifact()
            return KnowledgeRetrievalResult(
                query=query.text,
                match_status="matched",
                artifacts=[artifact],
            )

    records = []
    retriever = FakeRetriever()
    monkeypatch.setattr(
        finance_toolset,
        "list_latest_quality_reports_db",
        lambda _user: [],
    )
    monkeypatch.setattr(runtime_module, "write_session_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        runtime_module,
        "save_agent_run_record_db",
        lambda record: records.append(record) or True,
    )
    runtime = build_finance_runtime(
        knowledge_retriever=retriever,
        decision_engine=execute(
            "knowledge.lexical_search", "finance.budget_coaching"
        ),
        llm_client=None,
    )

    result = await runtime.handle(
        user_id="demo",
        message="我的应急基金应该存多少",
        profile={"name": "Demo", "preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert retriever.queries[0].text == "我的应急基金应该存多少"
    assert "MoneySmart" in result["reply"]
    assert records[0].policy["knowledge_evidence"][0]["source_url"].startswith(
        "https://moneysmart.gov.au/"
    )
    assert any(call.name == "search_knowledge" for call in records[0].tool_calls)


@pytest.mark.asyncio
async def test_runtime_states_no_match_without_fabricating_guidance(monkeypatch):
    from app.runtime.execution import finance_toolset
    from app.runtime.orchestration import finance_runtime as runtime_module
    from app.runtime.orchestration.factory import build_finance_runtime

    class NoMatchRetriever:
        def retrieve(self, query):
            return KnowledgeRetrievalResult(
                query=query.text, match_status="no_match", artifacts=[]
            )

    monkeypatch.setattr(
        finance_toolset,
        "list_latest_quality_reports_db",
        lambda _user: [],
    )
    monkeypatch.setattr(runtime_module, "write_session_context", lambda **_kwargs: None)
    monkeypatch.setattr(runtime_module, "save_agent_run_record_db", lambda _record: True)
    runtime = build_finance_runtime(
        knowledge_retriever=NoMatchRetriever(),
        decision_engine=execute("knowledge.lexical_search"),
        llm_client=None,
    )

    result = await runtime.handle(
        user_id="demo",
        message="我的预算怎么考虑火星房产税",
        profile={"preferences": {"preferred_language": "zh"}},
        transactions=[],
        monthly_totals=[],
        chat_history=[],
    )

    assert "没有直接匹配" in result["reply"]
    assert all(item["agent"] != "cfo" for item in result["data"]["findings"])


def test_office_evidence_projects_reviewed_source_without_ranking_details(monkeypatch):
    from app.routes import office as office_route

    source = _artifact().model_dump(mode="json")
    source.pop("score")
    monkeypatch.setattr(
        office_route,
        "get_agent_run_record_db",
        lambda _request_id: {
            "request_id": "req-knowledge",
            "user_id": "demo",
            "policy": {"knowledge_evidence": [source]},
            "tool_calls": [{"name": "search_knowledge", "status": "called"}],
            "handoffs": [],
            "input_summary": {},
        },
    )
    monkeypatch.setattr(office_route, "list_latest_quality_reports_db", lambda _user: [])

    projection = office_route.get_evidence("req-knowledge")

    assert len(projection.cited_sources) == 1
    assert "ASIC MoneySmart" in projection.cited_sources[0]
    assert "https://moneysmart.gov.au/" in projection.cited_sources[0]
    assert "score" not in projection.model_dump_json()
