import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCapabilities, updateProfile } from "../services/financeApi";
import { SettingsPage } from "./SettingsPage";

vi.mock("../services/financeApi", async () => {
  const actual = await vi.importActual<typeof import("../services/financeApi")>(
    "../services/financeApi"
  );
  return {
    ...actual,
    fetchCapabilities: vi.fn(async () => []),
    importStatement: vi.fn(),
    updateProfile: vi.fn(async () => ({})),
  };
});

const profile = {
  name: "Ryan",
  occupation: "Engineer",
  financial_goals: [],
  risk_tolerance: "moderate",
  monthly_income: 25000,
  monthly_expenses: 12000,
  assets: { cash_balance: 38000, savings: 10000 },
  preferences: {
    response_tone: "comprehensive",
    preferred_language: "en",
    evidence_level: "detailed",
  },
  cost_preferences: {
    reporting_currency: "USD",
    monthly_ai_budget: 50,
  },
};

function renderSettings(showDeveloperTools = false) {
  return render(
    <SettingsPage
      userId="demo"
      profileName="Ryan"
      profile={profile}
      apiBaseUrl="http://localhost:18000"
      transactionCount={0}
      monthlyIncome={25000}
      showDeveloperTools={showDeveloperTools}
    />
  );
}

describe("SettingsPage cost reporting preferences", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads and saves reporting currency and the monthly AI budget separately", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: /Cost Reporting/ }));

    const currency = screen.getByRole("combobox");
    const budget = screen.getByPlaceholderText("Not configured");
    expect((currency as HTMLSelectElement).value).toBe("USD");
    expect((budget as HTMLInputElement).value).toBe("50");

    fireEvent.change(currency, { target: { value: "AUD" } });
    fireEvent.change(budget, { target: { value: "75.25" } });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));

    await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateProfile).mock.calls[0][1]).toMatchObject({
      cost_preferences: {
        reporting_currency: "AUD",
        monthly_ai_budget: 75.25,
      },
    });
  });

  it("persists an empty budget as null instead of fabricating zero spend", async () => {
    renderSettings();
    fireEvent.click(screen.getByRole("button", { name: /Cost Reporting/ }));

    fireEvent.change(screen.getByPlaceholderText("Not configured"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));

    await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateProfile).mock.calls[0][1].cost_preferences).toEqual({
      reporting_currency: "USD",
      monthly_ai_budget: null,
    });
  });
});

describe("SettingsPage developer capabilities", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hides developer controls unless explicitly enabled", () => {
    renderSettings();

    expect(
      screen.queryByRole("button", { name: /^Developer$/ })
    ).toBeNull();
    expect(fetchCapabilities).not.toHaveBeenCalled();
  });

  it("renders the read-only capability state from the backend catalog", async () => {
    vi.mocked(fetchCapabilities).mockResolvedValueOnce([
      {
        descriptor: {
          capability_id: "investment.external_market_history",
          kind: "tool",
          title: "External market history",
          description: "Bounded external market evidence.",
          source: "mcp",
          owner: "investment_research",
          risk_level: "medium",
          execution_mode: "read_only",
          input_contract: "AgentContextPayload",
          output_contract: "ExternalMarketHistoryArtifact",
        },
        status: {
          enabled: true,
          available: false,
          reason: "MCP discovery failed: McpInvocationError",
          checked_at: "2026-07-21T12:00:00Z",
        },
      },
    ]);
    renderSettings(true);

    fireEvent.click(screen.getByRole("button", { name: /^Developer$/ }));

    expect(await screen.findByText("External market history")).toBeTruthy();
    expect(screen.getByText("unhealthy")).toBeTruthy();
    expect(screen.getByText("investment.external_market_history")).toBeTruthy();
    expect(fetchCapabilities).toHaveBeenCalledTimes(1);
  });
});
