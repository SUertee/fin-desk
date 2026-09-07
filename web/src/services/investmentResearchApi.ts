import { getApiBaseUrl } from "./financeApi";
import { authFetch } from "./authApi";

export type MarketAssetType = "equity" | "etf";

export type MoneyAmount = {
  amount: string;
  currency: string;
};

export type WatchlistItem = {
  user_id: string;
  symbol: string;
  asset_type: MarketAssetType;
  note: string;
  created_at: string;
  updated_at: string;
};

export type MarketQuote = {
  symbol: string;
  asset_type: MarketAssetType;
  price: MoneyAmount;
  quote_as_of: string;
  timestamp_basis: "provider_time" | "retrieval_time";
  source: string;
  venue: string;
};

export type MarketPriceBar = {
  period: string;
  close: MoneyAmount;
};

export type ResearchEvidence = {
  kind: "profile" | "quote" | "history" | "benchmark_history" | "exchange_rate";
  source: string;
  as_of: string;
  description: string;
};

export type HistoricalPerformanceSummary = {
  status: "available" | "insufficient_data";
  symbol: string;
  currency: string;
  observation_count: number;
  date_from: string | null;
  date_to: string | null;
  period_return_percent: string | null;
  annualized_volatility_percent: string | null;
  max_drawdown_percent: string | null;
};

export type BenchmarkComparison = {
  status: "available" | "unavailable" | "insufficient_data";
  benchmark_symbol: string;
  performance: HistoricalPerformanceSummary | null;
  excess_period_return_percent: string | null;
  limitation: string | null;
};

export type InvestmentReadinessFinding = {
  code: string;
  severity: "info" | "medium" | "high";
  title: string;
  detail: string;
};

export type InvestmentReadinessAssessment = {
  status: "ready" | "caution" | "insufficient_data";
  reporting_currency: string;
  monthly_cash_flow: string | null;
  liquid_reserve: MoneyAmount | null;
  reserve_months: string | null;
  liabilities: MoneyAmount | null;
  risk_tolerance: string;
  findings: InvestmentReadinessFinding[];
  limitations: string[];
  trade_actions_allowed: false;
};

export type InstrumentResearchSnapshot = {
  user_id: string;
  symbol: string;
  asset_type: MarketAssetType;
  followed: boolean;
  profile: {
    symbol: string;
    name: string;
    venue: string;
    currency: string;
    sector: string | null;
    industry: string | null;
    country: string | null;
    source: string;
    fetched_at: string;
  };
  quote: MarketQuote | null;
  history: {
    provider: string;
    currency: string;
    date_from: string;
    date_to: string;
    fetched_at: string;
    bars: MarketPriceBar[];
  };
  performance: HistoricalPerformanceSummary;
  benchmark: BenchmarkComparison;
  readiness: InvestmentReadinessAssessment;
  evidence: ResearchEvidence[];
  limitations: string[];
  trade_actions_allowed: false;
};

export type InvestmentScenario = {
  user_id: string;
  scenario_id: string;
  name: string;
  reporting_currency: string;
  starting_cash: MoneyAmount | null;
  created_at: string;
  updated_at: string;
};

export type ScenarioPosition = {
  user_id: string;
  scenario_id: string;
  symbol: string;
  asset_type: MarketAssetType;
  quantity: string;
  created_at: string;
  updated_at: string;
};

export type InvestmentScenarioDetail = {
  scenario: InvestmentScenario;
  positions: ScenarioPosition[];
};

export type ScenarioValuation = {
  status: "empty" | "partial" | "complete";
  scenario: InvestmentScenario;
  as_of: string;
  positions: Array<{
    symbol: string;
    asset_type: MarketAssetType;
    quantity: string;
    quote: MarketQuote | null;
    native_market_value: MoneyAmount | null;
    reporting_market_value: MoneyAmount | null;
    exchange_rate_snapshot: {
      billing_currency: string;
      reporting_currency: string;
      exchange_rate: string;
      exchange_rate_date: string;
      exchange_rate_source: string;
    } | null;
    issues: string[];
  }>;
  native_totals: MoneyAmount[];
  converted_subtotal: MoneyAmount | null;
  reporting_total: MoneyAmount | null;
  remaining_cash: MoneyAmount | null;
  overallocated_amount: MoneyAmount | null;
  coverage: {
    position_count: number;
    quoted_position_count: number;
    reporting_position_count: number;
    quote_sources: string[];
  };
  risk: {
    findings: Array<{
      code: string;
      severity: "info" | "medium" | "high";
      title: string;
      detail: string;
      symbols: string[];
    }>;
    trade_actions_allowed: false;
  };
  readiness: InvestmentReadinessAssessment;
  limitations: string[];
  trade_actions_allowed: false;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${getApiBaseUrl()}${path}`, init);
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail ?? "Investment research request failed");
  }
  return payload as T;
}

export function fetchWatchlist(userId: string): Promise<WatchlistItem[]> {
  return request(`/investment-research/${encodeURIComponent(userId)}/watchlist`);
}

export function followInstrument(
  userId: string,
  symbol: string,
  assetType: MarketAssetType
): Promise<WatchlistItem> {
  return request(`/investment-research/${encodeURIComponent(userId)}/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, asset_type: assetType, note: "" }),
  });
}

export async function unfollowInstrument(
  userId: string,
  symbol: string,
  assetType: MarketAssetType
): Promise<void> {
  const params = new URLSearchParams({ asset_type: assetType });
  await request(
    `/investment-research/${encodeURIComponent(userId)}/watchlist/${encodeURIComponent(symbol)}?${params}`,
    { method: "DELETE" }
  );
}

export function fetchInstrumentResearch(
  userId: string,
  symbol: string,
  assetType: MarketAssetType,
  benchmarkSymbol = "SPY"
): Promise<InstrumentResearchSnapshot> {
  const params = new URLSearchParams({
    asset_type: assetType,
    benchmark_symbol: benchmarkSymbol,
  });
  return request(
    `/investment-research/${encodeURIComponent(userId)}/instruments/${encodeURIComponent(symbol)}?${params}`
  );
}

export function fetchScenarios(userId: string): Promise<InvestmentScenario[]> {
  return request(`/investment-research/${encodeURIComponent(userId)}/scenarios`);
}

export function createScenario(
  userId: string,
  payload: { name: string; reporting_currency: string; starting_cash_amount: number | null }
): Promise<InvestmentScenario> {
  return request(`/investment-research/${encodeURIComponent(userId)}/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchScenario(
  userId: string,
  scenarioId: string
): Promise<InvestmentScenarioDetail> {
  return request(
    `/investment-research/${encodeURIComponent(userId)}/scenarios/${encodeURIComponent(scenarioId)}`
  );
}

export function replaceScenarioPositions(
  userId: string,
  scenarioId: string,
  positions: Array<{ symbol: string; asset_type: MarketAssetType; quantity: number }>
): Promise<InvestmentScenarioDetail> {
  return request(
    `/investment-research/${encodeURIComponent(userId)}/scenarios/${encodeURIComponent(scenarioId)}/positions`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions }),
    }
  );
}

export function fetchScenarioValuation(
  userId: string,
  scenarioId: string
): Promise<ScenarioValuation> {
  return request(
    `/investment-research/${encodeURIComponent(userId)}/scenarios/${encodeURIComponent(scenarioId)}/valuation`
  );
}
