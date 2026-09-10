import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n";
import { fetchCashPlan } from "../services/financeApi";
import { FinanceWorkspacePage } from "./FinanceWorkspacePage";

vi.mock("../services/financeApi", async (importOriginal) => {
  const original = await importOriginal<typeof import("../services/financeApi")>();
  return { ...original, fetchCashPlan: vi.fn().mockRejectedValue(new Error("no plan")) };
});

describe("FinanceWorkspacePage quick bookkeeping", () => {
  beforeEach(() => localStorage.setItem("findesk-lang", "zh"));

  it("turns a breakfast reminder into a manual ledger entry", async () => {
    const createTransaction = vi.fn().mockResolvedValue(undefined);
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo"
          loading={false}
          errMsg={null}
          isUploading={false}
          primaryCurrency="CNY"
          tableTransactions={[]}
          onReload={vi.fn()}
          onOpenLedger={vi.fn()}
          onOpenCashPlan={vi.fn()}
          onUploadStatement={vi.fn()}
          onCreateManualTransaction={createTransaction}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /早餐.*快速记录/ }));
    fireEvent.change(screen.getByLabelText(/金额/), { target: { value: "12.5" } });
    fireEvent.change(screen.getByLabelText(/商户/), { target: { value: "公司食堂" } });
    fireEvent.click(screen.getByRole("button", { name: "保存到流水" }));

    await waitFor(() => expect(createTransaction).toHaveBeenCalledTimes(1));
    expect(createTransaction).toHaveBeenCalledWith(expect.objectContaining({
      amount: 12.5,
      direction: "expense",
      entry_type: "expense",
      counterparty: "公司食堂",
      description: "早餐",
      category: "dining",
      payment_method: "支付宝",
      meal_tag: "breakfast",
      template_id: "breakfast",
    }));
    expect(createTransaction.mock.calls[0][0].occurred_at).toMatch(/[+-]\d{2}:\d{2}$/);
  });

  it("offers one generic entry flow for expense, income, refund and transfer", () => {
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo" loading={false} errMsg={null} isUploading={false}
          primaryCurrency="CNY" tableTransactions={[]} onReload={vi.fn()}
          onOpenLedger={vi.fn()} onOpenCashPlan={vi.fn()} onUploadStatement={vi.fn()}
          onCreateManualTransaction={vi.fn().mockResolvedValue(undefined)}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "记一笔" }));
    expect(screen.getByRole("button", { name: "支出" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "收入" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "退款" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "转账" })).toBeTruthy();
  });

  it("never presents a missing cash plan as a real zero amount", async () => {
    vi.mocked(fetchCashPlan).mockResolvedValueOnce({
      configured: false,
      plan: null,
      projection: null,
    });
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo" loading={false} errMsg={null} isUploading={false}
          primaryCurrency="CNY" tableTransactions={[]} onReload={vi.fn()}
          onOpenLedger={vi.fn()} onOpenCashPlan={vi.fn()} onUploadStatement={vi.fn()}
          onCreateManualTransaction={vi.fn().mockResolvedValue(undefined)}
        />
      </I18nProvider>,
    );

    await screen.findByText("先完善现金计划");
    const availableCash = screen.getByText("当前可用现金").parentElement;
    expect(availableCash?.querySelector("strong")?.textContent).toBe("—");
    expect(screen.getByText("计划尚未设置")).toBeTruthy();
  });

  it("shows an unavailable state when the plan request fails", async () => {
    vi.mocked(fetchCashPlan).mockRejectedValueOnce(new Error("offline"));
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo" loading={false} errMsg={null} isUploading={false}
          primaryCurrency="CNY" tableTransactions={[]} onReload={vi.fn()}
          onOpenLedger={vi.fn()} onOpenCashPlan={vi.fn()} onUploadStatement={vi.fn()}
          onCreateManualTransaction={vi.fn().mockResolvedValue(undefined)}
        />
      </I18nProvider>,
    );

    await screen.findByText("现金计划暂时无法读取");
    expect(screen.getByText("系统没有用默认金额代替缺失数据，请稍后重试。")).toBeTruthy();
  });

  it("labels the next essential payment instead of an earlier optional purchase", async () => {
    vi.mocked(fetchCashPlan).mockResolvedValueOnce({
      configured: true,
      plan: {
        user_id: "demo", currency: "CNY", cash_balance: 1800,
        daily_budget: 35, monthly_budget: 1800, entries: [], updated_at: "2026-09-10T00:00:00Z",
      },
      projection: {
        as_of: "2026-09-10", horizon_end: "2026-10-10", currency: "CNY",
        current_cash: 1800, total_debt: 1000, next_income_date: "2026-09-15",
        safe_to_spend_until_next_income: 1625, minimum_projected_balance: 0,
        funding_gap: 0, ending_balance: 100,
        events: [
          { entry_id: "gym", name: "健身房月卡", kind: "purchase", date: "2026-09-11", amount: -450, essential: false, running_balance: 1350 },
          { entry_id: "rent", name: "房租", kind: "housing", date: "2026-09-12", amount: -1000, essential: true, running_balance: 350 },
        ],
      },
    });
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo" loading={false} errMsg={null} isUploading={false}
          primaryCurrency="CNY" tableTransactions={[]} onReload={vi.fn()}
          onOpenLedger={vi.fn()} onOpenCashPlan={vi.fn()} onUploadStatement={vi.fn()}
          onCreateManualTransaction={vi.fn().mockResolvedValue(undefined)}
        />
      </I18nProvider>,
    );

    await screen.findByText("¥1,000");
    expect(screen.getByText("房租 · 9 月 12 日 · 还有 2 天")).toBeTruthy();
  });

  it("moves actionable reminders out of the page body", async () => {
    const onAttentionChange = vi.fn();
    render(
      <I18nProvider>
        <FinanceWorkspacePage
          userId="demo" loading={false} errMsg={null} isUploading={false}
          primaryCurrency="CNY" tableTransactions={[]} onReload={vi.fn()}
          onOpenLedger={vi.fn()} onOpenCashPlan={vi.fn()} onUploadStatement={vi.fn()}
          onCreateManualTransaction={vi.fn().mockResolvedValue(undefined)}
          onAttentionChange={onAttentionChange}
        />
      </I18nProvider>,
    );

    await waitFor(() => expect(onAttentionChange).toHaveBeenCalledWith([
      expect.objectContaining({ id: "first-import", actionTarget: "upload" }),
    ]));
    expect(screen.queryByText("需要处理")).toBeNull();
  });
});
