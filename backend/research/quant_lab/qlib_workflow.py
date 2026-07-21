"""Qlib workflow planning and bounded process execution.

This module deliberately does not import qlib. The dedicated research environment
owns the qrun executable and all heavy model dependencies.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from research.quant_lab.contracts import QuantExperimentSpec, QlibWorkflowRun


def build_qlib_workflow_config(
    spec: QuantExperimentSpec,
    *,
    provider_uri: str,
    market_name: str = "all",
) -> dict:
    """Build a transparent Qlib LightGBM ranking workflow configuration."""

    split = spec.split
    label = (
        f"Rank(Ref($close, -{spec.horizon_days + 1}) "
        "/ Ref($close, -1) - 1)"
    )
    handler_kwargs = {
        "start_time": split.train.start.isoformat(),
        "end_time": split.test.end.isoformat(),
        "fit_start_time": split.train.start.isoformat(),
        "fit_end_time": split.train.end.isoformat(),
        "instruments": market_name,
        "label": [[label], ["LABEL0"]],
    }
    return {
        "qlib_init": {"provider_uri": provider_uri, "region": "us"},
        "market": market_name,
        "benchmark": spec.benchmark,
        "task": {
            "model": {
                "class": "LGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {
                    "loss": "mse",
                    "colsample_bytree": 0.8879,
                    "learning_rate": 0.0421,
                    "subsample": 0.8789,
                    "lambda_l1": 205.6999,
                    "lambda_l2": 580.9768,
                    "max_depth": 8,
                    "num_leaves": 210,
                    "num_threads": 4,
                    "seed": spec.seed,
                },
            },
            "dataset": {
                "class": "DatasetH",
                "module_path": "qlib.data.dataset",
                "kwargs": {
                    "handler": {
                        "class": "Alpha158",
                        "module_path": "qlib.contrib.data.handler",
                        "kwargs": handler_kwargs,
                    },
                    "segments": {
                        "train": [
                            split.train.start.isoformat(),
                            split.train.end.isoformat(),
                        ],
                        "valid": [
                            split.validation.start.isoformat(),
                            split.validation.end.isoformat(),
                        ],
                        "test": [
                            split.test.start.isoformat(),
                            split.test.end.isoformat(),
                        ],
                    },
                },
            },
            "record": [
                {
                    "class": "SignalRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {},
                },
                {
                    "class": "SigAnaRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {"ana_long_short": False, "ann_scaler": 252},
                },
                {
                    "class": "PortAnaRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {
                        "config": {
                            "strategy": {
                                "class": "TopkDropoutStrategy",
                                "module_path": "qlib.contrib.strategy.signal_strategy",
                                "kwargs": {
                                    "topk": spec.top_k,
                                    "n_drop": max(1, spec.top_k // 5),
                                },
                            },
                            "executor": {
                                "class": "SimulatorExecutor",
                                "module_path": "qlib.backtest.executor",
                                "kwargs": {
                                    "time_per_step": "day",
                                    "generate_portfolio_metrics": True,
                                },
                            },
                            "backtest": {
                                "start_time": split.test.start.isoformat(),
                                "end_time": split.test.end.isoformat(),
                                "account": 100000000,
                                "benchmark": spec.benchmark,
                                "exchange_kwargs": {
                                    "freq": "day",
                                    "limit_threshold": 0.095,
                                    "deal_price": "close",
                                    "open_cost": float(
                                        (spec.transaction_cost_bps + spec.slippage_bps)
                                        / 10000
                                    ),
                                    "close_cost": float(
                                        (spec.transaction_cost_bps + spec.slippage_bps)
                                        / 10000
                                    ),
                                    "min_cost": 0,
                                },
                            },
                        }
                    },
                },
            ],
        },
    }


def write_workflow_config(config: dict, path: str | Path) -> Path:
    """Write JSON syntax, which is valid YAML and avoids a runtime YAML dependency."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2, sort_keys=True) + "\n"
    if target.exists():
        if target.read_text(encoding="utf-8") == payload:
            return target
        raise FileExistsError("workflow config already exists with different content")
    target.write_text(payload, encoding="utf-8")
    return target


class SubprocessQlibRunner:
    def __init__(
        self,
        *,
        executable: str = "qrun",
        timeout_seconds: int = 3600,
        excerpt_limit: int = 4000,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.excerpt_limit = max(100, min(excerpt_limit, 4000))

    def run(self, config_path: str | Path) -> QlibWorkflowRun:
        config = Path(config_path).resolve(strict=True)
        command = [self.executable, str(config)]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
            status = "completed" if result.returncode == 0 else "failed"
            return QlibWorkflowRun(
                status=status,
                command=command,
                exit_code=result.returncode,
                latency_ms=int((time.monotonic() - started) * 1000),
                stdout_excerpt=result.stdout[-self.excerpt_limit :],
                stderr_excerpt=result.stderr[-self.excerpt_limit :],
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return QlibWorkflowRun(
                status="timed_out",
                command=command,
                latency_ms=int((time.monotonic() - started) * 1000),
                stdout_excerpt=stdout[-self.excerpt_limit :],
                stderr_excerpt=stderr[-self.excerpt_limit :],
            )
