"""Typed trace export and CI regression reports for agent harness runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.evals.replay import (
    FIXTURES_DIR,
    EvalCase,
    evaluate_run_record,
    load_eval_cases,
)
from app.models.runtime import AgentRunRecord


TRACE_EXPORT_SCHEMA_VERSION = "agent-trace-export/v1"
TRACE_EXPORT_ITEM_SCHEMA_VERSION = "agent-trace-export-item/v1"
TRACE_EXPORT_REPORT_SCHEMA_VERSION = "agent-trace-export-report/v1"


class TraceExportItem(BaseModel):
    schema_version: str = TRACE_EXPORT_ITEM_SCHEMA_VERSION
    case_id: str | None = None
    record: AgentRunRecord


class TraceExportResult(BaseModel):
    case_id: str | None = None
    request_id: str | None = None
    entrypoint: str | None = None
    user_id: str | None = None
    evaluated: bool = False
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    skipped_reason: str | None = None
    error: str | None = None
    runtime_used: str | None = None
    model_name: str | None = None
    selected_agents: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    output_validations: list[dict[str, Any]] = Field(default_factory=list)
    output_contract: str | None = None
    audit_status: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)


class TraceExportSummary(BaseModel):
    total_records: int = 0
    evaluated_records: int = 0
    passed_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    error_records: int = 0
    ok: bool = False


class TraceExportReport(BaseModel):
    schema_version: str = TRACE_EXPORT_REPORT_SCHEMA_VERSION
    generated_at: str
    source_path: str
    fixtures_dir: str
    summary: TraceExportSummary
    results: list[TraceExportResult] = Field(default_factory=list)


def build_trace_export_item(
    record: AgentRunRecord | dict[str, Any],
    *,
    case_id: str | None = None,
) -> TraceExportItem:
    return TraceExportItem(
        case_id=case_id,
        record=AgentRunRecord.model_validate(record),
    )


def write_trace_export_items(
    items: list[TraceExportItem | AgentRunRecord | dict[str, Any]],
    output_path: Path,
    *,
    jsonl: bool = True,
) -> Path:
    parsed_items = [
        item if isinstance(item, TraceExportItem) else build_trace_export_item(item)
        for item in items
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if jsonl:
        lines = [
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False)
            for item in parsed_items
        ]
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    payload = {
        "schema_version": TRACE_EXPORT_SCHEMA_VERSION,
        "records": [item.model_dump(mode="json") for item in parsed_items],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def load_trace_export_items(source_path: Path) -> list[TraceExportItem]:
    raw_items = _load_raw_items(source_path)
    return [_parse_trace_export_item(raw_item) for raw_item in raw_items]


def evaluate_trace_export_file(
    source_path: Path,
    *,
    fixtures_dir: Path = FIXTURES_DIR,
    fail_on_skipped: bool = True,
) -> TraceExportReport:
    cases = load_eval_cases(fixtures_dir)
    results: list[TraceExportResult] = []

    for raw_item in _load_raw_items(source_path):
        try:
            item = _parse_trace_export_item(raw_item)
        except Exception as exc:
            results.append(
                TraceExportResult(
                    error=f"Invalid trace export item: {type(exc).__name__}: {exc}",
                )
            )
            continue

        results.append(
            _evaluate_trace_export_item(
                item,
                cases=cases,
            )
        )

    summary = _summarize_results(results, fail_on_skipped=fail_on_skipped)
    return TraceExportReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_path=str(source_path),
        fixtures_dir=str(fixtures_dir),
        summary=summary,
        results=results,
    )


def _load_raw_items(source_path: Path) -> list[Any]:
    if source_path.suffix.lower() == ".jsonl":
        return [
            json.loads(line)
            for line in source_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("records", "items", "traces"):
            records = payload.get(key)
            if isinstance(records, list):
                return records
        return [payload]
    raise ValueError("Trace export source must be a JSON object, array, or JSONL file")


def _parse_trace_export_item(raw_item: Any) -> TraceExportItem:
    if not isinstance(raw_item, dict):
        raise ValueError("Trace export item must be a JSON object")

    if "record" in raw_item:
        return TraceExportItem.model_validate(raw_item)

    record_payload = raw_item.get("run_record") or raw_item
    case_id = raw_item.get("case_id") or raw_item.get("eval_case_id")
    return build_trace_export_item(record_payload, case_id=case_id)


def _evaluate_trace_export_item(
    item: TraceExportItem,
    *,
    cases: list[EvalCase],
) -> TraceExportResult:
    result = _base_result(item)
    case, error = _resolve_eval_case(item, cases)
    if error:
        result.skipped_reason = error
        return result

    evaluation = evaluate_run_record(item.record, case)
    result.case_id = case.case_id
    result.evaluated = True
    result.passed = evaluation.passed
    result.failures = evaluation.failures
    return result


def _base_result(item: TraceExportItem) -> TraceExportResult:
    record = item.record
    return TraceExportResult(
        case_id=item.case_id,
        request_id=record.request_id,
        entrypoint=record.entrypoint,
        user_id=record.user_id,
        runtime_used=record.runtime_used,
        model_name=record.model_name,
        selected_agents=record.selected_agents,
        tool_calls=[tool.model_dump(mode="json") for tool in record.tool_calls],
        handoffs=[handoff.model_dump(mode="json") for handoff in record.handoffs],
        output_validations=[
            validation.model_dump(mode="json")
            for validation in record.output_validations
        ],
        output_contract=record.output_contract,
        audit_status=record.audit_status,
        usage=record.usage.model_dump(mode="json"),
        cost=record.cost.model_dump(mode="json"),
    )


def _resolve_eval_case(
    item: TraceExportItem,
    cases: list[EvalCase],
) -> tuple[EvalCase | None, str | None]:
    if item.case_id:
        for case in cases:
            if case.case_id == item.case_id:
                return case, None
        return None, f"Eval case not found: {item.case_id}"

    matches = [
        case
        for case in cases
        if case.entrypoint == item.record.entrypoint
        and case.user_id == item.record.user_id
    ]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return (
            None,
            "No eval case matched "
            f"entrypoint={item.record.entrypoint} user_id={item.record.user_id}",
        )
    case_ids = ", ".join(case.case_id for case in matches)
    return None, f"Multiple eval cases matched this record: {case_ids}"


def _summarize_results(
    results: list[TraceExportResult],
    *,
    fail_on_skipped: bool,
) -> TraceExportSummary:
    evaluated_records = sum(1 for result in results if result.evaluated)
    passed_records = sum(1 for result in results if result.evaluated and result.passed)
    failed_records = sum(1 for result in results if result.evaluated and not result.passed)
    skipped_records = sum(1 for result in results if result.skipped_reason)
    error_records = sum(1 for result in results if result.error)
    ok = (
        bool(results)
        and failed_records == 0
        and error_records == 0
        and (not fail_on_skipped or skipped_records == 0)
    )
    return TraceExportSummary(
        total_records=len(results),
        evaluated_records=evaluated_records,
        passed_records=passed_records,
        failed_records=failed_records,
        skipped_records=skipped_records,
        error_records=error_records,
        ok=ok,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate exported agent run traces against harness fixtures.",
    )
    parser.add_argument("source_path", type=Path)
    parser.add_argument("--fixtures-dir", type=Path, default=FIXTURES_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--allow-skipped",
        action="store_true",
        help="Do not fail when a trace has no matching eval fixture.",
    )
    args = parser.parse_args(argv)

    report = evaluate_trace_export_file(
        args.source_path,
        fixtures_dir=args.fixtures_dir,
        fail_on_skipped=not args.allow_skipped,
    )
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0 if report.summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
