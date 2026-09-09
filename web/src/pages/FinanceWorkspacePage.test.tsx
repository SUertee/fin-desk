import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n";
import { FinanceWorkspacePage } from "./FinanceWorkspacePage";
import { saveAccountBalances } from "../services/financeApi";

vi.mock("../services/financeApi", async (importOriginal) => {
  const original = await importOriginal<typeof import("../services/financeApi")>();
  return {
    ...original,
    fetchCashPlan: vi.fn().mockRejectedValue(new Error("no plan")),
    fetchAccountBalances: vi.fn().mockResolvedValue({
      user_id: "demo", currency: "CNY", items: [], total: 0, confirmed_at: null,
    }),
    saveAccountBalances: vi.fn().mockResolvedValue({
      user_id: "demo", currency: "CNY", total: 1800,
      confirmed_at: "2026-09-09T10:00:00Z",
      items: [
        { account_type: "bank", amount: 1800, currency: "CNY", confirmed_at: "2026-09-09T10:00:00Z" },
        { account_type: "alipay", amount: 0, currency: "CNY", confirmed_at: "2026-09-09T10:00:00Z" },
        { account_type: "wechat", amount: 0, currency: "CNY", confirmed_at: "2026-09-09T10:00:00Z" },
        { account_type: "cash", amount: 0, currency: "CNY", confirmed_at: "2026-09-09T10:00:00Z" },
      ],
    }),
  };
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

  it("confirms four account balances as the cash projection baseline", async () => {
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

    fireEvent.click(screen.getAllByRole("button", { name: "更新余额" })[0]);
    fireEvent.change(screen.getByLabelText("银行卡"), { target: { value: "1800" } });
    fireEvent.change(screen.getByLabelText("支付宝余额"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("微信余额"), { target: { value: "80" } });
    fireEvent.change(screen.getByLabelText("现金"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "确认余额并重新计算" }));

    await waitFor(() => expect(saveAccountBalances).toHaveBeenCalledWith("demo", {
      bank: 1800, alipay: 20, wechat: 80, cash: 100, currency: "CNY",
    }));
  });
});
