import { fireEvent, render, screen } from "@testing-library/react";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAiCostOverview, type AiCostOverview } from "../../services/financeApi";
import { AiCostExplorer } from "./AiCostExplorer";

vi.mock("../../services/financeApi", async () => {
  const actual = await vi.importActual<typeof import("../../services/financeApi")>(
    "../../services/financeApi"
  );
  return { ...actual, fetchAiCostOverview: vi.fn() };
});

beforeAll(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

afterAll(() => vi.unstubAllGlobals());

const baseOverview: AiCostOverview = {
  user_id: "demo",
  period: { date_from: "2026-07-01", date_to: "2026-07-31" },
  status: "complete",
  issues: [],
  reporting_currency: "CNY",
  coverage: {
    run_count: 1,
    billable_run_count: 1,
    complete_run_count: 1,
    partial_run_count: 0,
    provider_count: 1,
    subscription_status: "not_connected",
    latest_exchange_rate_date: "2026-07-05",
  },
  summary: {
    tracked_total: { amount: "7.200000000000", currency: "CNY" },
    api_usage_total: { amount: "7.200000000000", currency: "CNY" },
    converted_subtotal: { amount: "7.200000000000", currency: "CNY" },
    subscription_total: null,
    budget: {
      status: "on_track",
      limit: { amount: "300.000000000000", currency: "CNY" },
      utilization_percent: "2.4",
    },
  },
  trend: [
    {
      date: "2026-07-05",
      status: "complete",
      reporting_total: { amount: "7.200000000000", currency: "CNY" },
      run_count: 1,
    },
  ],
  breakdowns: {
    providers: [
      {
        key: "deepseek",
        label: "deepseek",
        reporting_total: { amount: "7.200000000000", currency: "CNY" },
        share_percent: "100.0",
        run_count: 1,
      },
    ],
    models: [],
    entrypoints: [],
  },
  items: [
    {
      request_id: "run-cost-1",
      occurred_at: "2026-07-05T12:00:00Z",
      entrypoint: "chat",
      providers: ["deepseek"],
      models: ["deepseek-chat"],
      status: "complete",
      issues: [],
      billing_totals: [{ amount: "1.000000000000", currency: "USD" }],
      reporting_total: { amount: "7.200000000000", currency: "CNY" },
      exchange_rate_snapshots: [
        {
          billing_currency: "USD",
          reporting_currency: "CNY",
          exchange_rate: "7.2",
          exchange_rate_date: "2026-07-05",
          exchange_rate_source: "test-fx",
        },
      ],
    },
  ],
};

describe("AiCostExplorer", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders audited totals and opens run-level currency evidence on demand", async () => {
    vi.mocked(fetchAiCostOverview).mockResolvedValue(baseOverview);
    render(<AiCostExplorer userId="demo" onBack={vi.fn()} />);

    await screen.findByText("本期 API 成本已完成换算");
    expect(screen.getByText("AI 订阅")).toBeTruthy();
    expect(screen.getByText("未连接")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByText("deepseek-chat").closest("button")!);

    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain("USD");
    expect(drawer.textContent).toContain("1 USD = 7.2 CNY");
    expect(drawer.textContent).toContain("run-cost-1");
  });

  it("shows an explicit empty state instead of rendering zero cost", async () => {
    vi.mocked(fetchAiCostOverview).mockResolvedValue({
      ...baseOverview,
      status: "empty",
      coverage: {
        ...baseOverview.coverage,
        run_count: 0,
        billable_run_count: 0,
        complete_run_count: 0,
        provider_count: 0,
        latest_exchange_rate_date: null,
      },
      summary: {
        tracked_total: null,
        api_usage_total: null,
        converted_subtotal: null,
        subscription_total: null,
        budget: { status: "not_configured", limit: null, utilization_percent: null },
      },
      trend: [],
      breakdowns: { providers: [], models: [], entrypoints: [] },
      items: [],
    });

    render(<AiCostExplorer userId="demo" onBack={vi.fn()} />);

    await screen.findByText("本期还没有可计费的 Agent Run");
    expect(screen.queryByText("¥0.00")).toBeNull();
    expect(screen.queryByText("￥0.00")).toBeNull();
  });

  it("marks partial coverage and withholds a fabricated aggregate", async () => {
    vi.mocked(fetchAiCostOverview).mockResolvedValue({
      ...baseOverview,
      status: "partial",
      issues: ["missing_exchange_rate"],
      coverage: {
        ...baseOverview.coverage,
        complete_run_count: 0,
        partial_run_count: 1,
        latest_exchange_rate_date: null,
      },
      summary: {
        tracked_total: null,
        api_usage_total: null,
        converted_subtotal: null,
        subscription_total: null,
        budget: { status: "unavailable", limit: null, utilization_percent: null },
      },
      trend: [
        { date: "2026-07-05", status: "partial", reporting_total: null, run_count: 1 },
      ],
      breakdowns: { providers: [], models: [], entrypoints: [] },
      items: [
        {
          ...baseOverview.items[0],
          status: "partial",
          issues: ["missing_exchange_rate"],
          reporting_total: null,
          exchange_rate_snapshots: [],
        },
      ],
    });

    render(<AiCostExplorer userId="demo" onBack={vi.fn()} />);

    await screen.findByText("成本覆盖不完整");
    expect(screen.getAllByText("数据不完整").length).toBeGreaterThan(0);
    expect(screen.getByText("待换算")).toBeTruthy();
  });
});
