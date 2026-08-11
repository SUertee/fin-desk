"""Central settings and profile loading.

The project keeps YAML files for readability, but this loader intentionally
supports only the small subset used by the bundled profiles so tests do not
depend on PyYAML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit


CONFIG_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DatabaseSettings:
    dsn: str = ""


@dataclass(frozen=True)
class RedisSettings:
    url: str = ""
    key_prefix: str = "findesk:v1"
    chat_history_ttl_seconds: int = 3600
    session_memory_ttl_seconds: int = 86400
    socket_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        prefix = self.key_prefix.strip().strip(":")
        if not prefix:
            raise ValueError("Redis key prefix cannot be empty")
        for field_name in (
            "chat_history_ttl_seconds",
            "session_memory_ttl_seconds",
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be positive")
        if self.socket_timeout_seconds <= 0:
            raise ValueError("Redis socket timeout must be positive")
        object.__setattr__(self, "url", self.url.strip())
        object.__setattr__(self, "key_prefix", prefix)

    @property
    def enabled(self) -> bool:
        return bool(self.url)


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
    outbound_call_budget: int = 4

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
class ExchangeRateSettings:
    provider: str = "frankfurter"
    allowed_providers: tuple[str, ...] = ("frankfurter",)
    base_url: str = "https://api.frankfurter.dev"
    timeout_seconds: int = 10
    max_snapshot_age_days: int = 7

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        allowed = tuple(
            item.strip().lower() for item in self.allowed_providers if item.strip()
        )
        if provider not in allowed:
            raise ValueError("exchange-rate provider is not allowlisted")
        if self.timeout_seconds < 1:
            raise ValueError("exchange-rate timeout must be positive")
        if self.max_snapshot_age_days < 0:
            raise ValueError("exchange-rate snapshot age cannot be negative")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_providers", allowed)


@dataclass(frozen=True)
class WebResearchSettings:
    provider: str = "tavily"
    allowed_providers: tuple[str, ...] = ("tavily",)
    base_url: str = "https://api.tavily.com"
    allowed_domains: tuple[str, ...] = (
        "bis.org",
        "chinatax.gov.cn",
        "csrc.gov.cn",
        "ecb.europa.eu",
        "federalreserve.gov",
        "finra.org",
        "gov.cn",
        "imf.org",
        "investor.gov",
        "mof.gov.cn",
        "oecd.org",
        "pbc.gov.cn",
        "worldbank.org",
    )
    timeout_seconds: int = 10
    cache_ttl_seconds: int = 3600
    max_results: int = 5
    outbound_call_budget: int = 1

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        allowed_providers = tuple(
            item.strip().lower() for item in self.allowed_providers if item.strip()
        )
        allowed_domains = tuple(
            item.strip().lower().removeprefix("www.").rstrip(".")
            for item in self.allowed_domains
            if item.strip()
        )
        if provider not in allowed_providers:
            raise ValueError("web-research provider is not allowlisted")
        if not allowed_domains:
            raise ValueError("web-research domain allowlist cannot be empty")
        for field_name in (
            "timeout_seconds",
            "cache_ttl_seconds",
            "max_results",
            "outbound_call_budget",
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be positive")
        if self.max_results > 10:
            raise ValueError("web-research result limit cannot exceed 10")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_providers", allowed_providers)
        object.__setattr__(self, "allowed_domains", allowed_domains)


@dataclass(frozen=True)
class KnowledgeSettings:
    retrieval_mode: Literal["lexical", "hybrid"] = "lexical"
    embedding_provider: str = "siliconflow"
    allowed_embedding_providers: tuple[str, ...] = ("siliconflow",)
    embedding_api_key: str = field(default="", repr=False)
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_timeout_seconds: int = 20
    embedding_batch_size: int = 32
    vector_min_score: float = 0.45
    rrf_k: int = 60

    def __post_init__(self) -> None:
        mode = self.retrieval_mode.strip().lower()
        provider = self.embedding_provider.strip().lower()
        allowed = tuple(
            item.strip().lower()
            for item in self.allowed_embedding_providers
            if item.strip()
        )
        if mode not in {"lexical", "hybrid"}:
            raise ValueError("knowledge retrieval mode must be lexical or hybrid")
        if not allowed or provider not in allowed:
            raise ValueError("knowledge embedding provider is not allowlisted")
        if not self.embedding_model.strip():
            raise ValueError("knowledge embedding model cannot be empty")
        parsed_base_url = urlsplit(self.embedding_base_url.strip())
        if parsed_base_url.scheme != "https" or not parsed_base_url.hostname:
            raise ValueError("knowledge embedding base URL must use HTTPS")
        if not 1 <= self.embedding_dimension <= 4096:
            raise ValueError(
                "knowledge embedding dimension must be between 1 and 4096"
            )
        if not 1 <= self.embedding_timeout_seconds <= 120:
            raise ValueError(
                "knowledge embedding timeout must be between 1 and 120 seconds"
            )
        if not 1 <= self.embedding_batch_size <= 256:
            raise ValueError("knowledge embedding batch size must be between 1 and 256")
        if not 0 <= self.vector_min_score <= 1:
            raise ValueError("knowledge vector score must be between 0 and 1")
        if not 1 <= self.rrf_k <= 1000:
            raise ValueError("knowledge RRF k must be between 1 and 1000")
        object.__setattr__(self, "retrieval_mode", mode)
        object.__setattr__(self, "embedding_provider", provider)
        object.__setattr__(self, "allowed_embedding_providers", allowed)
        object.__setattr__(self, "embedding_api_key", self.embedding_api_key.strip())
        object.__setattr__(
            self,
            "embedding_base_url",
            self.embedding_base_url.rstrip("/"),
        )
        object.__setattr__(self, "embedding_model", self.embedding_model.strip())


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: str = "minio"
    allowed_providers: tuple[str, ...] = ("minio",)
    endpoint: str = "localhost:9000"
    external_endpoint: str = "localhost:9000"
    bucket: str = "findesk-user-assets"
    access_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    secure: bool = False
    external_secure: bool = False
    presign_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        allowed = tuple(
            item.strip().lower()
            for item in self.allowed_providers
            if item.strip()
        )
        if not allowed or provider not in allowed:
            raise ValueError("object storage provider is not allowlisted")
        if not self.endpoint.strip():
            raise ValueError("object storage endpoint cannot be empty")
        if not self.bucket.strip():
            raise ValueError("object storage bucket cannot be empty")
        if not 60 <= self.presign_ttl_seconds <= 86400:
            raise ValueError(
                "object storage presign TTL must be between 60 and 86400 seconds"
            )
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_providers", allowed)
        object.__setattr__(self, "endpoint", self.endpoint.strip())
        object.__setattr__(
            self, "external_endpoint", self.external_endpoint.strip()
        )
        object.__setattr__(self, "bucket", self.bucket.strip())
        object.__setattr__(self, "access_key", self.access_key.strip())
        object.__setattr__(self, "secret_key", self.secret_key.strip())

    @property
    def enabled(self) -> bool:
        return bool(self.access_key and self.secret_key)


@dataclass(frozen=True)
class VisionSettings:
    provider: str = "siliconflow"
    allowed_providers: tuple[str, ...] = ("siliconflow",)
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "Qwen/Qwen2.5-VL-72B-Instruct"
    timeout_seconds: int = 60
    outbound_call_budget: int = 8

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        allowed = tuple(
            item.strip().lower()
            for item in self.allowed_providers
            if item.strip()
        )
        if not allowed or provider not in allowed:
            raise ValueError("vision provider is not allowlisted")
        if not self.model.strip():
            raise ValueError("vision model cannot be empty")
        parsed_base_url = urlsplit(self.base_url.strip())
        if parsed_base_url.scheme != "https" or not parsed_base_url.hostname:
            raise ValueError("vision base URL must use HTTPS")
        if not 1 <= self.timeout_seconds <= 180:
            raise ValueError("vision timeout must be between 1 and 180 seconds")
        if not 1 <= self.outbound_call_budget <= 100:
            raise ValueError(
                "vision outbound call budget must be between 1 and 100"
            )
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_providers", allowed)
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "model", self.model.strip())

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class DocumentIngestionSettings:
    inbox_path: Path = Path("storage/document-inbox")
    storage_path: Path = Path("storage/document-imports")
    max_file_bytes: int = 20_000_000
    poll_seconds: int = 10
    stable_seconds: int = 5
    image_min_area: int = 5000
    thumbnail_max_edge: int = 300
    caption_max_chars: int = 300

    def __post_init__(self) -> None:
        if self.max_file_bytes < 1:
            raise ValueError("document maximum file size must be positive")
        if self.poll_seconds < 2:
            raise ValueError("document poll interval must be at least 2 seconds")
        if self.stable_seconds < 1:
            raise ValueError("document stable interval must be positive")
        if self.image_min_area < 1:
            raise ValueError("document image_min_area must be positive")
        if self.thumbnail_max_edge < 16:
            raise ValueError("document thumbnail_max_edge must be at least 16")
        if not 50 <= self.caption_max_chars <= 2000:
            raise ValueError(
                "document caption_max_chars must be between 50 and 2000"
            )


@dataclass(frozen=True)
class FinanceInboxSettings:
    timeout_seconds: int = 10
    max_response_bytes: int = 2_000_000
    max_entries_per_feed: int = 200
    max_redirects: int = 3
    max_opml_bytes: int = 1_000_000
    max_opml_outlines: int = 200
    allow_proxy_fake_ips: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "timeout_seconds",
            "max_response_bytes",
            "max_entries_per_feed",
            "max_opml_bytes",
            "max_opml_outlines",
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"{field_name} must be positive")
        if self.max_redirects < 0 or self.max_redirects > 10:
            raise ValueError("max_redirects must be between 0 and 10")


@dataclass(frozen=True)
class StatementIngestionSettings:
    inbox_path: Path = Path("storage/import-inbox")
    storage_path: Path = Path("storage/statement-imports")
    poll_seconds: int = 10
    stable_seconds: int = 5
    max_file_bytes: int = 20_000_000
    email_poll_seconds: int = 300
    email_host: str = ""
    email_port: int = 993
    email_username: str = ""
    email_password: str = field(default="", repr=False)
    email_use_ssl: bool = True

    def __post_init__(self) -> None:
        if self.poll_seconds < 2:
            raise ValueError("statement poll interval must be at least 2 seconds")
        if self.stable_seconds < 1:
            raise ValueError("statement stable interval must be positive")
        if self.max_file_bytes < 1:
            raise ValueError("statement maximum file size must be positive")
        if self.email_poll_seconds < 30:
            raise ValueError("statement email poll interval must be at least 30 seconds")
        if not 1 <= self.email_port <= 65535:
            raise ValueError("statement email port is invalid")

    @property
    def email_available(self) -> bool:
        return bool(self.email_host and self.email_username and self.email_password)


@dataclass(frozen=True)
class McpSettings:
    enabled: bool = False
    transport: Literal["stdio", "sse"] = "stdio"
    command: str = "vibe-trading-mcp"
    allowed_commands: tuple[str, ...] = ("vibe-trading-mcp",)
    url: str = "http://127.0.0.1:8900/sse"
    allowed_urls: tuple[str, ...] = ("http://127.0.0.1:8900/sse",)
    allowed_tools: tuple[str, ...] = ("get_market_data",)
    timeout_seconds: int = 20
    max_response_bytes: int = 200_000
    health_ttl_seconds: int = 30
    market_source: str = "yfinance"
    lookback_days: int = 90
    max_rows: int = 90

    def __post_init__(self) -> None:
        transport = self.transport.strip().lower()
        command = self.command.strip()
        allowed_commands = tuple(
            item.strip() for item in self.allowed_commands if item.strip()
        )
        url = self.url.strip()
        allowed_urls = tuple(item.strip() for item in self.allowed_urls if item.strip())
        allowed_tools = tuple(item.strip() for item in self.allowed_tools if item.strip())
        if transport not in {"stdio", "sse"}:
            raise ValueError("MCP transport must be stdio or sse")
        if transport == "stdio" and (not command or command not in allowed_commands):
            raise ValueError("MCP stdio command is not allowlisted")
        if transport == "sse" and (not url or url not in allowed_urls):
            raise ValueError("MCP SSE URL is not allowlisted")
        if "get_market_data" not in allowed_tools:
            raise ValueError("MCP Vibe market-data tool is not allowlisted")
        if self.timeout_seconds < 1 or self.timeout_seconds > 120:
            raise ValueError("MCP timeout must be between 1 and 120 seconds")
        if self.max_response_bytes < 1 or self.max_response_bytes > 1_000_000:
            raise ValueError("MCP response bound must be between 1 and 1000000 bytes")
        if self.health_ttl_seconds < 1 or self.health_ttl_seconds > 300:
            raise ValueError("MCP health TTL must be between 1 and 300 seconds")
        if self.lookback_days < 1 or self.lookback_days > 366:
            raise ValueError("MCP market lookback must be between 1 and 366 days")
        if self.max_rows < 1 or self.max_rows > 250:
            raise ValueError("MCP market row limit must be between 1 and 250")
        if self.market_source.strip().lower() not in {
            "yfinance",
            "okx",
            "tushare",
            "baostock",
            "tencent",
            "akshare",
            "ccxt",
            "auto",
        }:
            raise ValueError("MCP market source is not supported")
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "allowed_commands", allowed_commands)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "allowed_urls", allowed_urls)
        object.__setattr__(self, "allowed_tools", allowed_tools)
        object.__setattr__(self, "market_source", self.market_source.strip().lower())


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
    redis: RedisSettings = RedisSettings()
    default_user_id: str = "demo"
    runtime_profile: str = "default"
    chat_model_profile: str = "chat"
    specialist_model_profile: str = "specialist"
    audit_model_profile: str = "audit"
    cost: CostSettings = CostSettings()
    investment: InvestmentSettings = InvestmentSettings()
    market_data: MarketDataSettings = MarketDataSettings()
    exchange_rate: ExchangeRateSettings = ExchangeRateSettings()
    web_research: WebResearchSettings = WebResearchSettings()
    knowledge: KnowledgeSettings = KnowledgeSettings()
    finance_inbox: FinanceInboxSettings = FinanceInboxSettings()
    statement_ingestion: StatementIngestionSettings = StatementIngestionSettings()
    mcp: McpSettings = McpSettings()
    object_storage: ObjectStorageSettings = ObjectStorageSettings()
    vision: VisionSettings = VisionSettings()
    document_ingestion: DocumentIngestionSettings = DocumentIngestionSettings()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
        redis=RedisSettings(
            url=os.getenv("REDIS_URL", ""),
            key_prefix=os.getenv("REDIS_KEY_PREFIX", "findesk:v1"),
            chat_history_ttl_seconds=int(
                os.getenv("REDIS_CHAT_HISTORY_TTL_SECONDS", "3600")
            ),
            session_memory_ttl_seconds=int(
                os.getenv("REDIS_SESSION_MEMORY_TTL_SECONDS", "86400")
            ),
            socket_timeout_seconds=float(
                os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "1")
            ),
        ),
        default_user_id=os.getenv("DEFAULT_USER_ID", "demo"),
        runtime_profile=os.getenv("FINANCE_RUNTIME_PROFILE", "default"),
        chat_model_profile=os.getenv("FINANCE_CHAT_MODEL_PROFILE", "chat"),
        specialist_model_profile=os.getenv(
            "FINANCE_SPECIALIST_MODEL_PROFILE",
            "specialist",
        ),
        audit_model_profile=os.getenv("FINANCE_AUDIT_MODEL_PROFILE", "audit"),
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
                os.getenv("MARKET_DATA_OUTBOUND_CALL_BUDGET", "4")
            ),
        ),
        exchange_rate=ExchangeRateSettings(
            provider=os.getenv("EXCHANGE_RATE_PROVIDER", "frankfurter"),
            allowed_providers=tuple(
                _split_csv(
                    os.getenv("EXCHANGE_RATE_ALLOWED_PROVIDERS", "frankfurter")
                )
            ),
            base_url=os.getenv(
                "EXCHANGE_RATE_BASE_URL", "https://api.frankfurter.dev"
            ),
            timeout_seconds=int(os.getenv("EXCHANGE_RATE_TIMEOUT_SECONDS", "10")),
            max_snapshot_age_days=int(
                os.getenv("EXCHANGE_RATE_MAX_SNAPSHOT_AGE_DAYS", "7")
            ),
        ),
        web_research=WebResearchSettings(
            provider=os.getenv("WEB_RESEARCH_PROVIDER", "tavily"),
            allowed_providers=tuple(
                _split_csv(os.getenv("WEB_RESEARCH_ALLOWED_PROVIDERS", "tavily"))
            ),
            base_url=os.getenv("WEB_RESEARCH_BASE_URL", "https://api.tavily.com"),
            allowed_domains=tuple(
                _split_csv(
                    os.getenv(
                        "WEB_RESEARCH_ALLOWED_DOMAINS",
                        "bis.org,chinatax.gov.cn,csrc.gov.cn,ecb.europa.eu,"
                        "federalreserve.gov,finra.org,gov.cn,imf.org,investor.gov,"
                        "mof.gov.cn,oecd.org,pbc.gov.cn,worldbank.org",
                    )
                )
            ),
            timeout_seconds=int(os.getenv("WEB_RESEARCH_TIMEOUT_SECONDS", "10")),
            cache_ttl_seconds=int(
                os.getenv("WEB_RESEARCH_CACHE_TTL_SECONDS", "3600")
            ),
            max_results=int(os.getenv("WEB_RESEARCH_MAX_RESULTS", "5")),
            outbound_call_budget=int(
                os.getenv("WEB_RESEARCH_OUTBOUND_CALL_BUDGET", "1")
            ),
        ),
        knowledge=KnowledgeSettings(
            retrieval_mode=os.getenv("KNOWLEDGE_RETRIEVAL_MODE", "lexical"),
            embedding_provider=os.getenv(
                "KNOWLEDGE_EMBEDDING_PROVIDER", "siliconflow"
            ),
            allowed_embedding_providers=tuple(
                _split_csv(
                    os.getenv(
                        "KNOWLEDGE_EMBEDDING_ALLOWED_PROVIDERS",
                        "siliconflow",
                    )
                )
            ),
            embedding_api_key=os.getenv("SILICONFLOW_API_KEY", ""),
            embedding_base_url=os.getenv(
                "SILICONFLOW_BASE_URL",
                "https://api.siliconflow.cn/v1",
            ),
            embedding_model=os.getenv(
                "SILICONFLOW_EMBEDDING_MODEL",
                "BAAI/bge-m3",
            ),
            embedding_dimension=int(
                os.getenv("SILICONFLOW_EMBEDDING_DIMENSION", "1024")
            ),
            embedding_timeout_seconds=int(
                os.getenv("SILICONFLOW_EMBEDDING_TIMEOUT_SECONDS", "20")
            ),
            embedding_batch_size=int(
                os.getenv("KNOWLEDGE_EMBEDDING_BATCH_SIZE", "32")
            ),
            vector_min_score=float(
                os.getenv("KNOWLEDGE_VECTOR_MIN_SCORE", "0.45")
            ),
            rrf_k=int(os.getenv("KNOWLEDGE_RRF_K", "60")),
        ),
        finance_inbox=FinanceInboxSettings(
            timeout_seconds=int(os.getenv("FINANCE_INBOX_TIMEOUT_SECONDS", "10")),
            max_response_bytes=int(
                os.getenv("FINANCE_INBOX_MAX_RESPONSE_BYTES", "2000000")
            ),
            max_entries_per_feed=int(
                os.getenv("FINANCE_INBOX_MAX_ENTRIES_PER_FEED", "200")
            ),
            max_redirects=int(os.getenv("FINANCE_INBOX_MAX_REDIRECTS", "3")),
            max_opml_bytes=int(
                os.getenv("FINANCE_INBOX_MAX_OPML_BYTES", "1000000")
            ),
            max_opml_outlines=int(
                os.getenv("FINANCE_INBOX_MAX_OPML_OUTLINES", "200")
            ),
            allow_proxy_fake_ips=_env_bool(
                "FINANCE_INBOX_ALLOW_PROXY_FAKE_IPS",
                False,
            ),
        ),
        statement_ingestion=StatementIngestionSettings(
            inbox_path=Path(
                os.getenv("STATEMENT_INBOX_PATH", "storage/import-inbox")
            ),
            storage_path=Path(
                os.getenv("STATEMENT_STORAGE_PATH", "storage/statement-imports")
            ),
            poll_seconds=int(os.getenv("STATEMENT_POLL_SECONDS", "10")),
            stable_seconds=int(os.getenv("STATEMENT_STABLE_SECONDS", "5")),
            max_file_bytes=int(
                os.getenv("STATEMENT_MAX_FILE_BYTES", "20000000")
            ),
            email_poll_seconds=int(
                os.getenv("STATEMENT_EMAIL_POLL_SECONDS", "300")
            ),
            email_host=os.getenv("STATEMENT_EMAIL_HOST", ""),
            email_port=int(os.getenv("STATEMENT_EMAIL_PORT", "993")),
            email_username=os.getenv("STATEMENT_EMAIL_USERNAME", ""),
            email_password=os.getenv("STATEMENT_EMAIL_PASSWORD", ""),
            email_use_ssl=_env_bool("STATEMENT_EMAIL_USE_SSL", True),
        ),
        mcp=McpSettings(
            enabled=_env_bool("MCP_VIBE_ENABLED", False),
            transport=os.getenv("MCP_VIBE_TRANSPORT", "stdio"),
            command=os.getenv("MCP_VIBE_COMMAND", "vibe-trading-mcp"),
            allowed_commands=tuple(
                _split_csv(
                    os.getenv("MCP_STDIO_ALLOWED_COMMANDS", "vibe-trading-mcp")
                )
            ),
            allowed_tools=tuple(
                _split_csv(os.getenv("MCP_VIBE_ALLOWED_TOOLS", "get_market_data"))
            ),
            url=os.getenv("MCP_VIBE_URL", "http://127.0.0.1:8900/sse"),
            allowed_urls=tuple(
                _split_csv(
                    os.getenv(
                        "MCP_SSE_ALLOWED_URLS",
                        "http://127.0.0.1:8900/sse",
                    )
                )
            ),
            timeout_seconds=int(os.getenv("MCP_VIBE_TIMEOUT_SECONDS", "20")),
            max_response_bytes=int(
                os.getenv("MCP_VIBE_MAX_RESPONSE_BYTES", "200000")
            ),
            health_ttl_seconds=int(
                os.getenv("MCP_VIBE_HEALTH_TTL_SECONDS", "30")
            ),
            market_source=os.getenv("MCP_VIBE_MARKET_SOURCE", "yfinance"),
            lookback_days=int(os.getenv("MCP_VIBE_LOOKBACK_DAYS", "90")),
            max_rows=int(os.getenv("MCP_VIBE_MAX_ROWS", "90")),
        ),
        object_storage=ObjectStorageSettings(
            provider=os.getenv("OBJECT_STORAGE_PROVIDER", "minio"),
            allowed_providers=tuple(
                _split_csv(os.getenv("OBJECT_STORAGE_ALLOWED_PROVIDERS", "minio"))
            ),
            endpoint=os.getenv("OBJECT_STORAGE_ENDPOINT", "localhost:9000"),
            external_endpoint=os.getenv(
                "OBJECT_STORAGE_EXTERNAL_ENDPOINT", "localhost:9000"
            ),
            bucket=os.getenv("OBJECT_STORAGE_BUCKET", "findesk-user-assets"),
            access_key=os.getenv("OBJECT_STORAGE_ACCESS_KEY", ""),
            secret_key=os.getenv("OBJECT_STORAGE_SECRET_KEY", ""),
            secure=_env_bool("OBJECT_STORAGE_SECURE", False),
            external_secure=_env_bool("OBJECT_STORAGE_EXTERNAL_SECURE", False),
            presign_ttl_seconds=int(
                os.getenv("OBJECT_STORAGE_PRESIGN_TTL_SECONDS", "300")
            ),
        ),
        vision=VisionSettings(
            provider=os.getenv("VISION_PROVIDER", "siliconflow"),
            allowed_providers=tuple(
                _split_csv(os.getenv("VISION_ALLOWED_PROVIDERS", "siliconflow"))
            ),
            api_key=os.getenv("SILICONFLOW_API_KEY", ""),
            base_url=os.getenv("VISION_BASE_URL", "https://api.siliconflow.cn/v1"),
            model=os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct"),
            timeout_seconds=int(os.getenv("VISION_TIMEOUT_SECONDS", "60")),
            outbound_call_budget=int(
                os.getenv("VISION_OUTBOUND_CALL_BUDGET", "8")
            ),
        ),
        document_ingestion=DocumentIngestionSettings(
            inbox_path=Path(
                os.getenv("DOCUMENT_INBOX_PATH", "storage/document-inbox")
            ),
            storage_path=Path(
                os.getenv("DOCUMENT_STORAGE_PATH", "storage/document-imports")
            ),
            max_file_bytes=int(os.getenv("DOCUMENT_MAX_FILE_BYTES", "20000000")),
            poll_seconds=int(os.getenv("DOCUMENT_POLL_SECONDS", "10")),
            stable_seconds=int(os.getenv("DOCUMENT_STABLE_SECONDS", "5")),
            image_min_area=int(os.getenv("DOCUMENT_IMAGE_MIN_AREA", "5000")),
            thumbnail_max_edge=int(
                os.getenv("DOCUMENT_THUMBNAIL_MAX_EDGE", "300")
            ),
            caption_max_chars=int(
                os.getenv("DOCUMENT_CAPTION_MAX_CHARS", "300")
            ),
        ),
    )
