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
  evidence: [
    {
      kind: "quote" as const,
      source: "openbb:yfinance",
      as_of: "2026-07-19T10:00:00Z",
      description: "Latest normalized market quote",
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

    fireEvent.click(screen.getByRole("button", { name: /1 sources/i }));
    await screen.findByText("EVIDENCE");
    expect(screen.getAllByText("openbb:yfinance").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/not an executable quote/i)).toBeTruthy();
  });

  it("hands the CFO an explicit investment-research prompt", async () => {
    const onAskCfo = vi.fn();
    vi.mocked(fetchWatchlist).mockResolvedValue([watchlistItem]);
    vi.mocked(fetchInstrumentResearch).mockResolvedValue(snapshot);
    render(<InvestmentResearchPage userId="demo" onAskCfo={onAskCfo} />);

    fireEvent.click(await screen.findByText("AAPL"));
    await screen.findByText("Apple Inc.");
    fireEvent.click(screen.getByRole("button", { name: /Ask CFO/i }));

    expect(onAskCfo).toHaveBeenCalledWith(expect.stringContaining("股票标的 AAPL"));
  });

  it("labels scenario work as hypothetical and disconnected from real capital", async () => {
    render(<InvestmentResearchPage userId="demo" onAskCfo={vi.fn()} />);
    await waitFor(() => expect(fetchScenarios).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /假设场景/ }));

    expect(screen.getByText(/不连接券商、不使用真实资金/)).toBeTruthy();
    expect(screen.getByText("Hypothetical only")).toBeTruthy();
  });
});
