/**
 * Loads a user's finance workspace data (transactions, latest analysis run,
 * profile, data-source status, CFO brief) and exposes the derived view models
 * the workspace pages render. All fetching goes through services/financeApi.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDataSourceStatus,
  fetchLatestAnalysisRun,
  fetchProfile,
  fetchTransactions,
  fetchWorkspaceBrief,
  importStatement,
} from "../services/financeApi";
import type { DataSourceStatus } from "../services/financeApi";
import type { WorkspaceBrief } from "../types/financeAgent";
import type { AnalysisRunRow, TransactionRow } from "../types/db";
import {
  buildReportText,
  computeCategoryComparison,
  computeCategoryData,
  computeCurrentMonthExpense,
  computeMonthlyTotalsFromTxs,
  computeSourceBreakdown,
  summarizeByCurrency,
  toMonthlyTrendsData,
  toTableTransactions,
} from "../utils/financeTransforms";
import type { MonthlyTotal } from "../utils/financeTransforms";

export function useFinanceWorkspaceData(userId: string) {
  const [profileName, setProfileName] = useState("User");
  const [profile, setProfile] = useState<Record<string, any> | null>(null);
  const [monthlyIncome, setMonthlyIncome] = useState(0);
  const [txs, setTxs] = useState<TransactionRow[]>([]);
  const [monthlyTotalsFromRun, setMonthlyTotalsFromRun] = useState<
    MonthlyTotal[] | null
  >(null);
  const [latestRun, setLatestRun] = useState<AnalysisRunRow | null>(null);
  const [brief, setBrief] = useState<WorkspaceBrief | null>(null);
  const [dataSourceStatus, setDataSourceStatus] = useState<DataSourceStatus | null>(null);

  const [loading, setLoading] = useState(true);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErrMsg(null);

    try {
      const [transactions, latestRunResponse, profile, dataStatus] = await Promise.all([
        fetchTransactions(userId, 2000),
        fetchLatestAnalysisRun(userId),
        fetchProfile(userId),
        fetchDataSourceStatus(userId).catch(() => null),
      ]);
      // The brief may run an LLM composition — hydrate it after first paint
      // instead of blocking the whole page on it.
      fetchWorkspaceBrief(userId)
        .then((briefResponse) => setBrief(briefResponse))
        .catch(() => setBrief(null));

      setProfileName(profile.name || "User");
      setMonthlyIncome(profile.monthly_income || 0);
      setProfile(profile);

      console.log("[api] transactions:", transactions);
      console.log("[api] latestRun:", latestRunResponse);

      setTxs(transactions);
      setLatestRun(latestRunResponse ?? null);
      setDataSourceStatus(dataStatus);

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
      setIsUploading(true);
      setErrMsg(null);

      try {
        await importStatement(userId, file);
        await load();
      } catch (e: any) {
        setErrMsg(e?.message ?? "Statement import failed");
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

  // monthlyTotals：优先用后端分析结果；没有就从 txs 计算
  const monthlyTotals: MonthlyTotal[] = useMemo(() => {
    if (monthlyTotalsFromRun && monthlyTotalsFromRun.length > 0) {
      return monthlyTotalsFromRun;
    }
    return computeMonthlyTotalsFromTxs(txs);
  }, [monthlyTotalsFromRun, txs]);

  const summaryByCurrency = useMemo(() => summarizeByCurrency(txs), [txs]);

  const monthlyTrendsData = useMemo(
    () => toMonthlyTrendsData(monthlyTotals),
    [monthlyTotals]
  );

  const tableTransactions = useMemo(() => toTableTransactions(txs), [txs]);

  const sourceData = useMemo(() => computeSourceBreakdown(txs), [txs]);

  const categoryData = useMemo(() => computeCategoryData(txs), [txs]);

  // Current month for income summary
  const currentMonth = new Date().toISOString().slice(0, 7);
  const currentMonthExpense = useMemo(
    () => computeCurrentMonthExpense(txs, currentMonth),
    [txs, currentMonth]
  );

  const categoryComparisonData = useMemo(
    () => computeCategoryComparison(txs, currentMonth),
    [txs, currentMonth]
  );

  const reportOutput = (latestRun?.output ?? null) as Record<string, any> | null;
  const reportText = useMemo(() => buildReportText(reportOutput), [reportOutput]);

  const primaryCurrency = summaryByCurrency[0]?.currency ?? "CNY";
  const primarySummary = summaryByCurrency[0];
  const primaryExpenseRatio =
    primarySummary && primarySummary.income > 0
      ? primarySummary.expense / primarySummary.income
      : null;
  const budgetStatus: "good" | "watch" | "risk" =
    primaryExpenseRatio !== null && primaryExpenseRatio > 0.8
      ? "risk"
      : primaryExpenseRatio !== null && primaryExpenseRatio > 0.5
        ? "watch"
        : "good";
  const duplicateCount = txs.filter((t) => t.is_duplicate).length;
  const topCategory = useMemo(
    () => [...categoryData].sort((a, b) => b.amount - a.amount)[0],
    [categoryData]
  );

  return {
    // loaded data
    profileName,
    profile,
    monthlyIncome,
    txs,
    latestRun,
    brief,
    dataSourceStatus,
    // request state
    loading,
    errMsg,
    isUploading,
    // actions
    load,
    handleUploadStatement,
    // derived view models
    monthlyTotals,
    summaryByCurrency,
    monthlyTrendsData,
    tableTransactions,
    sourceData,
    categoryData,
    currentMonthExpense,
    categoryComparisonData,
    reportText,
    primaryCurrency,
    budgetStatus,
    duplicateCount,
    topCategory,
  };
}
