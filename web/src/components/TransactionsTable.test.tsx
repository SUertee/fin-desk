import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "../i18n";
import type { TransactionRow } from "../types/db";
import { toTableTransactions } from "../utils/financeTransforms";
import { TransactionsTable } from "./TransactionsTable";

const base: TransactionRow = {
  id: "bank-1",
  user_id: "demo",
  date: "2026-09-05",
  month: "2026-09",
  description: "消费",
  counterparty: "消费",
  amount: -71.75,
  currency: "CNY",
  balance: 1949.16,
  type: "statement_import",
  category: "other",
  source: "bank_icbc",
  payment_method: "快捷支付",
  is_duplicate: false,
  source_file: "bank.pdf",
  raw: { row: { summary: "消费" } },
};

describe("TransactionsTable transaction details", () => {
  beforeEach(() => localStorage.setItem("findesk-lang", "zh"));

  it("uses a matched wallet record to explain a generic bank transaction", () => {
    const wallet: TransactionRow = {
      ...base,
      id: "wallet-1",
      counterparty: "示例超市",
      description: "订单号支付",
      source: "alipay",
      payment_method: "工商银行储蓄卡",
      category: "groceries",
      is_duplicate: true,
      duplicate_of: "bank-1",
      external_id: "wallet-order-1",
      source_file: "alipay.csv",
      raw: { row: { 交易对方: "示例超市", 商品说明: "订单号支付" } },
    };

    render(<I18nProvider><TransactionsTable transactions={toTableTransactions([base, wallet])} /></I18nProvider>);

    const transactionButton = screen.getByRole("button", { name: /示例超市.*订单号支付/ });
    expect(transactionButton).toBeTruthy();
    fireEvent.click(transactionButton);

    const dialog = screen.getByRole("dialog", { name: "交易详情" });
    expect(within(dialog).getByText("工商银行 · 关联 支付宝")).toBeTruthy();
    expect(within(dialog).getByText("买菜日用")).toBeTruthy();
    expect(within(dialog).getByText("关联账单凭据")).toBeTruthy();
    expect(within(dialog).getByText("wallet-order-1")).toBeTruthy();
  });

  it("labels a record honestly when no merchant detail exists", () => {
    render(<I18nProvider><TransactionsTable transactions={toTableTransactions([base])} /></I18nProvider>);
    expect(screen.getByRole("button", { name: "未识别商户" })).toBeTruthy();
  });
});
