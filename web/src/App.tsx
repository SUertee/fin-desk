import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTransactions,
  fetchLatestAnalysisRun,
  fetchProfile,
} from "./services/supabaseApi";
import type { AnalysisRunRow, TransactionRow } from "./types/db";

import { Header } from "./components/Header";
import { AgentTeamPanel } from "./components/AgentTeamPanel";
import { MetricsCards } from "./components/MetricsCards";
import { MonthlyTrends } from "./components/MonthlyTrends";
import { TransactionsTable } from "./components/TransactionsTable";
import { SourceBreakdown } from "./components/SourceBreakdown";
import { CategoryPieChart } from "./components/CategoryPieChart";
import { IncomeSummary } from "./components/IncomeSummary";
import { CategoryComparison } from "./components/CategoryComparison";
import { OperatingSummary } from "./components/OperatingSummary";

// 小工具：把 number 控制到 2 位，避免 43.760000000000005 这种
function round2(n: number) {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

type MonthlyTotal = {
  month: string; // "2025-03"
  income: number;
  expense: number;
  net: number;
  count: number;
};

function computeMonthlyTotalsFromTxs(txs: TransactionRow[]): MonthlyTotal[] {
  const map = new Map<string, MonthlyTotal>();

  for (const t of txs) {
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

export default function App() {
  // TODO: Replace hardcoded "demo" with auth-based user identification
  const userId = "demo";

  const [monthlyIncome, setMonthlyIncome] = useState(0);
  const [txs, setTxs] = useState<TransactionRow[]>([]);
  const [monthlyTotalsFromRun, setMonthlyTotalsFromRun] = useState<
    MonthlyTotal[] | null
  >(null);
  const [latestRun, setLatestRun] = useState<AnalysisRunRow | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErrMsg(null);

    try {
      const [transactions, latestRunResponse, profile] = await Promise.all([
        fetchTransactions(userId, 2000),
        fetchLatestAnalysisRun(userId),
        fetchProfile(userId),
      ]);

      setMonthlyIncome(profile.monthly_income || 0);

      console.log("[api] transactions:", transactions);
      console.log("[api] latestRun:", latestRunResponse);

      setTxs(transactions);
      setLatestRun(latestRunResponse ?? null);

      // 这里兼容你两种存法：analysis_runs.output.monthly_totals 或 analysis_runs.monthly_totals
      const totals =
        (latestRunResponse?.output?.monthly_totals as MonthlyTotal[] | undefined) ??
        (latestRunResponse?.monthly_totals as MonthlyTotal[] | undefined) ??
        null;

      setMonthlyTotalsFromRun(totals);
    } catch (e: any) {
      setErrMsg(e?.message ?? "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const handleUploadStatement = useCallback(
    async (file: File) => {
      const webhookUrl = import.meta.env.VITE_N8N_WEBHOOK_URL as
        | string
        | undefined;

      if (!webhookUrl) {
        setErrMsg("Missing VITE_N8N_WEBHOOK_URL in your env.");
        return;
      }

      setIsUploading(true);
      setErrMsg(null);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("user_id", userId || "");

        const response = await fetch(webhookUrl, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || "Upload failed");
        }

        await load();
      } catch (e: any) {
        setErrMsg(e?.message ?? "Upload failed");
      } finally {
        setIsUploading(false);
      }
    },
    [load, userId]
  );

  useEffect(() => {
    let mounted = true;

    (async () => {
      // 防止 StrictMode 下重复触发造成奇怪状态
      try {
        await load();
      } finally {
        if (!mounted) return;
      }
    })();

    return () => {
      mounted = false;
    };
  }, [load]);

  // ✅ monthlyTotals：优先用后端分析结果；没有就从 txs 计算
  const monthlyTotals: MonthlyTotal[] = useMemo(() => {
    if (monthlyTotalsFromRun && monthlyTotalsFromRun.length > 0) {
      return monthlyTotalsFromRun;
    }
    return computeMonthlyTotalsFromTxs(txs);
  }, [monthlyTotalsFromRun, txs]);

  // ✅ summary：给 MetricsCards（按币种分组，排除重复）
  const summaryByCurrency = useMemo(() => {
    const map: Record<string, { income: number; expense: number }> = {};
    for (const t of txs) {
      if (t.is_duplicate) continue;
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
  }, [txs]);

  const monthlyTrendsData = useMemo(
    () =>
      monthlyTotals.map((m) => ({
        month: m.month,
        income: m.income,
        expenses: m.expense,
      })),
    [monthlyTotals]
  );

  const tableTransactions = useMemo(
    () =>
      txs.map((t, index) => ({
        id: t.id ?? String(index + 1),
        date: t.date ?? "—",
        month: t.month ?? t.date?.slice(0, 7) ?? "—",
        merchant: t.description ?? "—",
        category: t.category ?? "Uncategorized",
        amount: Number(t.amount ?? 0),
        currency: t.currency ?? "CNY",
        source: t.source ?? "manual",
        payment_method: t.payment_method ?? "",
        is_duplicate: t.is_duplicate ?? false,
      })),
    [txs]
  );

  // Source breakdown data
  const sourceData = useMemo(() => {
    const map: Record<string, Record<string, { count: number; income: number; expense: number }>> = {};
    for (const t of txs) {
      const src = t.source || "manual";
      const cur = t.currency || "CNY";
      const key = `${src}:${cur}`;
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
  }, [txs]);

  // Category pie chart data (expenses only, excluding duplicates)
  const categoryData = useMemo(() => {
    const catMap: Record<string, { amount: number; currency: string }> = {};
    for (const t of txs) {
      if (t.is_duplicate) continue;
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
  }, [txs]);

  // Current month for income summary
  const currentMonth = new Date().toISOString().slice(0, 7);
  const currentMonthExpense = useMemo(() => {
    let total = 0;
    for (const t of txs) {
      if (t.is_duplicate) continue;
      const m = t.month || t.date?.slice(0, 7);
      if (m !== currentMonth) continue;
      const amt = Number(t.amount || 0);
      if (amt < 0) total += Math.abs(amt);
    }
    return round2(total);
  }, [txs, currentMonth]);

  // Category comparison: current month vs historical average (excluding duplicates)
  const categoryComparisonData = useMemo(() => {
    const months: Record<string, Record<string, number>> = {};
    for (const t of txs) {
      if (t.is_duplicate) continue;
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
    return Array.from(allCats).map((cat) => ({
      category: cat,
      currentMonth: round2(currentData[cat] || 0),
      average: catTotals[cat] ? round2(catTotals[cat].total / catTotals[cat].count) : 0,
      currency: "CNY",
    })).filter((d) => d.currentMonth > 0 || d.average > 0);
  }, [txs, currentMonth]);

  const reportInput = latestRun?.input ?? null;
  const reportText = useMemo(() => {
    if (!reportInput) return null;
    if (typeof reportInput === "string") return reportInput;
    try {
      return JSON.stringify(reportInput, null, 2);
    } catch {
      return String(reportInput);
    }
  }, [reportInput]);

  const primaryCurrency = summaryByCurrency[0]?.currency ?? "CNY";
  const primarySummary = summaryByCurrency[0];
  const primaryExpenseRatio =
    primarySummary && primarySummary.income > 0
      ? primarySummary.expense / primarySummary.income
      : null;
  const budgetStatus =
    primaryExpenseRatio !== null && primaryExpenseRatio > 0.8
      ? "risk"
      : primaryExpenseRatio !== null && primaryExpenseRatio > 0.5
        ? "watch"
        : "good";
  const duplicateCount = txs.filter((t) => t.is_duplicate).length;

  const operatingSummaryItems = [
    {
      label: "Cash flow",
      value: primarySummary ? `${primarySummary.net.toLocaleString()} ${primaryCurrency}` : "—",
      note: "Income minus expenses in loaded data",
      status: primarySummary && primarySummary.net >= 0 ? "good" : "watch",
    },
    {
      label: "Expenses",
      value: primarySummary ? `${primarySummary.expense.toLocaleString()} ${primaryCurrency}` : "—",
      note: "Duplicate transactions excluded",
      status: "neutral",
    },
    {
      label: "Budget risk",
      value: primaryExpenseRatio !== null ? `${Math.round(primaryExpenseRatio * 100)}%` : "—",
      note: "Loaded expenses vs income",
      status: budgetStatus,
    },
    {
      label: "Data quality",
      value: `${duplicateCount}`,
      note: "Potential duplicates flagged",
      status: duplicateCount > 0 ? "watch" : "good",
    },
  ] as const;

  return (
    <div className="flex min-h-screen bg-[#f7f8f8]">
      <div
        className={`flex-1 flex flex-col transition-all duration-300 ${
          isSidebarOpen ? "mr-[420px]" : "mr-0"
        }`}
      >
        <Header
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
          onUploadStatement={handleUploadStatement}
          isUploading={isUploading}
        />

        <main className="flex-1 px-8 py-6">
          <div className="mb-6">
            <h1 className="mb-2">Financial Overview</h1>
            <div className="text-sm text-gray-600">
              {monthlyTrendsData.length > 0
                ? `${monthlyTrendsData[0].month} to ${
                    monthlyTrendsData[monthlyTrendsData.length - 1].month
                  }`
                : "—"}
            </div>
          </div>

          {loading && <div className="text-sm text-gray-500">Loading...</div>}

          {errMsg && (
            <div className="text-sm text-red-600">
              {errMsg}
              <button
                onClick={load}
                className="ml-3 text-xs text-blue-600 underline"
              >
                Retry
              </button>
            </div>
          )}

          {!loading && !errMsg && (
            <>
              <OperatingSummary items={operatingSummaryItems} />
              <MetricsCards items={summaryByCurrency} />
              <IncomeSummary
                monthlyIncome={monthlyIncome}
                currentMonthExpense={currentMonthExpense}
              />
              <SourceBreakdown items={sourceData} />
              <div className="grid grid-cols-2 gap-4 mb-6">
                <MonthlyTrends data={monthlyTrendsData} currency={summaryByCurrency[0]?.currency ?? 'CNY'} />
                <CategoryPieChart data={categoryData} />
              </div>
              <div className="mb-6">
                <CategoryComparison data={categoryComparisonData} />
              </div>
              <TransactionsTable transactions={tableTransactions} />

              <div className="mt-6 bg-white rounded-lg border border-gray-200">
                <div className="px-5 py-4 border-b border-gray-200">
                  <h3 className="text-sm text-gray-900">Latest Report</h3>
                  <div className="text-xs text-gray-500 mt-1">
                    Generated from analysis_runs.input
                  </div>
                </div>
                <div className="px-5 py-4">
                  {reportText ? (
                    <pre className="text-xs text-slate-700 whitespace-pre-wrap break-words">
                      {reportText}
                    </pre>
                  ) : (
                    <div className="text-xs text-gray-500">
                      No report available yet.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      <AgentTeamPanel
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        userId={userId}
      />
    </div>
  );
}
