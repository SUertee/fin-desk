"""Deterministic eval run service for sample-backed harness records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.evals.replay import FIXTURES_DIR, HarnessEvalResult, evaluate_run_record, get_eval_case

SAMPLES_FILE = Path(__file__).with_name("samples") / "ci_traces.jsonl"


class EvalRunItem(BaseModel):
    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    request_id: str | None = None
    source: str = "ci_traces"


class EvalRunSummary(BaseModel):
    ok: bool = True
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[EvalRunItem] = Field(default_factory=list)


def run_sample_evals(
    *,
    samples_file: Path = SAMPLES_FILE,
    fixtures_dir: Path = FIXTURES_DIR,
) -> EvalRunSummary:
    results: list[EvalRunItem] = []
    for sample in _load_samples(samples_file):
        case_id = str(sample.get("case_id") or "").strip()
        record = sample.get("record")
        if not case_id or not isinstance(record, dict):
            continue

        case = get_eval_case(case_id, fixtures_dir)
        if case is None:
            results.append(
                EvalRunItem(
                    case_id=case_id,
                    passed=False,
                    failures=[f"Eval case not found: {case_id}"],
                    request_id=record.get("request_id"),
                )
            )
            continue

        evaluation: HarnessEvalResult = evaluate_run_record(record, case)
        results.append(
            EvalRunItem(
                case_id=evaluation.case_id,
                passed=evaluation.passed,
                failures=evaluation.failures,
                request_id=record.get("request_id"),
            )
        )

    passed = sum(1 for item in results if item.passed)
    failed = len(results) - passed
    return EvalRunSummary(
        total=len(results),
        passed=passed,
        failed=failed,
        results=results,
    )


def _load_samples(samples_file: Path) -> list[dict[str, Any]]:
    if not samples_file.exists():
        return []
    samples: list[dict[str, Any]] = []
    for line in samples_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        samples.append(json.loads(line))
    return samples
