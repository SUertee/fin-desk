import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { updateProfile } from "../services/financeApi";
import { SettingsPage } from "./SettingsPage";

vi.mock("../services/financeApi", async () => {
  const actual = await vi.importActual<typeof import("../services/financeApi")>(
    "../services/financeApi"
  );
  return {
    ...actual,
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

function renderSettings() {
  return render(
    <SettingsPage
      userId="demo"
      profileName="Ryan"
      profile={profile}
      apiBaseUrl="http://localhost:18000"
      transactionCount={0}
      monthlyIncome={25000}
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
