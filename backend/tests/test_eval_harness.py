from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.settings import get_settings
from app.evals.contracts import (
    OFFLINE_TRIAL_LIMITS,
    EvalBaseline,
    EvalBaselineCase,
    EvalCaseResult,
    EvalGraderResult,
    EvalSuiteReport,
    EvalTask,
    EvalTrial,
)
from app.evals.harness_runner import (
    DEFAULT_BASELINE_PATH,
    OfflineNetworkAccessError,
    compare_baseline,
    decide_gate,
    hermetic_offline_environment,
    load_baseline,
    main,
    offline_config_fingerprint,
    run_offline_harness,
)


def _suite(
    case_id: str,
    *,
    status: str = "pass",
    severity: str = "major",
) -> EvalSuiteReport:
    task_id = f"synthetic:{case_id}"
    reason_codes = [] if status == "pass" else ["synthetic_failure"]
    case = EvalCaseResult(
        suite_id="synthetic",
        case_id=case_id,
        status=status,
        severity=severity,
        reason_codes=reason_codes,
    )
    return EvalSuiteReport(
        suite_id="synthetic",
        total=1,
        passed=int(status == "pass"),
        failed=int(status == "fail"),
        errors=int(status == "error"),
        skipped=int(status == "skip"),
        tasks=[
            EvalTask(
                task_id=task_id,
                suite_id="synthetic",
                fixture_ref="tests/fixtures/synthetic.json",
                expected_outcome="pass",
                grader_ids=["synthetic.grader"],
                severity=severity,
                limits=OFFLINE_TRIAL_LIMITS,
            )
        ],
        trials=[
            EvalTrial(
                trial_id=f"{task_id}:trial-1",
                task_id=task_id,
                mode="offline",
                profile_name="offline-hermetic-v1",
                config_fingerprint="a" * 12,
                status=status,
            )
        ],
        graders=[
            EvalGraderResult(
                grader_id="synthetic.grader",
                dimension="correctness",
                target="outcome",
                status=status,
                severity=severity,
                reason_code=(
                    "synthetic_passed" if status == "pass" else "synthetic_failure"
                ),
            )
        ],
        cases=[case],
    )


def test_eval_contracts_reject_unknown_fields():
    with pytest.raises(ValidationError):
        EvalBaseline.model_validate(
            {"schema_version": "1", "cases": {}, "unexpected": True}
        )


def test_hermetic_environment_overrides_and_restores_local_state(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local-hostile")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://live.example/db")
    monkeypatch.setenv("REDIS_URL", "redis://live.example/0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-live-key")
    get_settings.cache_clear()

    with hermetic_offline_environment():
        settings = get_settings()
        assert settings.environment == "test"
        assert settings.database.dsn == ""
        assert settings.redis.url == ""
        assert not settings.mcp.enabled
        with pytest.raises(OfflineNetworkAccessError):
            socket.create_connection(("example.com", 443))

    assert get_settings().environment == "local-hostile"
    assert get_settings().database.dsn == "postgresql://live.example/db"


def test_baseline_diff_and_gate_are_severity_aware():
    baseline = EvalBaseline(
        cases={
            "synthetic:blocking": EvalBaselineCase(
                status="pass", severity="major"
            ),
            "synthetic:required": EvalBaselineCase(
                status="pass", severity="critical"
            ),
        }
    )
    blocking_suite = _suite("blocking", status="fail", severity="major")
    diff = compare_baseline(baseline, [blocking_suite])

    assert [item.stable_id for item in diff.regressed] == ["synthetic:blocking"]
    assert [item.stable_id for item in diff.missing] == ["synthetic:required"]
    assert not decide_gate([blocking_suite], diff).passed

    advisory_baseline = EvalBaseline(
        cases={
            "synthetic:advisory": EvalBaselineCase(
                status="pass", severity="advisory"
            )
        }
    )
    advisory_suite = _suite("advisory", status="fail", severity="advisory")
    advisory_diff = compare_baseline(advisory_baseline, [advisory_suite])

    assert len(advisory_diff.regressed) == 1
    assert decide_gate([advisory_suite], advisory_diff).passed


def test_baseline_diff_reports_new_and_resolved_cases():
    baseline = EvalBaseline(
        cases={
            "synthetic:fixed": EvalBaselineCase(status="fail", severity="major")
        }
    )
    diff = compare_baseline(
        baseline,
        [_suite("fixed"), _suite("new-case")],
    )

    assert [item.stable_id for item in diff.resolved] == ["synthetic:fixed"]
    assert [item.stable_id for item in diff.new] == ["synthetic:new-case"]


def test_invalid_baseline_is_rejected(tmp_path: Path, monkeypatch):
    baseline_path = tmp_path / "invalid.json"
    baseline_path.write_text('{"schema_version":"2"}', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid eval baseline"):
        load_baseline(baseline_path)

    monkeypatch.setattr(
        sys,
        "argv",
        ["harness_runner", "--baseline", str(baseline_path)],
    )
    assert main() == 2


def test_offline_harness_is_complete_deterministic_and_private(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://private.example/finance")
    monkeypatch.setenv("REDIS_URL", "redis://private.example/0")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret-key")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "embedding-secret-key")
    monkeypatch.setenv("MCP_VIBE_ENABLED", "true")
    baseline = load_baseline(DEFAULT_BASELINE_PATH)

    first = asyncio.run(run_offline_harness(baseline))
    second = asyncio.run(run_offline_harness(baseline))

    assert first == second
    assert first.config_fingerprint == offline_config_fingerprint()
    assert sum(suite.total for suite in first.suites) == 79
    assert sum(suite.passed for suite in first.suites) == 79
    assert first.gate.passed
    serialized = json.dumps(first.model_dump(mode="json"), ensure_ascii=False)
    for forbidden in (
        "super-secret-key",
        "embedding-secret-key",
        "private.example",
        "chat_history",
        "system_prompt",
        "transaction_description",
    ):
        assert forbidden not in serialized
