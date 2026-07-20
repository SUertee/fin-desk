"""Strict contracts for reproducible, non-executable quant research."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.investments import normalize_symbol


SplitMethod = Literal["chronological", "walk_forward"]
ExperimentStatus = Literal["completed", "failed", "partial"]
BaselineName = Literal["equal_weight", "momentum_20d"]


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class DateWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def validate_order(self) -> "DateWindow":
        if self.start > self.end:
            raise ValueError("window start must be on or before end")
        return self


class ChronologicalSplit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train: DateWindow
    validation: DateWindow
    test: DateWindow

    @model_validator(mode="after")
    def validate_order(self) -> "ChronologicalSplit":
        if not self.train.end < self.validation.start:
            raise ValueError("training must end before validation starts")
        if not self.validation.end < self.test.start:
            raise ValueError("validation must end before test starts")
        return self


class QuantExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_name: str = Field(min_length=1, max_length=160)
    universe: list[str] = Field(min_length=2, max_length=100)
    benchmark: str = "SPY"
    target: Literal["next_5d_relative_return_rank"] = (
        "next_5d_relative_return_rank"
    )
    horizon_days: int = Field(default=5, ge=1, le=20)
    momentum_lookback_days: int = Field(default=20, ge=2, le=252)
    top_k: int = Field(default=5, ge=1, le=50)
    split_method: SplitMethod = "chronological"
    split: ChronologicalSplit
    transaction_cost_bps: Decimal = Field(default=Decimal("5"), ge=0, le=1000)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0, le=1000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @field_validator("universe")
    @classmethod
    def validate_universe(cls, value: list[str]) -> list[str]:
        normalized = [normalize_symbol(symbol) for symbol in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("universe symbols must be unique")
        return normalized

    @field_validator("benchmark")
    @classmethod
    def validate_benchmark(cls, value: str) -> str:
        return normalize_symbol(value)

    @model_validator(mode="after")
    def validate_strategy(self) -> "QuantExperimentSpec":
        if self.top_k > len(self.universe):
            raise ValueError("top_k cannot exceed universe size")
        return self


class NormalizedPriceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    asset_type: Literal["equity", "etf"]
    period: date
    currency: str = Field(min_length=3, max_length=3)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int | None = Field(default=None, ge=0)
    factor: Decimal = Field(default=Decimal("1"), gt=0)
    source: str = Field(min_length=1, max_length=120)
    fetched_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("currency must contain letters only")
        return normalized

    @field_validator("fetched_at")
    @classmethod
    def validate_fetched_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "NormalizedPriceRow":
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["quant-dataset-v1"] = "quant-dataset-v1"
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbols: list[str] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    currencies: list[str] = Field(min_length=1)
    date_from: date
    date_to: date
    row_count: int = Field(gt=0)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_range(self) -> "DatasetManifest":
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if self.snapshot_id != self.content_sha256[:16]:
            raise ValueError("snapshot_id must be derived from content_sha256")
        return self


class ResearchDatasetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: DatasetManifest
    rows: list[NormalizedPriceRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "ResearchDatasetSnapshot":
        payload = [row.model_dump(mode="json") for row in self.rows]
        digest = content_sha256(payload)
        if digest != self.manifest.content_sha256:
            raise ValueError("dataset rows do not match manifest hash")
        if len(self.rows) != self.manifest.row_count:
            raise ValueError("dataset rows do not match manifest row_count")
        return self


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_count: int = Field(ge=0)
    rank_ic: Decimal | None = Field(default=None, ge=-1, le=1)
    annualized_return_percent: Decimal | None = None
    annualized_volatility_percent: Decimal | None = Field(default=None, ge=0)
    sharpe_ratio: Decimal | None = None
    max_drawdown_percent: Decimal | None = Field(default=None, ge=0, le=100)
    turnover_percent: Decimal | None = Field(default=None, ge=0)
    transaction_cost_percent: Decimal = Field(default=Decimal("0"), ge=0)
    net_return_percent: Decimal | None = None


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: BaselineName
    parameters: dict[str, int | str | Decimal] = Field(default_factory=dict)
    metrics: BacktestMetrics


class ModelDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    framework: Literal["qlib"] = "qlib"
    model_type: Literal["lightgbm"] = "lightgbm"
    framework_version: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=80)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class ExperimentArtifactBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["quant-experiment-v1"] = "quant-experiment-v1"
    experiment_id: str = Field(min_length=1, max_length=160)
    created_at: datetime
    status: ExperimentStatus
    spec: QuantExperimentSpec
    dataset: DatasetManifest
    model: ModelDescriptor
    baselines: list[BaselineResult] = Field(min_length=2)
    out_of_sample_metrics: BacktestMetrics | None = None
    limitations: list[str] = Field(min_length=1)
    trade_actions_allowed: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_baselines(self) -> "ExperimentArtifactBody":
        names = {baseline.name for baseline in self.baselines}
        if names != {"equal_weight", "momentum_20d"}:
            raise ValueError("equal_weight and momentum_20d baselines are required")
        if self.status == "completed" and self.out_of_sample_metrics is None:
            raise ValueError("completed experiment requires out-of-sample metrics")
        return self


class ExperimentArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    body: ExperimentArtifactBody
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(cls, body: ExperimentArtifactBody) -> "ExperimentArtifact":
        digest = content_sha256(body.model_dump(mode="json"))
        return cls(body=body, content_sha256=digest)

    @model_validator(mode="after")
    def validate_hash(self) -> "ExperimentArtifact":
        expected = content_sha256(self.body.model_dump(mode="json"))
        if self.content_sha256 != expected:
            raise ValueError("experiment artifact hash does not match body")
        return self


class QlibWorkflowRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["completed", "failed", "timed_out"]
    command: list[str] = Field(min_length=2, max_length=4)
    exit_code: int | None = None
    latency_ms: int = Field(ge=0)
    stdout_excerpt: str = Field(default="", max_length=4000)
    stderr_excerpt: str = Field(default="", max_length=4000)
