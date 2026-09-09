/**
 * Pure derivations from loaded transactions/analysis runs into the view
 * models the workspace renders. No fetching, no React — keep these testable.
 */
import type { TransactionRow } from "../types/db";

// 小工具：把 number 控制到 2 位，避免 43.760000000000005 这种
export function round2(n: number) {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

export type MonthlyTotal = {
  month: string; // "2025-03"
  income: number;
  expense: number;
  net: number;
  count: number;
};

function isActualLedgerActivity(t: TransactionRow) {
  return !t.is_duplicate && !(t.source === "bank_icbc" && t.category === "transfer");
}

export function computeMonthlyTotalsFromTxs(txs: TransactionRow[]): MonthlyTotal[] {
  const map = new Map<string, MonthlyTotal>();

  for (const t of txs) {
    if (!isActualLedgerActivity(t)) continue;
    const month = t.month || (t.date ? t.date.slice(0, 7) : "unknown");
    const amt = Number(t.amount || 0);

    const row =
      map.get(month) ??
      ({
        month,
        income: 0,
        expense: 0,
        net: 0,
        count: 0,
      } satisfies MonthlyTotal);

    if (amt > 0) row.income += amt;
    else row.expense += Math.abs(amt);

    row.count += 1;
    map.set(month, row);
  }

  const res = Array.from(map.values())
    .sort((a, b) => a.month.localeCompare(b.month))
    .map((m) => {
      const income = round2(m.income);
      const expense = round2(m.expense);
      return {
        ...m,
        income,
        expense,
        net: round2(income - expense),
      };
    });

  return res;
}

// summary：给 MetricsCards（按币种分组，排除重复）
export function summarizeByCurrency(txs: TransactionRow[]) {
  const map: Record<string, { income: number; expense: number }> = {};
  for (const t of txs) {
    if (!isActualLedgerActivity(t)) continue;
    const cur = t.currency || "CNY";
    if (!map[cur]) map[cur] = { income: 0, expense: 0 };
    const amt = Number(t.amount || 0);
    if (amt > 0) map[cur].income += amt;
    else map[cur].expense += Math.abs(amt);
  }
  return Object.entries(map).map(([currency, v]) => ({
    currency,
    income: round2(v.income),
    expense: round2(v.expense),
    net: round2(v.income - v.expense),
  }));
}

export function toMonthlyTrendsData(monthlyTotals: MonthlyTotal[]) {
  return monthlyTotals.map((m) => ({
    month: m.month,
    income: m.income,
    expenses: m.expense,
  }));
}

export function toTableTransactions(txs: TransactionRow[]) {
  const linkedByCanonicalId = new Map<string, TransactionRow[]>();
  for (const transaction of txs) {
    if (!transaction.duplicate_of) continue;
    const linked = linkedByCanonicalId.get(String(transaction.duplicate_of)) ?? [];
    linked.push(transaction);
    linkedByCanonicalId.set(String(transaction.duplicate_of), linked);
  }

  const generic = new Set(["", "—", "消费", "支出", "付款", "交易", "payment", "purchase"]);
  const detailScore = (transaction: TransactionRow) => {
    const counterparty = (transaction.counterparty ?? "").trim().toLocaleLowerCase();
    const description = (transaction.description ?? "").trim().toLocaleLowerCase();
    return (generic.has(counterparty) ? 0 : 2) + (generic.has(description) ? 0 : 1);
  };

  return txs.map((t, index) => ({
    ...(() => {
      const linked = linkedByCanonicalId.get(String(t.id ?? "")) ?? [];
      const detail = [...linked].sort((a, b) => detailScore(b) - detailScore(a))[0];
      const ownCounterparty = (t.counterparty ?? "").trim();
      const ownDescription = (t.description ?? "").trim();
      const merchant = generic.has(ownCounterparty.toLocaleLowerCase())
        ? (detail?.counterparty || detail?.description || ownCounterparty || ownDescription || "—")
        : ownCounterparty;
      const description = generic.has(ownDescription.toLocaleLowerCase())
        ? (detail?.description || ownDescription)
        : ownDescription;
      const ownCategory = (t.category ?? "").trim();
      const category = ["", "other", "uncategorized", "其他"].includes(ownCategory.toLocaleLowerCase())
        ? (detail?.category || ownCategory || "Uncategorized")
        : ownCategory;
      return {
        merchant,
        description,
        category,
        matched_sources: Array.from(new Set(linked.map((item) => item.source).filter(Boolean))) as string[],
        matched_source_file: detail?.source_file ?? "",
        matched_external_id: detail?.external_id ?? "",
        matched_merchant_order_id: detail?.merchant_order_id ?? "",
        matched_raw: detail?.raw ?? null,
      };
    })(),
    id: t.id ?? String(index + 1),
    date: t.date ?? "—",
    month: t.month ?? t.date?.slice(0, 7) ?? "—",
    amount: Number(t.amount ?? 0),
    gross_amount: Number((t as TransactionRow & { gross_amount?: number }).gross_amount ?? Math.abs(Number(t.amount ?? 0))),
    currency: t.currency ?? "CNY",
    source: t.source ?? "manual",
    payment_method: t.payment_method ?? "",
    status: t.status ?? "",
    direction: t.direction ?? "",
    type: t.type ?? "",
    created_at: t.created_at ?? "",
    note: t.note ?? "",
    external_id: t.external_id ?? "",
    merchant_order_id: t.merchant_order_id ?? "",
    source_file: t.source_file ?? "",
    raw: t.raw ?? null,
    is_duplicate: t.is_duplicate ?? false,
  }));
}

// Source breakdown data
export function computeSourceBreakdown(txs: TransactionRow[]) {
  const map: Record<string, Record<string, { count: number; income: number; expense: number }>> = {};
  for (const t of txs) {
    const src = t.source || "manual";
    const cur = t.currency || "CNY";
    if (!map[src]) map[src] = {};
    if (!map[src][cur]) map[src][cur] = { count: 0, income: 0, expense: 0 };
    map[src][cur].count++;
    const amt = Number(t.amount || 0);
    if (amt > 0) map[src][cur].income += amt;
    else map[src][cur].expense += Math.abs(amt);
  }
  const items: { source: string; currency: string; count: number; income: number; expense: number }[] = [];
  for (const [source, currencies] of Object.entries(map)) {
    for (const [currency, v] of Object.entries(currencies)) {
      items.push({ source, currency, count: v.count, income: round2(v.income), expense: round2(v.expense) });
    }
  }
  return items;
}

// Category pie chart data (expenses only, excluding duplicates)
export function computeCategoryData(txs: TransactionRow[]) {
  const catMap: Record<string, { amount: number; currency: string }> = {};
  for (const t of txs) {
    if (!isActualLedgerActivity(t)) continue;
    const amt = Number(t.amount || 0);
    if (amt >= 0) continue;
    const cat = t.category || "其他";
    const cur = t.currency || "CNY";
    const key = `${cat}|${cur}`;
    if (!catMap[key]) catMap[key] = { amount: 0, currency: cur };
    catMap[key].amount += Math.abs(amt);
  }
  return Object.entries(catMap).map(([key, v]) => ({
    category: key.split("|")[0],
    amount: round2(v.amount),
    currency: v.currency,
  }));
}

export function computeCurrentMonthExpense(txs: TransactionRow[], currentMonth: string) {
  let total = 0;
  for (const t of txs) {
    if (!isActualLedgerActivity(t)) continue;
    const m = t.month || t.date?.slice(0, 7);
    if (m !== currentMonth) continue;
    const amt = Number(t.amount || 0);
    if (amt < 0) total += Math.abs(amt);
  }
  return round2(total);
}

// Category comparison: current month vs historical average (excluding duplicates)
export function computeCategoryComparison(txs: TransactionRow[], currentMonth: string) {
  const months: Record<string, Record<string, number>> = {};
  for (const t of txs) {
    if (!isActualLedgerActivity(t)) continue;
    const amt = Number(t.amount || 0);
    if (amt >= 0) continue;
    const m = t.month || t.date?.slice(0, 7) || "unknown";
    const cat = t.category || "其他";
    if (!months[m]) months[m] = {};
    months[m][cat] = (months[m][cat] || 0) + Math.abs(amt);
  }
  const allMonths = Object.keys(months).sort();
  const pastMonths = allMonths.filter((m) => m !== currentMonth);
  const currentData = months[currentMonth] || {};

  // Calculate average per category across past months
  const catTotals: Record<string, { total: number; count: number }> = {};
  for (const m of pastMonths) {
    for (const [cat, amt] of Object.entries(months[m])) {
      if (!catTotals[cat]) catTotals[cat] = { total: 0, count: 0 };
      catTotals[cat].total += amt;
      catTotals[cat].count++;
    }
  }

  const allCats = new Set([...Object.keys(currentData), ...Object.keys(catTotals)]);
  return Array.from(allCats)
    .map((cat) => ({
      category: cat,
      currentMonth: round2(currentData[cat] || 0),
      average: catTotals[cat] ? round2(catTotals[cat].total / catTotals[cat].count) : 0,
      currency: "CNY",
    }))
    .filter((d) => d.currentMonth > 0 || d.average > 0);
}

export function buildReportText(reportOutput: Record<string, any> | null): string | null {
  if (!reportOutput || Object.keys(reportOutput).length === 0) return null;
  const lines: string[] = [];
  const insights = reportOutput.insights ?? reportOutput.summary ?? null;
  if (Array.isArray(insights)) {
    lines.push("Insights:", ...insights.map((item: any) => `• ${typeof item === "string" ? item : item?.title ?? JSON.stringify(item)}`));
  } else if (typeof insights === "string") {
    lines.push(insights);
  }
  const reportActions = reportOutput.actions ?? reportOutput.recommendations ?? null;
  if (Array.isArray(reportActions) && reportActions.length > 0) {
    lines.push("", "Actions:", ...reportActions.map((item: any) => `• ${typeof item === "string" ? item : item?.title ?? JSON.stringify(item)}`));
  }
  if (reportOutput.budget) {
    lines.push("", `Budget: ${typeof reportOutput.budget === "string" ? reportOutput.budget : JSON.stringify(reportOutput.budget)}`);
  }
  return lines.length ? lines.join("\n") : null;
}
