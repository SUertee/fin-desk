"""Central settings and profile loading.

The project keeps YAML files for readability, but this loader intentionally
supports only the small subset used by the bundled profiles so tests do not
depend on PyYAML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DatabaseSettings:
    dsn: str = ""


@dataclass(frozen=True)
class CostSettings:
    reporting_currency: str = "USD"

    def __post_init__(self) -> None:
        currency = self.reporting_currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("reporting currency must be a three-letter code")
        object.__setattr__(self, "reporting_currency", currency)


@dataclass(frozen=True)
class InvestmentSettings:
    reporting_currency: str = "CNY"
    quote_stale_after_days: int = 3
    concentration_threshold_percent: Decimal = Decimal("35")

    def __post_init__(self) -> None:
        currency = self.reporting_currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("investment reporting currency must be a three-letter code")
        if self.quote_stale_after_days < 1:
            raise ValueError("investment quote stale days must be positive")
        threshold = Decimal(str(self.concentration_threshold_percent))
        if threshold <= 0 or threshold > 100:
            raise ValueError("investment concentration threshold must be in (0, 100]")
        object.__setattr__(self, "reporting_currency", currency)
        object.__setattr__(self, "concentration_threshold_percent", threshold)


@dataclass(frozen=True)
class MarketDataSettings:
    provider: str = "yfinance"
    allowed_providers: tuple[str, ...] = ("yfinance",)
    timeout_seconds: int = 12
    quote_ttl_seconds: int = 180
    history_ttl_seconds: int = 86400
    profile_ttl_seconds: int = 604800
    symbol_limit: int = 20
    history_day_limit: int = 3660
    outbound_call_budget: int = 3

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        allowed = tuple(
            item.strip().lower() for item in self.allowed_providers if item.strip()
        )
        if not provider:
            raise ValueError("market data provider cannot be empty")
        if not allowed:
            raise ValueError("market data provider allowlist cannot be empty")
        for field_name in (
            "timeout_seconds",
            "quote_ttl_seconds",
            "history_ttl_seconds",
            "profile_ttl_seconds",
            "symbol_limit",
            "history_day_limit",
            "outbound_call_budget",
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be positive")
        if self.symbol_limit > 100:
            raise ValueError("market data symbol limit cannot exceed 100")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_providers", allowed)


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    api_base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.2
    max_tokens: int = 1200
    timeout_seconds: int = 30
    input_cost_per_1m: Decimal | None = None
    cached_input_cost_per_1m: Decimal | None = None
    output_cost_per_1m: Decimal | None = None
    billing_currency: str = "USD"
    pricing_source: str = "not_configured"
    pricing_effective_date: date | None = None

    def __post_init__(self) -> None:
        currency = self.billing_currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError(f"invalid billing currency for profile {self.name}")
        object.__setattr__(self, "billing_currency", currency)
        for field_name in (
            "input_cost_per_1m",
            "cached_input_cost_per_1m",
            "output_cost_per_1m",
        ):
            raw = getattr(self, field_name)
            if raw is None:
                continue
            try:
                parsed = Decimal(str(raw))
            except InvalidOperation as exc:
                raise ValueError(f"invalid {field_name} for profile {self.name}") from exc
            if parsed < 0:
                raise ValueError(f"negative {field_name} for profile {self.name}")
            object.__setattr__(self, field_name, parsed)
        if isinstance(self.pricing_effective_date, str):
            object.__setattr__(
                self,
                "pricing_effective_date",
                date.fromisoformat(self.pricing_effective_date),
            )


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    mode: str = "self_hosted"
    max_tool_calls: int = 6
    max_handoffs: int = 3
    audit_on_specialist: bool = True
    allow_market_context: bool = False


@dataclass(frozen=True)
class AppSettings:
    environment: str
    allowed_origins: list[str]
    database: DatabaseSettings
    default_user_id: str = "demo"
    runtime_profile: str = "default"
    chat_model_profile: str = "chat"
    specialist_model_profile: str = "specialist"
    audit_model_profile: str = "audit"
    analysis_model_profile: str = "analysis"
    cost: CostSettings = CostSettings()
    investment: InvestmentSettings = InvestmentSettings()
    market_data: MarketDataSettings = MarketDataSettings()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _coerce_scalar(value: str) -> Any:
    stripped = value.strip().strip('"').strip("'")
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    if stripped.lower() in {"null", "none"}:
        return None
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped


def _load_simple_yaml(path: Path) -> dict[str, dict[str, Any]]:
    """Load simple top-level mapping YAML used by profile files."""

    if not path.exists():
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    current_name: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and raw_line.endswith(":"):
            current_name = raw_line[:-1].strip()
            profiles[current_name] = {}
            continue
        if current_name is None or ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        profiles[current_name][key.strip()] = _coerce_scalar(value)
    return profiles


@lru_cache(maxsize=1)
def load_model_profiles() -> dict[str, ModelProfile]:
    raw_profiles = _load_simple_yaml(CONFIG_DIR / "model_profiles.yaml")
    profiles: dict[str, ModelProfile] = {}
    for name, payload in raw_profiles.items():
        profiles[name] = ModelProfile(name=name, **payload)
    if not profiles:
        profiles["chat"] = ModelProfile(name="chat")
        profiles["specialist"] = ModelProfile(name="specialist")
        profiles["audit"] = ModelProfile(name="audit")
        profiles["analysis"] = ModelProfile(name="analysis")
    return profiles


@lru_cache(maxsize=1)
def load_runtime_profiles() -> dict[str, RuntimeProfile]:
    raw_profiles = _load_simple_yaml(CONFIG_DIR / "runtime_profiles.yaml")
    profiles: dict[str, RuntimeProfile] = {}
    for name, payload in raw_profiles.items():
        profiles[name] = RuntimeProfile(name=name, **payload)
    if not profiles:
        profiles["default"] = RuntimeProfile(name="default")
    return profiles


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:18001,http://127.0.0.1:18001",
    )
    return AppSettings(
        environment=os.getenv("APP_ENV", "local"),
        allowed_origins=_split_csv(origins),
        database=DatabaseSettings(
            dsn=os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL", "")
        ),
        default_user_id=os.getenv("DEFAULT_USER_ID", "demo"),
        runtime_profile=os.getenv("FINANCE_RUNTIME_PROFILE", "default"),
        chat_model_profile=os.getenv("FINANCE_CHAT_MODEL_PROFILE", "chat"),
        specialist_model_profile=os.getenv(
            "FINANCE_SPECIALIST_MODEL_PROFILE",
            "specialist",
        ),
        audit_model_profile=os.getenv("FINANCE_AUDIT_MODEL_PROFILE", "audit"),
        analysis_model_profile=os.getenv("FINANCE_ANALYSIS_MODEL_PROFILE", "analysis"),
        cost=CostSettings(
            reporting_currency=os.getenv("FINANCE_REPORTING_CURRENCY", "USD"),
        ),
        investment=InvestmentSettings(
            reporting_currency=os.getenv("INVESTMENT_REPORTING_CURRENCY", "CNY"),
            quote_stale_after_days=int(
                os.getenv("INVESTMENT_QUOTE_STALE_AFTER_DAYS", "3")
            ),
            concentration_threshold_percent=Decimal(
                os.getenv("INVESTMENT_CONCENTRATION_THRESHOLD_PERCENT", "35")
            ),
        ),
        market_data=MarketDataSettings(
            provider=os.getenv("MARKET_DATA_PROVIDER", "yfinance"),
            allowed_providers=tuple(
                _split_csv(os.getenv("MARKET_DATA_ALLOWED_PROVIDERS", "yfinance"))
            ),
            timeout_seconds=int(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "12")),
            quote_ttl_seconds=int(os.getenv("MARKET_DATA_QUOTE_TTL_SECONDS", "180")),
            history_ttl_seconds=int(
                os.getenv("MARKET_DATA_HISTORY_TTL_SECONDS", "86400")
            ),
            profile_ttl_seconds=int(
                os.getenv("MARKET_DATA_PROFILE_TTL_SECONDS", "604800")
            ),
            symbol_limit=int(os.getenv("MARKET_DATA_SYMBOL_LIMIT", "20")),
            history_day_limit=int(
                os.getenv("MARKET_DATA_HISTORY_DAY_LIMIT", "3660")
            ),
            outbound_call_budget=int(
                os.getenv("MARKET_DATA_OUTBOUND_CALL_BUDGET", "3")
            ),
        ),
    )
