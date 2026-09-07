import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InvestmentResearchPage } from "./InvestmentResearchPage";
import {
  fetchInstrumentResearch,
  fetchScenarios,
  fetchWatchlist,
} from "../services/investmentResearchApi";


vi.mock("../services/investmentResearchApi", () => ({
  fetchWatchlist: vi.fn(async () => []),
  fetchScenarios: vi.fn(async () => []),
  fetchInstrumentResearch: vi.fn(),
  fetchScenario: vi.fn(),
  fetchScenarioValuation: vi.fn(),
  followInstrument: vi.fn(),
  unfollowInstrument: vi.fn(),
  createScenario: vi.fn(),
  replaceScenarioPositions: vi.fn(),
}));

const watchlistItem = {
  user_id: "demo",
  symbol: "AAPL",
  asset_type: "equity" as const,
  note: "",
  created_at: "2026-07-19T10:00:00Z",
  updated_at: "2026-07-19T10:00:00Z",
};

const snapshot = {
  user_id: "demo",
  symbol: "AAPL",
  asset_type: "equity" as const,
  followed: true,
  profile: {
    symbol: "AAPL",
    name: "Apple Inc.",
    venue: "NASDAQ",
    currency: "USD",
    sector: "Technology",
    industry: "Consumer Electronics",
    country: "United States",
    source: "openbb:yfinance",
    fetched_at: "2026-07-19T10:00:00Z",
  },
  quote: {
    symbol: "AAPL",
    asset_type: "equity" as const,
    price: { amount: "210.50", currency: "USD" },
    quote_as_of: "2026-07-19T10:00:00Z",
    timestamp_basis: "provider_time" as const,
    source: "openbb:yfinance",
    venue: "NASDAQ",
  },
  history: {
    provider: "openbb:yfinance",
    currency: "USD",
    date_from: "2026-07-17",
    date_to: "2026-07-19",
    fetched_at: "2026-07-19T10:00:00Z",
    bars: [
      { period: "2026-07-17", close: { amount: "200", currency: "USD" } },
      { period: "2026-07-18", close: { amount: "210.5", currency: "USD" } },
    ],
  },
  performance: {
    status: "available" as const,
    symbol: "AAPL",
    currency: "USD",
    observation_count: 2,
    date_from: "2026-07-17",
    date_to: "2026-07-18",
    period_return_percent: "5.25",
    annualized_volatility_percent: "12.34",
    max_drawdown_percent: "3.20",
  },
  benchmark: {
    status: "available" as const,
    benchmark_symbol: "SPY",
    performance: {
      status: "available" as const,
      symbol: "SPY",
      currency: "USD",
      observation_count: 2,
      date_from: "2026-07-17",
      date_to: "2026-07-18",
      period_return_percent: "3.15",
      annualized_volatility_percent: "9.20",
      max_drawdown_percent: "1.40",
    },
    excess_period_return_percent: "2.10",
    limitation: null,
  },
  readiness: {
    status: "caution" as const,
    reporting_currency: "CNY",
    monthly_cash_flow: "2500.00",
    liquid_reserve: { amount: "24000.00", currency: "CNY" },
    reserve_months: "2.40",
    liabilities: { amount: "0.00", currency: "CNY" },
    risk_tolerance: "moderate",
    findings: [
      {
        code: "low_liquid_reserve",
        severity: "medium" as const,
        title: "Liquid reserve is below three months",
        detail: "Configured cash and savings cover 2.40 months of recurring expenses.",
      },
    ],
    limitations: ["Readiness is not investment suitability."],
    trade_actions_allowed: false as const,
  },
  evidence: [
    {
      kind: "quote" as const,
      source: "openbb:yfinance",
      as_of: "2026-07-19T10:00:00Z",
      description: "Latest normalized market quote",
    },
    {
      kind: "benchmark_history" as const,
      source: "openbb:yfinance",
      as_of: "2026-07-19T10:00:00Z",
      description: "SPY normalized benchmark history",
    },
  ],
  limitations: ["Research is read-only and does not place brokerage orders."],
  trade_actions_allowed: false as const,
};

describe("InvestmentResearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWatchlist).mockResolvedValue([]);
    vi.mocked(fetchScenarios).mockResolvedValue([]);
  });

  it("renders an honest empty state without fake prices or an evidence drawer", async () => {
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);

    await screen.findByText("还没有关注标的。");
    expect(screen.getByText(/这里不会显示虚构行情/)).toBeTruthy();
    expect(screen.queryByText("EVIDENCE")).toBeNull();
    expect(screen.queryByText(/210\.50/)).toBeNull();
  });

  it("opens sourced evidence only after the user requests it", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([watchlistItem]);
    vi.mocked(fetchInstrumentResearch).mockResolvedValue(snapshot);
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);

    fireEvent.click(await screen.findByText("AAPL"));
    await screen.findByText("Apple Inc.");
    expect(screen.queryByText("EVIDENCE")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /2 (sources|个来源)/i }));
    await screen.findByText("EVIDENCE");
    expect(screen.getAllByText("openbb:yfinance").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/not an executable quote/i)).toBeTruthy();
  });

  it("separates performance, benchmark, and personal readiness", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([watchlistItem]);
    vi.mocked(fetchInstrumentResearch).mockResolvedValue(snapshot);
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);

    fireEvent.click(await screen.findByText("AAPL"));
    await screen.findByText("Apple Inc.");

    expect(screen.getAllByText("+5.25%")).toHaveLength(2);
    expect(screen.getByText("12.34%")).toBeTruthy();
    expect(screen.getByText("3.20%")).toBeTruthy();
    expect(screen.getByText("AAPL vs SPY")).toBeTruthy();
    expect(screen.getByText("+2.10%")).toBeTruthy();
    expect(screen.getByText("Liquid reserve is below three months")).toBeTruthy();
    expect(screen.getByText(/不是适合度判断/)).toBeTruthy();
  });

  it("renders insufficient history as unavailable rather than zero", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([watchlistItem]);
    vi.mocked(fetchInstrumentResearch).mockResolvedValue({
      ...snapshot,
      performance: {
        ...snapshot.performance,
        status: "insufficient_data",
        observation_count: 1,
        period_return_percent: null,
        annualized_volatility_percent: null,
        max_drawdown_percent: null,
      },
      benchmark: {
        status: "insufficient_data",
        benchmark_symbol: "SPY",
        performance: null,
        excess_period_return_percent: null,
        limitation: "Benchmark history is not sufficient for this period.",
      },
    });
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);

    fireEvent.click(await screen.findByText("AAPL"));
    await screen.findByText("Apple Inc.");

    expect(screen.getAllByText("Not enough data")).toHaveLength(3);
    expect(screen.queryByText("0.00%")).toBeNull();
    expect(screen.getByText("暂时无法进行可靠比较")).toBeTruthy();
  });

  it("hands the CFO an explicit investment-research prompt", async () => {
    const onAskCfo = vi.fn();
    vi.mocked(fetchWatchlist).mockResolvedValue([watchlistItem]);
    vi.mocked(fetchInstrumentResearch).mockResolvedValue(snapshot);
    render(<InvestmentResearchPage userId="demo" onAskCfo={onAskCfo} />);

    fireEvent.click(await screen.findByText("AAPL"));
    await screen.findByText("Apple Inc.");
    fireEvent.click(screen.getByRole("button", { name: /(Ask|询问) CFO/i }));

    expect(onAskCfo).toHaveBeenCalledWith(expect.stringContaining("股票标的 AAPL"));
  });

  it("labels scenario work as hypothetical and disconnected from real capital", async () => {
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);
    await waitFor(() => expect(fetchScenarios).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /假设场景/ }));

    expect(screen.getByText(/不连接券商、不使用真实资金/)).toBeTruthy();
    expect(screen.getByText(/Hypothetical only|仅供假设分析/)).toBeTruthy();
  });
});
