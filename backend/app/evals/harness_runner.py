"""Hermetic offline evaluation runner and regression gate."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence
from unittest.mock import patch

from pydantic import ValidationError

from app.config.settings import (
    get_settings,
    load_model_profiles,
    load_runtime_profiles,
)
from app.evals.contracts import (
    EvalBaseline,
    EvalBaselineCase,
    EvalBaselineDiff,
    EvalCaseChange,
    EvalGateDecision,
    EvalHarnessReport,
    EvalSuiteReport,
)
from app.evals.suite_adapters import run_offline_suites


PROFILE_NAME = "offline-hermetic-v1"
DEFAULT_BASELINE_PATH = Path(__file__).with_name("baselines") / "offline.json"
DEFAULT_REPORT_PATH = Path("reports/offline-eval-report.json")

OFFLINE_ENVIRONMENT = {
    "APP_ENV": "test",
    "POSTGRES_DSN": "",
    "DATABASE_URL": "",
    "REDIS_URL": "",
    "DEEPSEEK_API_KEY": "",
    "TAVILY_API_KEY": "",
    "SILICONFLOW_API_KEY": "",
    "KNOWLEDGE_RETRIEVAL_MODE": "lexical",
    "MCP_VIBE_ENABLED": "false",
    "STATEMENT_EMAIL_HOST": "",
    "STATEMENT_EMAIL_USERNAME": "",
    "STATEMENT_EMAIL_PASSWORD": "",
}


class OfflineNetworkAccessError(RuntimeError):
    """Raised when an offline eval attempts external or local network access."""


def offline_config_fingerprint() -> str:
    payload = {
        "profile_name": PROFILE_NAME,
        "environment": OFFLINE_ENVIRONMENT,
        "network_policy": "deny",
        "attempts": 1,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
    raise OfflineNetworkAccessError("offline eval profile denies network access")


def clear_runtime_caches() -> None:
    get_settings.cache_clear()
    load_model_profiles.cache_clear()
    load_runtime_profiles.cache_clear()

    from app.runtime.capabilities.health import get_capability_health_service
    from app.services.investment_research_runtime import (
        get_exchange_rate_service,
        get_investment_research_service,
        get_market_data_service,
    )

    get_capability_health_service.cache_clear()
    get_exchange_rate_service.cache_clear()
    get_investment_research_service.cache_clear()
    get_market_data_service.cache_clear()


@contextmanager
def hermetic_offline_environment() -> Iterator[None]:
    """Override local configuration and reject every network attempt."""

    with patch.dict(os.environ, OFFLINE_ENVIRONMENT, clear=False):
        clear_runtime_caches()
        with (
            patch("socket.create_connection", side_effect=_deny_network),
            patch("socket.getaddrinfo", side_effect=_deny_network),
            patch.object(socket.socket, "connect", _deny_network),
            patch.object(socket.socket, "connect_ex", _deny_network),
        ):
            try:
                yield
            finally:
                clear_runtime_caches()


def build_baseline(suites: Sequence[EvalSuiteReport]) -> EvalBaseline:
    cases: dict[str, EvalBaselineCase] = {}
    for suite in suites:
        for case in suite.cases:
            if case.stable_id in cases:
                raise ValueError(f"duplicate eval case ID: {case.stable_id}")
            cases[case.stable_id] = EvalBaselineCase(
                status=case.status,
                severity=case.severity,
            )
    return EvalBaseline(cases=dict(sorted(cases.items())))


def load_baseline(path: Path) -> EvalBaseline:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load eval baseline: {path}") from exc
    try:
        return EvalBaseline.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid eval baseline: {path}") from exc


def compare_baseline(
    baseline: EvalBaseline,
    suites: Sequence[EvalSuiteReport],
) -> EvalBaselineDiff:
    current = {
        case.stable_id: case
        for suite in suites
        for case in suite.cases
    }
    if sum(len(suite.cases) for suite in suites) != len(current):
        raise ValueError("current eval report contains duplicate case IDs")

    new: list[EvalCaseChange] = []
    missing: list[EvalCaseChange] = []
    resolved: list[EvalCaseChange] = []
    regressed: list[EvalCaseChange] = []

    for stable_id, case in sorted(current.items()):
        previous = baseline.cases.get(stable_id)
        if previous is None:
            new.append(
                EvalCaseChange(
                    stable_id=stable_id,
                    current_status=case.status,
                    severity=case.severity,
                    reason_codes=case.reason_codes,
                )
            )
            continue
        change = EvalCaseChange(
            stable_id=stable_id,
            previous_status=previous.status,
            current_status=case.status,
            severity=case.severity,
            reason_codes=case.reason_codes,
        )
        if previous.status in {"pass", "skip"} and case.status in {"fail", "error"}:
            regressed.append(change)
        elif previous.status in {"fail", "error"} and case.status == "pass":
            resolved.append(change)

    for stable_id, previous in sorted(baseline.cases.items()):
        if stable_id not in current and previous.required:
            missing.append(
                EvalCaseChange(
                    stable_id=stable_id,
                    previous_status=previous.status,
                    severity=previous.severity,
                    reason_codes=["required_case_missing"],
                )
            )
    return EvalBaselineDiff(
        new=new,
        missing=missing,
        resolved=resolved,
        regressed=regressed,
    )


def decide_gate(
    suites: Sequence[EvalSuiteReport],
    diff: EvalBaselineDiff,
) -> EvalGateDecision:
    reasons: set[str] = set()
    if diff.missing:
        reasons.add("required_case_missing")
    if any(change.severity in {"critical", "major"} for change in diff.regressed):
        reasons.add("blocking_case_regressed")
    if any(
        case.status in {"fail", "error"}
        and case.severity in {"critical", "major"}
        for suite in suites
        for case in suite.cases
    ):
        reasons.add("blocking_case_failed")
    return EvalGateDecision(passed=not reasons, reason_codes=sorted(reasons))


async def run_offline_harness(baseline: EvalBaseline) -> EvalHarnessReport:
    fingerprint = offline_config_fingerprint()
    with hermetic_offline_environment():
        suites = await run_offline_suites(fingerprint)
    diff = compare_baseline(baseline, suites)
    return EvalHarnessReport(
        config_fingerprint=fingerprint,
        suites=suites,
        baseline_diff=diff,
        gate=decide_gate(suites, diff),
    )


def write_json(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="replace the baseline with the current reviewed case statuses",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.write_baseline:
            fingerprint = offline_config_fingerprint()
            with hermetic_offline_environment():
                suites = asyncio.run(run_offline_suites(fingerprint))
            baseline = build_baseline(suites)
            write_json(args.baseline, baseline)
        else:
            baseline = load_baseline(args.baseline)
        report = asyncio.run(run_offline_harness(baseline))
        write_json(args.output, report)
    except (OfflineNetworkAccessError, ValueError, ValidationError) as exc:
        print(f"offline eval error: {exc}")
        return 2

    totals = {
        "total": sum(suite.total for suite in report.suites),
        "passed": sum(suite.passed for suite in report.suites),
        "failed": sum(suite.failed for suite in report.suites),
        "errors": sum(suite.errors for suite in report.suites),
    }
    print(json.dumps({**totals, "gate_passed": report.gate.passed}, sort_keys=True))
    return 0 if report.gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
