from datetime import date

from app.evals.knowledge_retrieval_eval import (
    KnowledgeRetrievalEvalCase,
    format_report,
    load_knowledge_retrieval_cases,
    run_knowledge_retrieval_eval,
)
from app.knowledge import KnowledgeRetrievalResult, build_knowledge_evidence
from app.knowledge.markdown_ingestion import DEFAULT_CORPUS, parse_markdown_file


def _artifact(document_name: str = "au-emergency-fund.md", *, stale: bool = False):
    bundle = parse_markdown_file(DEFAULT_CORPUS / document_name)
    return build_knowledge_evidence(
        bundle.document,
        bundle.chunks[0],
        retrieval_method="lexical",
        score=5.0,
        as_of=date(2028, 1, 1) if stale else date(2026, 7, 21),
    )


class MappingRetriever:
    def __init__(self, results):
        self.results = results

    def retrieve(self, query):
        return self.results[query.text]


def test_fixture_has_twenty_unique_cases_across_required_categories():
    cases = load_knowledge_retrieval_cases()

    assert len(cases) == 20
    assert len({case.case_id for case in cases}) == 20
    assert {case.category for case in cases} == {
        "relevance",
        "filter",
        "freshness",
        "no_match",
    }
    assert any(any(ord(char) > 127 for char in case.query) for case in cases)
    assert any(case.query.isascii() for case in cases)


def test_eval_reports_recall_citations_constraints_and_no_match():
    artifact = _artifact()
    stale_artifact = _artifact(stale=True)
    cases = [
        KnowledgeRetrievalEvalCase(
            case_id="relevant",
            category="relevance",
            query="relevant query",
            expected_match=True,
            acceptable_document_ids=[artifact.document_id],
        ),
        KnowledgeRetrievalEvalCase(
            case_id="filtered",
            category="filter",
            query="filtered query",
            filters={"jurisdictions": ["AU"]},
            expected_match=True,
            acceptable_document_ids=[artifact.document_id],
        ),
        KnowledgeRetrievalEvalCase(
            case_id="stale",
            category="freshness",
            query="stale query",
            as_of=date(2028, 1, 1),
            filters={"include_stale": True},
            expected_match=True,
            acceptable_document_ids=[stale_artifact.document_id],
            expected_freshness="stale",
        ),
        KnowledgeRetrievalEvalCase(
            case_id="honest",
            category="no_match",
            query="unsupported query",
            expected_match=False,
        ),
    ]
    retriever = MappingRetriever(
        {
            "relevant query": KnowledgeRetrievalResult(
                query="relevant query", match_status="matched", artifacts=[artifact]
            ),
            "filtered query": KnowledgeRetrievalResult(
                query="filtered query", match_status="matched", artifacts=[artifact]
            ),
            "stale query": KnowledgeRetrievalResult(
                query="stale query", match_status="matched", artifacts=[stale_artifact]
            ),
            "unsupported query": KnowledgeRetrievalResult(
                query="unsupported query", match_status="no_match", artifacts=[]
            ),
        }
    )

    report = run_knowledge_retrieval_eval(retriever, cases)

    assert report.passed == report.total == 4
    assert report.recall_at_k == 1.0
    assert report.citation_integrity == 1.0
    assert report.constraint_accuracy == 1.0
    assert report.no_match_accuracy == 1.0


def test_eval_exposes_relevance_and_no_match_failures():
    artifact = _artifact()
    cases = [
        KnowledgeRetrievalEvalCase(
            case_id="miss",
            category="relevance",
            query="missing relevant source",
            expected_match=True,
            acceptable_document_ids=["us-asset-allocation"],
        ),
        KnowledgeRetrievalEvalCase(
            case_id="fabricated",
            category="no_match",
            query="must be empty",
            expected_match=False,
        ),
    ]
    retriever = MappingRetriever(
        {
            "missing relevant source": KnowledgeRetrievalResult(
                query="missing relevant source",
                match_status="matched",
                artifacts=[artifact],
            ),
            "must be empty": KnowledgeRetrievalResult(
                query="must be empty", match_status="matched", artifacts=[artifact]
            ),
        }
    )

    report = run_knowledge_retrieval_eval(retriever, cases)
    output = format_report(report)

    assert report.passed == 0
    assert report.recall_at_k == 0.0
    assert report.no_match_accuracy == 0.0
    assert "miss:" in output
    assert "fabricated:" in output


def test_eval_rejects_malformed_citation_even_when_relevance_matches():
    artifact = _artifact()
    malformed = artifact.model_copy(update={"citation_id": "knowledge:wrong-chunk"})
    case = KnowledgeRetrievalEvalCase(
        case_id="bad-citation",
        category="relevance",
        query="emergency fund",
        expected_match=True,
        acceptable_document_ids=[artifact.document_id],
    )
    retriever = MappingRetriever(
        {
            "emergency fund": KnowledgeRetrievalResult(
                query="emergency fund", match_status="matched", artifacts=[malformed]
            )
        }
    )

    first = run_knowledge_retrieval_eval(retriever, [case])
    second = run_knowledge_retrieval_eval(retriever, [case])

    assert first == second
    assert first.recall_at_k == 1.0
    assert first.citation_integrity == 0.0
    assert first.passed == 0
    assert "invalid citation identity" in first.results[0].failures[0]
