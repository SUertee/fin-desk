import { useMemo, useState } from "react";
import { Coins, Upload } from "lucide-react";

import { CategoryPieChart } from "../components/CategoryPieChart";
import { MonthlyTrends } from "../components/MonthlyTrends";
import { SpendingCalendar } from "../components/SpendingCalendar";
import { TransactionsTable } from "../components/TransactionsTable";
import { AiCostExplorer } from "../features/cost-explorer/AiCostExplorer";
import { useI18n } from "../i18n";

type MonthlyTrend = { month: string; income: number; expenses: number };
type CategorySpend = { category: string; amount: number; currency: string };
type TableTransaction = {
  id: string | number;
  date: string;
  month: string;
  merchant: string;
  category: string;
  amount: number;
  currency: string;
  source: string;
  payment_method: string;
  is_duplicate: boolean;
};

type Props = {
  userId: string;
  primaryCurrency: string;
  monthlyTrendsData: MonthlyTrend[];
  categoryData: CategorySpend[];
  tableTransactions: TableTransaction[];
  duplicateCount: number;
  latestImportAt: string | null;
  isUploading: boolean;
  onUploadStatement: (file: File) => void;
  onAskCfoAbout: (question: string) => void;
};

type LedgerTab = "calendar" | "transactions" | "categories" | "trends";

export function LedgerPage({
  userId,
  primaryCurrency,
  monthlyTrendsData,
  categoryData,
  tableTransactions,
  duplicateCount,
  latestImportAt,
  isUploading,
  onUploadStatement,
  onAskCfoAbout,
}: Props) {
  const { lang, t } = useI18n();
  const [activeTab, setActiveTab] = useState<LedgerTab>("calendar");
  const [categoryView, setCategoryView] = useState<"spending" | "ai-costs">("spending");
  const latestMonth = monthlyTrendsData.at(-1)?.month;

  const period = useMemo(() => {
    if (!tableTransactions.length) return null;
    const dates = tableTransactions.map((transaction) => transaction.date).sort();
    return { from: dates[0], to: dates.at(-1) as string };
  }, [tableTransactions]);

  const sourceCounts = useMemo(() => {
    const counts = new Map<string, number>();
    tableTransactions.forEach((transaction) => {
      counts.set(transaction.source, (counts.get(transaction.source) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [tableTransactions]);

  const upload = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.xlsx,.pdf";
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (file) onUploadStatement(file);
    };
    input.click();
  };

  const tabs: Array<{ id: LedgerTab; label: string; count?: number }> = [
    { id: "calendar", label: lang === "zh" ? "日历" : "Calendar" },
    { id: "transactions", label: lang === "zh" ? "流水" : "Transactions", count: tableTransactions.length },
    { id: "categories", label: lang === "zh" ? "分类" : "Categories" },
    { id: "trends", label: lang === "zh" ? "趋势" : "Trends" },
  ];

  return (
    <main className="ledger-page">
      <header className="ledger-page-head">
        <div>
          <span>{lang === "zh" ? "真实账本" : "YOUR LEDGER"}</span>
          <h1>{lang === "zh" ? "流水" : "Transactions"}</h1>
          <p>
            {period
              ? (lang === "zh" ? `数据覆盖 ${period.from} 至 ${period.to}` : `Data from ${period.from} to ${period.to}`)
              : (lang === "zh" ? "导入账单后，在这里核对每天的钱去了哪里。" : "Import a statement to review daily spending.")}
          </p>
        </div>
        <button type="button" className="ledger-import-button" onClick={upload} disabled={isUploading}>
          <Upload /> {isUploading ? (lang === "zh" ? "正在导入" : "Importing") : (lang === "zh" ? "导入账单" : "Import statement")}
        </button>
      </header>

      <section className="explore2 ledger-explorer">
        <div className="explore2-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`explore2-tab ${activeTab === tab.id ? "explore2-tab-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
              {tab.count != null && <span className="explore2-count">{tab.count}</span>}
            </button>
          ))}
        </div>
        <div className="explore2-body">
          {activeTab === "calendar" && (
            <SpendingCalendar
              userId={userId}
              currency={primaryCurrency}
              defaultMonth={latestMonth}
              onAskCfo={onAskCfoAbout}
            />
          )}
          {activeTab === "transactions" && <TransactionsTable transactions={tableTransactions} />}
          {activeTab === "trends" && <MonthlyTrends data={monthlyTrendsData} currency={primaryCurrency} />}
          {activeTab === "categories" && categoryView === "spending" && (
            <div className="category-explorer">
              <div className="category-explorer-intro">
                <div>
                  <span>{lang === "zh" ? "支出分类" : "SPENDING CATEGORIES"}</span>
                  <h3>{lang === "zh" ? "钱花在了哪里" : "Where your money goes"}</h3>
                  <p>{lang === "zh" ? "点击分类查看支出结构；后续会继续下钻到具体交易。" : "Review spending structure by category."}</p>
                </div>
                <button type="button" className="ai-cost-category-card" onClick={() => setCategoryView("ai-costs")}>
                  <span className="ai-cost-category-icon"><Coins /></span>
                  <span><small>{lang === "zh" ? "数字服务" : "DIGITAL SERVICES"}</small><strong>{lang === "zh" ? "AI 成本" : "AI Costs"}</strong><em>{lang === "zh" ? "API 使用、订阅与预算" : "API usage and subscriptions"}</em></span>
                  <span className="ai-cost-category-arrow">→</span>
                </button>
              </div>
              <CategoryPieChart data={categoryData} />
            </div>
          )}
          {activeTab === "categories" && categoryView === "ai-costs" && (
            <AiCostExplorer userId={userId} onBack={() => setCategoryView("spending")} />
          )}
        </div>
      </section>

      <footer className="coverage-line ledger-coverage">
        {period && <span>{t("coverage.range")} {period.from} ~ {period.to}</span>}
        {sourceCounts.length > 0 && <span>{sourceCounts.map(([source, count]) => `${t(`source.${source}`)} ${count} ${t("coverage.rows")}`).join(" / ")}</span>}
        {duplicateCount > 0 && <span>{duplicateCount} {t("coverage.duplicates")}</span>}
        <span>{t("coverage.latestImport")}: {latestImportAt ? latestImportAt.slice(0, 10) : t("coverage.none")}</span>
      </footer>
    </main>
  );
}
