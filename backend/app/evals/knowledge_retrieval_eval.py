"""Deterministic evaluation for reviewed knowledge retrieval."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.knowledge import (
    KnowledgeFilters,
    KnowledgeQuery,
    KnowledgeRetriever,
)
from app.knowledge.contracts import KnowledgeFreshness

KNOWLEDGE_RETRIEVAL_FIXTURES = (
    Path(__file__).with_name("fixtures") / "knowledge_retrieval" / "cases.json"
)
KnowledgeEvalCategory = Literal["relevance", "filter", "freshness", "no_match"]


class KnowledgeRetrievalEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=3, max_length=80)
    category: KnowledgeEvalCategory
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=4, ge=1, le=10)
    as_of: date = date(2026, 7, 21)
    filters: KnowledgeFilters = Field(default_factory=KnowledgeFilters)
    expected_match: bool
    acceptable_document_ids: list[str] = Field(default_factory=list, max_length=6)
    expected_freshness: KnowledgeFreshness | None = None

    @model_validator(mode="after")
    def validate_expectation(self) -> "KnowledgeRetrievalEvalCase":
        if self.expected_match and not self.acceptable_document_ids:
            raise ValueError("matched cases require acceptable document IDs")
        if not self.expected_match and self.acceptable_document_ids:
            raise ValueError("no-match cases cannot name acceptable document IDs")
        return self


class KnowledgeRetrievalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: KnowledgeEvalCategory
    passed: bool
    recall_hit: bool | None
    citation_count: int = Field(ge=0)
    citation_valid_count: int = Field(ge=0)
    constraint_passed: bool
    no_match_honest: bool | None
    returned_document_ids: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class KnowledgeRetrievalEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    passed: int
    matched_cases: int
    recall_hits: int
    citation_count: int
    citation_valid_count: int
    constraint_cases: int
    constraint_passed: int
    no_match_cases: int
    no_match_passed: int
    results: list[KnowledgeRetrievalCaseResult]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def recall_at_k(self) -> float:
        return self.recall_hits / self.matched_cases if self.matched_cases else 0.0

    @property
    def citation_integrity(self) -> float:
        if not self.citation_count:
            return 1.0
        return self.citation_valid_count / self.citation_count

    @property
    def constraint_accuracy(self) -> float:
        if not self.constraint_cases:
            return 1.0
        return self.constraint_passed / self.constraint_cases

    @property
    def no_match_accuracy(self) -> float:
        if not self.no_match_cases:
            return 1.0
        return self.no_match_passed / self.no_match_cases

    def failures(self) -> list[KnowledgeRetrievalCaseResult]:
        return [result for result in self.results if not result.passed]


def load_knowledge_retrieval_cases(
    path: Path = KNOWLEDGE_RETRIEVAL_FIXTURES,
) -> list[KnowledgeRetrievalEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [KnowledgeRetrievalEvalCase.model_validate(item) for item in payload["cases"]]


def evaluate_knowledge_retrieval_case(
    retriever: KnowledgeRetriever,
    case: KnowledgeRetrievalEvalCase,
) -> KnowledgeRetrievalCaseResult:
    result = retriever.retrieve(
        KnowledgeQuery(
            text=case.query,
            top_k=case.top_k,
            as_of=case.as_of,
            filters=case.filters,
        )
    )
    failures: list[str] = []
    returned_ids = [artifact.document_id for artifact in result.artifacts]

    recall_hit: bool | None = None
    no_match_honest: bool | None = None
    if case.expected_match:
        recall_hit = any(
            document_id in case.acceptable_document_ids for document_id in returned_ids
        )
        if result.match_status != "matched" or not recall_hit:
            failures.append(
                "expected one of "
                f"{case.acceptable_document_ids!r}, returned {returned_ids!r}"
            )
    else:
        no_match_honest = result.match_status == "no_match" and not result.artifacts
        if not no_match_honest:
            failures.append(f"expected no_match, returned {returned_ids!r}")

    citation_valid_count = 0
    for artifact in result.artifacts:
        citation_failures: list[str] = []
        if artifact.citation_id != f"knowledge:{artifact.chunk_id}":
            citation_failures.append("citation identity")
        if not artifact.source_authority.strip():
            citation_failures.append("source authority")
        if not artifact.source_url.startswith(("https://", "http://")):
            citation_failures.append("source URL")
        if artifact.review_after < artifact.reviewed_at:
            citation_failures.append("review window")
        if citation_failures:
            failures.append(
                f"{artifact.chunk_id}: invalid {', '.join(citation_failures)}"
            )
        else:
            citation_valid_count += 1

    constraint_passed = True
    if case.filters.jurisdictions and any(
        artifact.jurisdiction.lower() not in case.filters.jurisdictions
        for artifact in result.artifacts
    ):
        constraint_passed = False
        failures.append("returned artifact violates jurisdiction filter")
    if case.expected_freshness and any(
        artifact.freshness != case.expected_freshness for artifact in result.artifacts
    ):
        constraint_passed = False
        failures.append(
            f"expected freshness {case.expected_freshness}, got "
            f"{[artifact.freshness for artifact in result.artifacts]!r}"
        )

    return KnowledgeRetrievalCaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=not failures,
        recall_hit=recall_hit,
        citation_count=len(result.artifacts),
        citation_valid_count=citation_valid_count,
        constraint_passed=constraint_passed,
        no_match_honest=no_match_honest,
        returned_document_ids=returned_ids,
        failures=failures,
    )


def run_knowledge_retrieval_eval(
    retriever: KnowledgeRetriever,
    cases: list[KnowledgeRetrievalEvalCase] | None = None,
) -> KnowledgeRetrievalEvalReport:
    selected = cases if cases is not None else load_knowledge_retrieval_cases()
    results = [evaluate_knowledge_retrieval_case(retriever, case) for case in selected]
    matched_results = [result for result in results if result.recall_hit is not None]
    constraint_results = [
        result for result in results if result.category in {"filter", "freshness"}
    ]
    no_match_results = [
        result for result in results if result.no_match_honest is not None
    ]
    return KnowledgeRetrievalEvalReport(
        total=len(results),
        passed=sum(result.passed for result in results),
        matched_cases=len(matched_results),
        recall_hits=sum(result.recall_hit is True for result in matched_results),
        citation_count=sum(result.citation_count for result in results),
        citation_valid_count=sum(result.citation_valid_count for result in results),
        constraint_cases=len(constraint_results),
        constraint_passed=sum(result.constraint_passed for result in constraint_results),
        no_match_cases=len(no_match_results),
        no_match_passed=sum(
            result.no_match_honest is True for result in no_match_results
        ),
        results=results,
    )


def format_report(report: KnowledgeRetrievalEvalReport) -> str:
    lines = [
        f"knowledge retrieval eval: {report.passed}/{report.total} ({report.accuracy:.0%})",
        f"  Recall@k          {report.recall_hits}/{report.matched_cases} ({report.recall_at_k:.0%})",
        "  citation integrity "
        f"{report.citation_valid_count}/{report.citation_count} ({report.citation_integrity:.0%})",
        "  filter/freshness  "
        f"{report.constraint_passed}/{report.constraint_cases} ({report.constraint_accuracy:.0%})",
        "  no-match honesty  "
        f"{report.no_match_passed}/{report.no_match_cases} ({report.no_match_accuracy:.0%})",
    ]
    for result in report.failures():
        lines.append(f"  - {result.case_id}: {'; '.join(result.failures)}")
    return "\n".join(lines)


def _main() -> int:
    from dotenv import load_dotenv

    from app.connectors.postgres.knowledge_store import (
        PostgresLexicalKnowledgeRetriever,
    )

    load_dotenv()
    report = run_knowledge_retrieval_eval(PostgresLexicalKnowledgeRetriever())
    print(format_report(report))
    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(_main())
