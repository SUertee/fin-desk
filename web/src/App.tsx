import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, LayoutDashboard, MessagesSquare, Settings as SettingsIcon } from "lucide-react";
import {
  fetchTransactions,
  fetchDataSourceStatus,
  fetchLatestAnalysisRun,
  fetchProfile,
  getApiBaseUrl,
  importStatement,
} from "./services/supabaseApi";
import { fetchWorkspaceBrief } from "./services/supabaseApi";
import type { WorkspaceBrief } from "./types/financeAgent";
import type { DataSourceStatus } from "./services/supabaseApi";
import type { AnalysisRunRow, TransactionRow } from "./types/db";

import { AgentTeamPanel } from "./components/AgentTeamPanel";
import { FinanceWorkspacePage } from "./pages/FinanceWorkspacePage";
import { MyOfficePage } from "./pages/MyOfficePage";
import { SettingsPage } from "./pages/SettingsPage";
import type { PageId } from "./pages/pageTypes";
import { useI18n } from "./i18n";

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
  const { t } = useI18n();

  const [activePage, setActivePage] = useState<PageId>("workspace");
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

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [cfoPrefill, setCfoPrefill] = useState<string | null>(null);
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

  const reportOutput = (latestRun?.output ?? null) as Record<string, any> | null;
  const reportText = useMemo(() => {
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
  }, [reportOutput]);

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
  const topCategory = useMemo(
    () => [...categoryData].sort((a, b) => b.amount - a.amount)[0],
    [categoryData]
  );

  const navItems = [
    { id: "workspace" as const, label: t("nav.workspace"), icon: LayoutDashboard },
    { id: "office" as const, label: t("nav.office"), icon: MessagesSquare },
    { id: "settings" as const, label: t("nav.settings"), icon: SettingsIcon },
  ];

  const onboardingItems = [
    budgetStatus === "risk"
      ? {
          title: "Reduce discretionary spend this week",
          body: "Your expense ratio is above the risk threshold. Start with the largest flexible category.",
          status: "High priority",
        }
      : budgetStatus === "watch"
        ? {
            title: "Set one weekly spending guardrail",
            body: "Spending is elevated but controllable. Use a weekly cap before changing the full budget.",
            status: "Recommended",
          }
        : {
            title: "Keep the current cash-flow rhythm",
            body: "Loaded income and expenses look stable. Automate savings before adding discretionary spend.",
            status: "Healthy",
          },
    topCategory
      ? {
          title: `Review ${topCategory.category}`,
          body: `${topCategory.category} is currently the largest expense category at ${topCategory.amount.toLocaleString()} ${topCategory.currency}.`,
          status: "Spending review",
        }
      : {
          title: "Import recent transactions",
          body: "Add a statement to unlock category review, anomaly checks, and budget recommendations.",
          status: "Data needed",
        },
    duplicateCount > 0
      ? {
          title: "Check duplicate transactions",
          body: `${duplicateCount} potential duplicates are flagged and should be reviewed before relying on reports.`,
          status: "Data quality",
        }
      : {
          title: "Data quality looks clean",
          body: "No duplicate transactions are currently flagged in the loaded dataset.",
          status: "Verified",
        },
  ];

  const actionItems =
    brief?.has_data && brief.actions.length > 0
      ? brief.actions.map((action) => ({
          title: action.title,
          body: action.rationale,
          status: `Impact ${action.impact} · Effort ${action.effort}`,
        }))
      : onboardingItems;
  const actionSource: "agent" | "onboarding" =
    brief?.has_data && brief.actions.length > 0 ? "agent" : "onboarding";


  return (
    <div className="product-shell">
      <header className="product-topbar">
        <div className="product-topbar-inner">
          <div className="product-brand-mark">
            <div className="product-logo">F</div>
            <div>
              <div className="product-brand-title">FinDesk</div>
            </div>
          </div>
          <nav className="product-tabs">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
                className={`product-tab ${active ? "product-tab-active" : ""}`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
          <div className="product-topbar-actions">
            <Bell className="product-bell" />
            <div className="product-avatar">RM</div>
          </div>
        </div>
      </header>

      <div
        className={`product-content${
          isSidebarOpen && activePage === "workspace" ? " product-content-with-chat" : ""
        }`}
      >
        {activePage === "workspace" ? (
          <FinanceWorkspacePage
            userId={userId}
            actionSource={actionSource}
            brief={brief}
            dataSourceStatus={dataSourceStatus}
            latestImportAt={dataSourceStatus?.latest_import?.created_at ?? null}
            loading={loading}
            errMsg={errMsg}
            isUploading={isUploading}
            primaryCurrency={primaryCurrency}
            budgetStatus={budgetStatus}
            duplicateCount={duplicateCount}
            monthlyTrendsData={monthlyTrendsData}
            actionItems={actionItems}
            categoryData={categoryData}
            tableTransactions={tableTransactions}
            onReload={load}
            onOpenCfo={() => setIsSidebarOpen(true)}
            onAskCfoAbout={(question) => {
              setCfoPrefill(question);
              setIsSidebarOpen(true);
            }}
            onUploadStatement={handleUploadStatement}
          />
        ) : activePage === "office" ? (
          <MyOfficePage userId={userId} userName={profileName} />
        ) : (
          <main className="settings-shell">
              {activePage === "settings" && (
              <SettingsPage
                userId={userId}
                profileName={profileName}
                profile={profile}
                apiBaseUrl={getApiBaseUrl()}
                transactionCount={txs.length}
                dataSourceStatus={dataSourceStatus}
                monthlyIncome={monthlyIncome}
                onProfileSaved={load}
                showDeveloperTools={false}
              />
              )}
            </main>
        )}
      </div>

      {activePage === "workspace" && (
        <AgentTeamPanel
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          userId={userId}
          hasFinanceData={txs.length > 0}
          topCategory={topCategory?.category}
          brief={brief}
          userName={profileName}
          prefill={cfoPrefill}
          onPrefillConsumed={() => setCfoPrefill(null)}
        />
      )}
    </div>
  );
}
