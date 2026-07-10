"""Replay persisted agent run records against harness eval fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from app.evals.replay import (
    FIXTURES_DIR,
    HarnessEvalResult,
    evaluate_run_record,
    get_eval_case,
)
from app.models.runtime import AgentRunRecord
from app.connectors.postgres.run_ledger_store import get_agent_run_record_db


RecordLoader = Callable[[str], dict[str, Any] | None]


class ReplayRunReport(BaseModel):
    request_id: str
    record_found: bool
    case_id: str | None = None
    record_summary: dict[str, Any] | None = None
    evaluation: HarnessEvalResult | None = None
    error: str | None = None


def _record_summary(record: AgentRunRecord) -> dict[str, Any]:
    return {
        "request_id": record.request_id,
        "user_id": record.user_id,
        "entrypoint": record.entrypoint,
        "runtime_used": record.runtime_used,
        "model_name": record.model_name,
        "selected_agents": record.selected_agents,
        "tool_calls": [tool.model_dump(mode="json") for tool in record.tool_calls],
        "handoffs": [handoff.model_dump(mode="json") for handoff in record.handoffs],
        "output_validations": [
            validation.model_dump(mode="json")
            for validation in record.output_validations
        ],
        "output_contract": record.output_contract,
        "audit_status": record.audit_status,
        "usage": record.usage.model_dump(mode="json"),
        "cost": record.cost.model_dump(mode="json"),
        "error_type": record.error_type,
    }


def replay_agent_run(
    request_id: str,
    *,
    case_id: str | None = None,
    fixtures_dir: Path = FIXTURES_DIR,
    record_loader: RecordLoader | None = None,
) -> ReplayRunReport:
    loader = record_loader or get_agent_run_record_db
    raw_record = loader(request_id)
    if raw_record is None:
        return ReplayRunReport(
            request_id=request_id,
            record_found=False,
            case_id=case_id,
            error="Agent run record not found",
        )

    record = AgentRunRecord.model_validate(raw_record)
    evaluation = None
    if case_id:
        case = get_eval_case(case_id, fixtures_dir)
        if case is None:
            return ReplayRunReport(
                request_id=request_id,
                record_found=True,
                case_id=case_id,
                record_summary=_record_summary(record),
                error=f"Eval case not found: {case_id}",
            )
        evaluation = evaluate_run_record(record, case)

    return ReplayRunReport(
        request_id=request_id,
        record_found=True,
        case_id=case_id,
        record_summary=_record_summary(record),
        evaluation=evaluation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a persisted agent run record against an eval fixture.",
    )
    parser.add_argument("request_id")
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--fixtures-dir", type=Path, default=FIXTURES_DIR)
    args = parser.parse_args(argv)

    report = replay_agent_run(
        args.request_id,
        case_id=args.case_id,
        fixtures_dir=args.fixtures_dir,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if not report.record_found or report.error:
        return 1
    if report.evaluation and not report.evaluation.passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
