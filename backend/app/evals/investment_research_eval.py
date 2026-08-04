"""Deterministic investment-research specialist and audit regression eval."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.agents.specialists import auditor, investment_research
from app.agents.specialists.contracts import SpecialistInput
from app.runtime.orchestration.factory import build_finance_runtime
from app.runtime.policy.runtime_policy import evaluate_runtime_policy


FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "investment_research"
    / "cases.json"
)


class InvestmentResearchEvalCase(BaseModel):
    case_id: str
    message: str
    research: dict
    expected_specialist_fragments: list[str] = Field(default_factory=list)
    expected_audit_fragments: list[str] = Field(default_factory=list)
    forbidden_output_fragments: list[str] = Field(default_factory=list)


class InvestmentResearchEvalResult(BaseModel):
    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


class InvestmentResearchEvalReport(BaseModel):
    total: int
    passed: int
    results: list[InvestmentResearchEvalResult]


def load_investment_research_cases(
    path: Path = FIXTURE,
) -> list[InvestmentResearchEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [InvestmentResearchEvalCase.model_validate(item) for item in payload["cases"]]


def evaluate_investment_research_case(
    case: InvestmentResearchEvalCase,
) -> InvestmentResearchEvalResult:
    failures: list[str] = []
    catalog = build_finance_runtime(llm_client=None).capability_catalog
    policy = evaluate_runtime_policy(["investment.research_review"], catalog)
    if "investment_research" not in policy.required_specialists:
        failures.append("investment_research specialist was not selected")
    if not policy.audit_required:
        failures.append("investment research did not require audit")

    evidence = {"investment_research": case.research}
    specialist = investment_research.run(
        SpecialistInput(task=case.message, evidence=evidence, policy=policy.model_dump())
    )
    audit = auditor.run(
        SpecialistInput(
            task=case.message,
            evidence=evidence,
            policy=policy.model_dump(),
            prior_outputs={"investment_research": specialist},
        )
    )
    specialist_text = json.dumps(
        specialist.model_dump(mode="json"), ensure_ascii=False
    ).lower()
    audit_text = json.dumps(audit.model_dump(mode="json"), ensure_ascii=False).lower()
    combined = f"{specialist_text}\n{audit_text}"

    for fragment in case.expected_specialist_fragments:
        if fragment.lower() not in specialist_text:
            failures.append(f"missing specialist fragment: {fragment}")
    for fragment in case.expected_audit_fragments:
        if fragment.lower() not in audit_text:
            failures.append(f"missing audit fragment: {fragment}")
    for fragment in case.forbidden_output_fragments:
        if fragment.lower() in combined:
            failures.append(f"forbidden output fragment: {fragment}")
    if case.research.get("trade_actions_allowed") is not False:
        failures.append("fixture did not preserve trade_actions_allowed=false")

    return InvestmentResearchEvalResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
    )


def run_investment_research_eval() -> InvestmentResearchEvalReport:
    results = [
        evaluate_investment_research_case(case)
        for case in load_investment_research_cases()
    ]
    return InvestmentResearchEvalReport(
        total=len(results),
        passed=sum(item.passed for item in results),
        results=results,
    )


if __name__ == "__main__":
    report = run_investment_research_eval()
    print(report.model_dump_json(indent=2))
    raise SystemExit(0 if report.passed == report.total else 1)
