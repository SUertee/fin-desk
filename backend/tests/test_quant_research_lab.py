from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.costing import MoneyAmount
from app.models.market_data import (
    ExternalCallUsage,
    MarketCacheMetadata,
    MarketPriceBar,
    MarketPriceHistory,
)
from research.quant_lab.artifacts import (
    read_experiment_artifact,
    write_experiment_artifact,
)
from research.quant_lab.baselines import (
    equal_weight_allocations,
    momentum_signals,
    momentum_top_k_allocations,
)
from research.quant_lab.contracts import (
    BacktestMetrics,
    BaselineResult,
    ChronologicalSplit,
    DatasetManifest,
    DateWindow,
    ExperimentArtifact,
    ExperimentArtifactBody,
    ModelDescriptor,
    QuantExperimentSpec,
)
from research.quant_lab.dataset import build_dataset_snapshot, write_dataset_snapshot
from research.quant_lab.leakage import FeatureLabelObservation, validate_observation
from research.quant_lab.qlib_workflow import (
    SubprocessQlibRunner,
    build_qlib_workflow_config,
)


NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


def _split() -> ChronologicalSplit:
    return ChronologicalSplit(
        train=DateWindow(start=date(2020, 1, 1), end=date(2022, 12, 31)),
        validation=DateWindow(start=date(2023, 1, 1), end=date(2023, 12, 31)),
        test=DateWindow(start=date(2024, 1, 1), end=date(2024, 12, 31)),
    )


def _spec(**overrides) -> QuantExperimentSpec:
    values = {
        "experiment_name": "etf-ranking-test",
        "universe": ["SPY", "QQQ", "IWM"],
        "benchmark": "SPY",
        "top_k": 2,
        "split": _split(),
    }
    values.update(overrides)
    return QuantExperimentSpec(**values)


def _history(symbol: str, closes: list[str]) -> MarketPriceHistory:
    start = date(2024, 1, 1)
    bars = []
    for index, close in enumerate(closes):
        amount = MoneyAmount(amount=close, currency="USD")
        bars.append(
            MarketPriceBar(
                symbol=symbol,
                asset_type="etf",
                period=start + timedelta(days=index),
                open=amount,
                high=amount,
                low=amount,
                close=amount,
                volume=1000 + index,
                source="openbb:test",
            )
        )
    return MarketPriceHistory(
        symbol=symbol,
        asset_type="etf",
        provider="openbb:test",
        currency="USD",
        date_from=start,
        date_to=start + timedelta(days=len(closes) - 1),
        fetched_at=NOW,
        bars=bars,
        cache=MarketCacheMetadata(
            cache_hit=False,
            cache_key=f"quant-history-{symbol.lower()}-0000000000000000",
            provider="test",
            fetched_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
        external_calls=ExternalCallUsage(budget=1, used=1, remaining=0),
    )


def _metrics(net_return: str = "1.25") -> BacktestMetrics:
    return BacktestMetrics(
        observation_count=100,
        rank_ic="0.05",
        annualized_return_percent="6.1",
        annualized_volatility_percent="8.2",
        sharpe_ratio="0.7",
        max_drawdown_percent="4.3",
        turnover_percent="12",
        transaction_cost_percent="0.1",
        net_return_percent=net_return,
    )


def _artifact(manifest: DatasetManifest, *, limitation: str = "Research only"):
    body = ExperimentArtifactBody(
        experiment_id="exp-etf-v0",
        created_at=NOW,
        status="completed",
        spec=_spec(),
        dataset=manifest,
        model=ModelDescriptor(
            framework_version="0.9.7",
            model_version="4.5",
            parameters={"seed": 42},
        ),
        baselines=[
            BaselineResult(name="equal_weight", metrics=_metrics("0.50")),
            BaselineResult(
                name="momentum_20d",
                parameters={"lookback": 20},
                metrics=_metrics("0.75"),
            ),
        ],
        out_of_sample_metrics=_metrics(),
        limitations=[limitation],
    )
    return ExperimentArtifact.build(body)


def test_experiment_spec_rejects_random_or_overlapping_split():
    with pytest.raises(ValidationError):
        _spec(split_method="random")

    with pytest.raises(ValidationError, match="training must end before"):
        ChronologicalSplit(
            train=DateWindow(start=date(2020, 1, 1), end=date(2023, 1, 1)),
            validation=DateWindow(start=date(2023, 1, 1), end=date(2023, 12, 31)),
            test=DateWindow(start=date(2024, 1, 1), end=date(2024, 12, 31)),
        )


def test_forward_labels_cannot_cross_partition_boundary():
    observation = FeatureLabelObservation(
        partition="train",
        feature_as_of=date(2022, 12, 30),
        label_from=date(2022, 12, 31),
        label_to=date(2023, 1, 3),
    )
    with pytest.raises(ValueError, match="crosses its partition"):
        validate_observation(observation, _split())


def test_dataset_snapshot_is_order_independent_and_preserves_provenance():
    spy = _history("SPY", ["100", "101", "102"])
    qqq = _history("QQQ", ["200", "202", "204"])
    first = build_dataset_snapshot([spy, qqq], created_at=NOW)
    second = build_dataset_snapshot([qqq, spy], created_at=NOW + timedelta(hours=1))

    assert first.manifest.content_sha256 == second.manifest.content_sha256
    assert first.manifest.snapshot_id == second.manifest.snapshot_id
    assert first.manifest.sources == ["openbb:test"]
    assert first.manifest.currencies == ["USD"]
    assert [(row.symbol, row.period) for row in first.rows] == sorted(
        (row.symbol, row.period) for row in first.rows
    )


def test_dataset_rejects_duplicate_history_and_writes_immutable_snapshot(tmp_path):
    spy = _history("SPY", ["100", "101", "102"])
    with pytest.raises(ValueError, match="duplicate history"):
        build_dataset_snapshot([spy, spy], created_at=NOW)

    snapshot = build_dataset_snapshot([spy], created_at=NOW)
    target = write_dataset_snapshot(snapshot, tmp_path)
    assert write_dataset_snapshot(snapshot, tmp_path) == target
    rebuilt = build_dataset_snapshot([spy], created_at=NOW + timedelta(hours=1))
    assert write_dataset_snapshot(rebuilt, tmp_path) == target
    assert (target / "raw" / "spy.csv").exists()
    assert (target / "instruments" / "all.txt").read_text().startswith("SPY\t")
    assert json.loads((target / "manifest.json").read_text())["content_sha256"] == (
        snapshot.manifest.content_sha256
    )


def test_equal_weight_and_momentum_baselines_are_deterministic_and_causal():
    spy = _history("SPY", [str(100 + index) for index in range(25)])
    qqq = _history("QQQ", [str(200 + index * 2) for index in range(25)])
    snapshot = build_dataset_snapshot([qqq, spy], created_at=NOW)
    as_of = date(2024, 1, 21)

    weights = equal_weight_allocations(["SPY", "QQQ"])
    assert sum((weight.weight for weight in weights), Decimal("0")) == Decimal("1")
    assert [weight.symbol for weight in weights] == ["QQQ", "SPY"]

    original = momentum_signals(
        snapshot.rows,
        as_of=as_of,
        lookback_observations=5,
    )
    future_changed = [
        row.model_copy(update={"close": Decimal("99999")})
        if row.period > as_of
        else row
        for row in snapshot.rows
    ]
    assert (
        momentum_signals(
            future_changed,
            as_of=as_of,
            lookback_observations=5,
        )
        == original
    )
    top = momentum_top_k_allocations(
        snapshot.rows,
        as_of=as_of,
        top_k=1,
        lookback_observations=5,
    )
    assert len(top) == 1
    assert top[0].weight == Decimal("1")


def test_experiment_artifact_is_non_trading_hashed_and_immutable(tmp_path):
    manifest = build_dataset_snapshot(
        [_history("SPY", ["100", "101"])],
        created_at=NOW,
    ).manifest
    artifact = _artifact(manifest)
    assert artifact.body.trade_actions_allowed is False

    target = write_experiment_artifact(artifact, tmp_path)
    assert write_experiment_artifact(artifact, tmp_path) == target
    assert read_experiment_artifact(target) == artifact

    changed = _artifact(manifest, limitation="Different result")
    with pytest.raises(FileExistsError, match="different immutable artifact"):
        write_experiment_artifact(changed, tmp_path)


def test_qlib_config_uses_time_split_rank_label_and_declared_costs():
    config = build_qlib_workflow_config(
        _spec(transaction_cost_bps="7", slippage_bps="3"),
        provider_uri="/research/qlib_data",
    )
    task = config["task"]
    segments = task["dataset"]["kwargs"]["segments"]
    label = task["dataset"]["kwargs"]["handler"]["kwargs"]["label"][0][0]
    backtest = task["record"][2]["kwargs"]["config"]["backtest"]

    assert segments["train"] == ["2020-01-01", "2022-12-31"]
    assert segments["test"] == ["2024-01-01", "2024-12-31"]
    assert label == "Rank(Ref($close, -6) / Ref($close, -1) - 1)"
    assert backtest["exchange_kwargs"]["open_cost"] == pytest.approx(0.001)
    assert task["model"]["class"] == "LGBModel"


def test_qlib_runner_never_uses_a_shell(monkeypatch, tmp_path):
    config = tmp_path / "workflow.yaml"
    config.write_text("{}\n", encoding="utf-8")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = SubprocessQlibRunner(executable="qrun-safe").run(config)

    assert result.status == "completed"
    assert observed["command"] == ["qrun-safe", str(config.resolve())]
    assert observed["shell"] is False


def test_live_application_does_not_import_research_package():
    app_root = Path(__file__).parents[1] / "app"
    offenders = []
    for path in app_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "from research" in source or "import research" in source:
            offenders.append(str(path.relative_to(app_root)))
    assert offenders == []
