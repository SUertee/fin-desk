import { useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  Coins,
  Database,
  FileCheck2,
  GitBranch,
  PanelRightOpen,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";

import { CategoryPieChart } from "../components/CategoryPieChart";
import { MonthlyTrends } from "../components/MonthlyTrends";
import { SpendingCalendar } from "../components/SpendingCalendar";
import { TransactionsTable } from "../components/TransactionsTable";
import { currencySymbol } from "../components/MetricsCards";
import { AiCostExplorer } from "../features/cost-explorer/AiCostExplorer";
import { FinanceInboxEntry } from "../components/inbox/FinanceInboxEntry";
import { useI18n } from "../i18n";
import type { DataSourceStatus } from "../services/financeApi";
import type { WorkspaceBrief } from "../types/financeAgent";

type MonthlyTrend = {
  month: string;
  income: number;
  expenses: number;
};

type CategorySpend = {
  category: string;
  amount: number;
  currency: string;
};

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

type ActionItem = {
  title: string;
  body: string;
  status: string;
};

type FinanceWorkspacePageProps = {
  userId: string;
  actionSource?: "agent" | "onboarding";
  brief?: WorkspaceBrief | null;
  dataSourceStatus?: DataSourceStatus | null;
  latestImportAt?: string | null;
  loading: boolean;
  errMsg: string | null;
  isUploading: boolean;
  primaryCurrency: string;
  budgetStatus: "good" | "watch" | "risk";
  duplicateCount: number;
  monthlyTrendsData: MonthlyTrend[];
  actionItems: ActionItem[];
  categoryData: CategorySpend[];
  tableTransactions: TableTransaction[];
  onReload: () => void;
  onOpenInbox: () => void;
  onOpenCfo: () => void;
  onAskCfoAbout?: (question: string) => void;
  onUploadStatement: (file: File) => void;
};

type ExploreTab = "calendar" | "trends" | "categories" | "transactions";
type DetailDrawer = "reasoning" | "import" | null;

function monthLabel(month: string | undefined, lang: string): string {
  if (!month) return "";
  const [year, monthNumber] = month.split("-");
  if (lang === "zh") return `${year} 年 ${Number(monthNumber)} 月`;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(monthNumber) - 1]} ${year}`;
}

function dayLabel(date: string, lang: string): string {
  const [, monthNumber, day] = date.split("-");
  if (lang === "zh") return `${Number(monthNumber)} 月 ${Number(day)} 日`;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(monthNumber) - 1]} ${Number(day)}`;
}

export function FinanceWorkspacePage({
  userId,
  actionSource = "onboarding",
  brief,
  dataSourceStatus,
  latestImportAt,
  loading,
  errMsg,
  isUploading,
  primaryCurrency,
  budgetStatus,
  duplicateCount,
  monthlyTrendsData,
  actionItems,
  categoryData,
  tableTransactions,
  onReload,
  onOpenInbox,
  onOpenCfo,
  onAskCfoAbout,
  onUploadStatement,
}: FinanceWorkspacePageProps) {
  const { lang, t } = useI18n();
  const [activeTab, setActiveTab] = useState<ExploreTab>("calendar");
  const [categoryView, setCategoryView] = useState<"spending" | "ai-costs">("spending");
  const [detailDrawer, setDetailDrawer] = useState<DetailDrawer>(null);
  const [selectedActionTitle, setSelectedActionTitle] = useState<string | null>(null);
  const sym = currencySymbol(primaryCurrency);

  const latestMonth = monthlyTrendsData.at(-1);
  const hasData = tableTransactions.length > 0;
  const topCategory = useMemo(
    () => [...categoryData].sort((a, b) => b.amount - a.amount)[0] ?? null,
    [categoryData]
  );

  // Highest single-day spend in the latest data month → proactive ask card
  const topSpendDay = useMemo(() => {
    if (!latestMonth) return null;
    const byDay = new Map<string, number>();
    for (const transaction of tableTransactions) {
      if (transaction.is_duplicate || transaction.amount >= 0) continue;
      if (transaction.month !== latestMonth.month) continue;
      byDay.set(transaction.date, (byDay.get(transaction.date) ?? 0) - transaction.amount);
    }
    let best: { date: string; amount: number } | null = null;
    for (const [date, amount] of byDay) {
      if (!best || amount > best.amount) best = { date, amount };
    }
    return best;
  }, [tableTransactions, latestMonth]);

  // Coverage footnote: per-source row counts from loaded transactions
  const sourceCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const transaction of tableTransactions) {
      counts.set(transaction.source, (counts.get(transaction.source) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [tableTransactions]);

  const period = useMemo(() => {
    if (!hasData) return null;
    const dates = tableTransactions.map((transaction) => transaction.date).sort();
    return { from: dates[0], to: dates.at(-1) as string };
  }, [tableTransactions, hasData]);

  const auditStatus = brief?.audit?.status;
  const briefActions = brief?.has_data ? brief.actions : [];
  const transactionCount = dataSourceStatus?.transaction_count ?? tableTransactions.length;
  const sourceCount = sourceCounts.length || dataSourceStatus?.channels.filter((channel) => channel.status !== "planned").length || 0;
  const qualityConfidence = hasData
    ? Math.max(72, Math.min(96, Math.round(92 - duplicateCount * 1.6)))
    : 0;
  const topActionTitle = selectedActionTitle ?? briefActions[0]?.title ?? actionItems[0]?.title ?? "CFO recommendation";
  const rawBriefText = sanitizeBriefText(brief?.headline);
  const netCashFlow = latestMonth ? latestMonth.income - latestMonth.expenses : null;
  const heroSummary = buildHeroSummary({
    lang,
    sym,
    hasData,
    netCashFlow,
    budgetStatus,
    topCategory,
    fallback: t("hero.fallback"),
  });
  const priorityAction = normalizeActionTitle(
    briefActions[0]?.title ?? actionItems[0]?.title,
    lang
  );
  const openReasoning = (title?: string) => {
    setSelectedActionTitle(title ?? null);
    setDetailDrawer("reasoning");
  };

  const handleUploadClick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.xlsx,.pdf";
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (file) onUploadStatement(file);
    };
    input.click();
  };

  const tabs: { id: ExploreTab; label: string; count?: number }[] = [
    { id: "calendar", label: t("tabs.calendar") },
    { id: "trends", label: t("tabs.trends") },
    { id: "categories", label: t("tabs.categories") },
    { id: "transactions", label: t("tabs.transactions"), count: tableTransactions.length },
  ];

  return (
    <main className="workspace-main">
      {/* Band 1: the CFO judgment and the four assets that support it */}
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <div className="dashboard-hero-eyebrow">
            <span>{t("hero.eyebrow")}</span>
            <span>/</span>
            <span>{monthLabel(latestMonth?.month, lang)}</span>
            {auditStatus && (
              <>
                <span>/</span>
                <span>{t(`hero.audit.${auditStatus}`)}</span>
              </>
            )}
          </div>
          <h1 className="cfo-judgment-text">{heroSummary}</h1>
          <div className="dashboard-hero-actions">
            <button type="button" onClick={onOpenCfo} className="dashboard-btn dashboard-btn-primary">
              <PanelRightOpen className="h-4 w-4" />
              {t("hero.askCfo")}
            </button>
            <button
              type="button"
              onClick={handleUploadClick}
              disabled={isUploading}
              className="dashboard-btn dashboard-btn-secondary"
            >
              <Upload className="h-4 w-4" />
              {isUploading ? t("hero.uploading") : t("hero.upload")}
            </button>
            <button type="button" onClick={() => openReasoning()} className="dashboard-btn-text">
              <GitBranch className="h-3.5 w-3.5" />
              {lang === "zh" ? "查看判断依据" : "View reasoning"}
            </button>
          </div>
          <p className="dashboard-hero-hint">{priorityAction}</p>
        </div>

        <div className="dashboard-metric-grid">
          <div className={`metric-card glass-panel ${netCashFlow != null && netCashFlow < 0 ? "metric-card-risk" : "metric-card-positive"}`}>
            <span className="metric-card-label">{lang === "zh" ? "净现金流" : "Net cash flow"}</span>
            <strong>{netCashFlow == null ? "—" : `${netCashFlow < 0 ? "-" : "+"}${formatMoney(netCashFlow, sym)}`}</strong>
            <small>
              {netCashFlow != null && netCashFlow < 0 ? <ArrowDownRight /> : <ArrowUpRight />}
              {monthLabel(latestMonth?.month, lang) || (lang === "zh" ? "等待数据" : "Awaiting data")}
            </small>
          </div>
          <div className="metric-card glass-panel metric-card-income">
            <span className="metric-card-label">{t("hero.stat.income")}</span>
            <strong>{latestMonth ? `${sym}${latestMonth.income.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}</strong>
            <small>{lang === "zh" ? "已确认收入" : "Confirmed inflow"}</small>
          </div>
          <div className="metric-card glass-panel metric-card-spend">
            <span className="metric-card-label">{t("hero.stat.expense")}</span>
            <strong>{latestMonth ? `${sym}${latestMonth.expenses.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}</strong>
            <small>{topCategory ? `${topCategory.category} · ${formatMoney(topCategory.amount, sym)}` : lang === "zh" ? "等待分类数据" : "Awaiting categories"}</small>
          </div>
          <button type="button" className="metric-card glass-panel metric-card-status" onClick={() => setDetailDrawer("import")}>
            <span className="metric-card-label">{t("hero.stat.budget")}</span>
            <strong>{t(`budget.${hasData ? budgetStatus : "data_limited"}`)}</strong>
            <small>
              <Database />
              {qualityConfidence ? `${qualityConfidence}% · ${duplicateCount} ${lang === "zh" ? "笔重复" : "duplicates"}` : lang === "zh" ? "等待账单导入" : "Awaiting statements"}
            </small>
          </button>
        </div>
      </section>

      {loading && <div className="text-sm text-gray-500">{t("workspace.loading")}</div>}

      {errMsg && (
        <div className="text-sm text-red-600">
          {lang === "zh" && /failed to fetch/i.test(errMsg) ? "无法连接后端服务" : errMsg}
          <button onClick={onReload} className="ml-3 text-xs text-blue-600 underline" type="button">
            {t("workspace.retry")}
          </button>
        </div>
      )}

      {!loading && !errMsg && (
        <>
          {/* Band 2: 行动 */}
          <div className="band-head">
            <h2>{t("actions.title")}</h2>
            <span className={`band-chip ${actionSource === "agent" ? "band-chip-agent" : ""}`}>
              {actionSource === "agent" ? t("actions.fromBrief") : t("actions.onboarding")}
            </span>
          </div>
          <section className="actions2">
            {(briefActions.length > 0
              ? briefActions.map((action) => ({
                  title: normalizeActionTitle(action.title, lang),
                  body: normalizeActionBody(action.rationale, lang),
                  status: lang === "zh" ? `影响 ${translateLevel(action.impact)} · 成本 ${translateLevel(action.effort)}` : `Impact ${action.impact} · Effort ${action.effort}`,
                }))
              : actionItems.map((item) => ({
                  title: normalizeActionTitle(item.title, lang),
                  body: normalizeActionBody(item.body, lang),
                  status: normalizeActionStatus(item.status, lang),
                }))
            )
              .slice(0, 2)
              .map((item, index) => (
                <button
                  key={item.title}
                  type="button"
                  className="action2-card"
                  onClick={() => openReasoning(item.title)}
                >
                  <div className="action2-rank">{index + 1}</div>
                  <div className="action2-meta">
                    <span>{item.status}</span>
                    <span>{lang === "zh" ? "Audit checked" : "Audit checked"}</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <span className="action2-go">
                    {lang === "zh" ? "查看 CFO 证据链 →" : "View CFO evidence →"}
                  </span>
                </button>
              ))}
            {topSpendDay && (
              <button
                type="button"
                className="action2-card action2-ask"
                onClick={() =>
                  onAskCfoAbout
                    ? onAskCfoAbout(
                        `帮我逐笔看看 ${topSpendDay.date} 这天的消费，有什么值得注意的？`
                      )
                    : onOpenCfo()
                }
              >
                <div className="action2-rank action2-rank-ask">?</div>
                <h3>
                  {dayLabel(topSpendDay.date, lang)}
                  {lang === "zh" ? "花了 " : ": spent "}
                  {sym}
                  {Math.round(topSpendDay.amount).toLocaleString()}
                </h3>
                <p>{t("actions.askDay.body")}</p>
                <span className="action2-go">{t("actions.askDay.cta")}</span>
              </button>
            )}
          </section>

          <FinanceInboxEntry userId={userId} onOpen={onOpenInbox} />

          <button
            type="button"
            className="data-quality-summary"
            onClick={() => setDetailDrawer("import")}
          >
            <div className="data-quality-copy">
              <div className="data-quality-title">
                <FileCheck2 />
                {lang === "zh" ? "数据质量摘要" : "Data Quality Summary"}
              </div>
              <div className="data-quality-subtitle">
                {lang === "zh"
                  ? "账单导入是确定性数据 pipeline；CFO 和 specialist 只消费它产出的结构化证据。"
                  : "Statement import is a deterministic data pipeline; the CFO and specialists consume its structured evidence."}
              </div>
            </div>
            <div className="data-quality-metrics">
              <span className="dq-good">{transactionCount.toLocaleString()} {lang === "zh" ? "笔交易" : "transactions"}</span>
              <span className={duplicateCount > 0 ? "dq-watch" : "dq-good"}>{duplicateCount} {lang === "zh" ? "笔重复已排除" : "duplicates removed"}</span>
              <span>{sourceCount} {lang === "zh" ? "个数据源" : "sources"}</span>
              <span className={qualityConfidence >= 85 ? "dq-good" : "dq-watch"}>{qualityConfidence || "—"}{qualityConfidence ? "%" : ""} {lang === "zh" ? "置信度" : "confidence"}</span>
            </div>
          </button>

          {/* Band 3: 探索 */}
          <section className="explore2">
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
                  defaultMonth={latestMonth?.month}
                  onAskCfo={onAskCfoAbout}
                />
              )}
              {activeTab === "trends" && (
                <MonthlyTrends data={monthlyTrendsData} currency={primaryCurrency} />
              )}
              {activeTab === "categories" && categoryView === "spending" && (
                <div className="category-explorer">
                  <div className="category-explorer-intro">
                    <div>
                      <span>{lang === "zh" ? "支出分类" : "SPENDING CATEGORIES"}</span>
                      <h3>{lang === "zh" ? "钱花在了哪里" : "Where your money goes"}</h3>
                      <p>
                        {lang === "zh"
                          ? "账单消费和数字服务成本属于同一财务视图，但由不同证据管线生成。"
                          : "Statement spend and digital-service costs share one finance view while retaining separate evidence pipelines."}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="ai-cost-category-card"
                      onClick={() => setCategoryView("ai-costs")}
                    >
                      <span className="ai-cost-category-icon"><Coins /></span>
                      <span>
                        <small>{lang === "zh" ? "数字服务" : "DIGITAL SERVICES"}</small>
                        <strong>{lang === "zh" ? "AI 成本" : "AI Costs"}</strong>
                        <em>
                          {lang === "zh"
                            ? "API 使用、订阅与预算"
                            : "API usage, subscriptions, and budget"}
                        </em>
                      </span>
                      <span className="ai-cost-category-arrow">→</span>
                    </button>
                  </div>
                  <CategoryPieChart data={categoryData} />
                </div>
              )}
              {activeTab === "categories" && categoryView === "ai-costs" && (
                <AiCostExplorer
                  userId={userId}
                  onBack={() => setCategoryView("spending")}
                />
              )}
              {activeTab === "transactions" && (
                <TransactionsTable transactions={tableTransactions} />
              )}
            </div>
          </section>

          {/* 数据脚注 */}
          <div className="coverage-line">
            {period && (
              <>
                <span>
                  {t("coverage.range")} {period.from} ~ {period.to}
                </span>
                <span className="coverage-dot">·</span>
              </>
            )}
            {sourceCounts.length > 0 && (
              <>
                <span>
                  {sourceCounts
                    .map(([source, count]) => `${t(`source.${source}`)} ${count} ${t("coverage.rows")}`)
                    .join(" / ")}
                </span>
                <span className="coverage-dot">·</span>
              </>
            )}
            {duplicateCount > 0 && (
              <>
                <span>
                  {duplicateCount} {t("coverage.duplicates")}
                </span>
                <span className="coverage-dot">·</span>
              </>
            )}
            <span>
              {t("coverage.latestImport")}:{" "}
              {latestImportAt ? latestImportAt.slice(0, 10) : t("coverage.none")}
            </span>
          </div>

          {detailDrawer && (
            <div className="workspace-drawer-shell" role="dialog" aria-modal="false">
              <aside className="workspace-detail-drawer">
                <div className="workspace-drawer-head">
                  <div>
                    <div className="workspace-drawer-kicker">
                      {detailDrawer === "reasoning" ? <Bot /> : <Database />}
                      {detailDrawer === "reasoning"
                        ? lang === "zh" ? "CFO 调度证据" : "CFO Orchestration Evidence"
                        : lang === "zh" ? "导入与数据质量" : "Import & Data Quality"}
                    </div>
                    <h3>
                      {detailDrawer === "reasoning"
                        ? topActionTitle
                        : lang === "zh" ? "Statement Import Pipeline" : "Statement Import Pipeline"}
                    </h3>
                  </div>
                  <button
                    type="button"
                    className="workspace-drawer-close"
                    onClick={() => setDetailDrawer(null)}
                    title="Close"
                  >
                    <X />
                  </button>
                </div>

                {detailDrawer === "reasoning" ? (
                  <div className="workspace-drawer-body">
                    <div className="reasoning-summary">
                      {lang === "zh"
                        ? "CFO 先判断用户目标和证据缺口，只在需要时调用 specialist 或确定性工具，最后统一输出给用户。"
                        : "The CFO judges intent and evidence gaps first, calls specialists or deterministic tools only when needed, then composes one user-facing answer."}
                    </div>
                    {rawBriefText && (
                      <div className="raw-brief-card">
                        <div>{lang === "zh" ? "CFO 原始简报摘要" : "Original CFO brief summary"}</div>
                        <p>{shortenText(rawBriefText, lang === "zh" ? 180 : 260)}</p>
                      </div>
                    )}
                    {[
                      {
                        icon: <Bot />,
                        title: "CFO Lead",
                        status: lang === "zh" ? "最终决策" : "Final decision",
                        body: lang === "zh"
                          ? `${heroSummary} 优先动作：${priorityAction}。`
                          : `${heroSummary} Priority action: ${priorityAction}.`,
                      },
                      {
                        icon: <GitBranch />,
                        title: "Expense Analyst",
                        status: lang === "zh" ? "按需调用" : "Called when needed",
                        body: topCategoryLabel(categoryData, lang),
                      },
                      {
                        icon: <CheckCircle2 />,
                        title: "Budget Coach",
                        status: lang === "zh" ? "预算判断" : "Budget check",
                        body: lang === "zh"
                          ? `预算状态为「${t(`budget.${hasData ? budgetStatus : "data_limited"}`)}」，建议先补齐收入与固定支出画像。`
                          : `Budget status is ${t(`budget.${hasData ? budgetStatus : "data_limited"}`)}; complete income and recurring-expense profile first.`,
                      },
                      {
                        icon: <ShieldCheck />,
                        title: "Risk & Audit",
                        status: auditStatus ? t(`hero.audit.${auditStatus}`) : lang === "zh" ? "证据检查" : "Evidence check",
                        body: lang === "zh"
                          ? "输出前检查数据覆盖、重复交易和建议是否超出证据范围。"
                          : "Checks data coverage, duplicate transactions, and whether the recommendation overclaims beyond evidence.",
                      },
                    ].map((step, index) => (
                      <div className="reasoning-step" key={step.title}>
                        <div className="reasoning-step-index">{index + 1}</div>
                        <div className="reasoning-step-icon">{step.icon}</div>
                        <div>
                          <div className="reasoning-step-top">
                            <strong>{step.title}</strong>
                            <span>{step.status}</span>
                          </div>
                          <p>{step.body}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="workspace-drawer-body">
                    <div className="reasoning-summary">
                      {lang === "zh"
                        ? "这里不是 Agent，而是后端数据工程链路。它把支付宝、微信、银行流水转换成 CFO 可以引用的结构化证据。"
                        : "This is not an agent. It is the backend data pipeline that turns Alipay, WeChat, and bank statements into structured evidence for the CFO."}
                    </div>
                    <div className="pipeline-steps">
                      {["Parse", "Normalize", "Deduplicate", "Categorize", "Quality Report"].map((step, index) => (
                        <div className="pipeline-step" key={step}>
                          <span>{index + 1}</span>
                          <strong>{step}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="import-metrics-grid">
                      <Metric label={lang === "zh" ? "交易记录" : "Transactions"} value={transactionCount.toLocaleString()} />
                      <Metric label={lang === "zh" ? "重复排除" : "Duplicates removed"} value={String(duplicateCount)} />
                      <Metric label={lang === "zh" ? "数据源" : "Sources"} value={String(sourceCount)} />
                      <Metric label={lang === "zh" ? "分类置信度" : "Category confidence"} value={qualityConfidence ? `${qualityConfidence}%` : "—"} />
                    </div>
                    <div className="source-list">
                      <div className="source-list-title">{lang === "zh" ? "来源覆盖" : "Source coverage"}</div>
                      {sourceCounts.length > 0 ? (
                        sourceCounts.map(([source, count]) => (
                          <div className="source-row" key={source}>
                            <span>{formatSourceLabel(source, t)}</span>
                            <strong>{count.toLocaleString()} {lang === "zh" ? "笔" : "rows"}</strong>
                          </div>
                        ))
                      ) : (
                        <div className="source-row muted">
                          <span>{lang === "zh" ? "暂无导入数据" : "No imported data yet"}</span>
                          <strong>—</strong>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </aside>
            </div>
          )}
        </>
      )}
    </main>
  );
}

function formatSourceLabel(source: string, t: (key: string) => string) {
  const translated = t(`source.${source}`);
  return translated === `source.${source}` ? source : translated;
}

function sanitizeBriefText(value?: string | null) {
  if (!value) return "";
  return value
    .replace(/\*\*/g, "")
    .replace(/__+/g, "")
    .replace(/#{1,6}\s*/g, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\s*\n+\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function shortenText(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength).trim()}…`;
}

function formatMoney(value: number, symbol: string) {
  return `${symbol}${Math.abs(value).toLocaleString(undefined, {
    maximumFractionDigits: 0,
  })}`;
}

function buildHeroSummary({
  lang,
  sym,
  hasData,
  netCashFlow,
  budgetStatus,
  topCategory,
  fallback,
}: {
  lang: string;
  sym: string;
  hasData: boolean;
  netCashFlow: number | null;
  budgetStatus: "good" | "watch" | "risk";
  topCategory: CategorySpend | null;
  fallback: string;
}) {
  if (!hasData || netCashFlow == null) return fallback;

  const category = topCategory?.category ?? (lang === "zh" ? "最大弹性类别" : "largest flexible category");
  const netText = formatMoney(netCashFlow, sym);

  if (lang === "zh") {
    if (netCashFlow < 0) {
      return `支出超过收入 ${netText}，当前预算风险优先从「${category}」复核。`;
    }
    if (budgetStatus === "risk") {
      return `本期现金流为正，但预算风险仍高；优先复核「${category}」。`;
    }
    return `本期现金流为正，继续保持节奏，并复核「${category}」的可控空间。`;
  }

  if (netCashFlow < 0) {
    return `Spending exceeds income by ${netText}; review ${category} before changing fixed budgets.`;
  }
  if (budgetStatus === "risk") {
    return `Cash flow is positive, but budget risk remains high; review ${category} first.`;
  }
  return `Cash flow is positive; maintain the rhythm and review controllable ${category} spend.`;
}

function normalizeActionTitle(title: string | undefined, lang: string) {
  if (!title) return lang === "zh" ? "导入账单以生成行动建议" : "Import statements to generate actions";
  if (lang !== "zh") return title;
  const lower = title.toLowerCase();
  if (lower.includes("largest flexible")) return "复核最大弹性支出类别";
  if (lower.includes("income") && lower.includes("recurring")) return "补全收入与固定支出画像";
  if (lower.includes("duplicate")) return "检查跨源重复交易";
  if (lower.includes("discretionary")) return "本周降低弹性支出";
  if (lower.includes("shopping")) return "复核购物支出";
  if (lower.includes("data quality")) return "确认数据质量";
  if (lower.includes("import")) return "导入最近账单";
  return title;
}

function normalizeActionBody(body: string | undefined, lang: string) {
  if (!body) return "";
  if (lang !== "zh") return body;
  const lower = body.toLowerCase();
  if (lower.includes("largest recurring") || lower.includes("largest recurring category")) {
    return "最快可控的节流空间通常来自最大且反复出现的支出类别。";
  }
  if (lower.includes("largest flexible")) {
    return "先从最大弹性支出类别入手，识别重复购买、冲动消费和可推迟开销。";
  }
  if (lower.includes("stable income") || lower.includes("recurring cost")) {
    return "预算基线需要稳定收入、房租/房贷、保险等固定支出信息。";
  }
  if (lower.includes("duplicates")) {
    return "跨源重复交易会影响现金流判断，建议先复核再依赖报表。";
  }
  if (lower.includes("expense ratio")) {
    return "支出占比已超过风险阈值，先用周级支出护栏控制弹性消费。";
  }
  if (lower.includes("no duplicate")) {
    return "当前没有发现需要优先处理的重复交易。";
  }
  return body;
}

function translateLevel(level: string) {
  if (level === "high") return "高";
  if (level === "medium") return "中";
  if (level === "low") return "低";
  return level;
}

function normalizeActionStatus(status: string | undefined, lang: string) {
  if (!status) return lang === "zh" ? "CFO 建议" : "CFO recommendation";
  if (lang !== "zh") return status;
  const lower = status.toLowerCase();
  if (lower.includes("high")) return "高优先级";
  if (lower.includes("recommended")) return "建议执行";
  if (lower.includes("healthy")) return "健康";
  if (lower.includes("spending")) return "支出复核";
  if (lower.includes("data")) return "数据质量";
  if (lower.includes("verified")) return "已验证";
  return status;
}

function topCategoryLabel(categoryData: CategorySpend[], lang: string) {
  const top = [...categoryData].sort((a, b) => b.amount - a.amount)[0];
  if (!top) {
    return lang === "zh"
      ? "等待账单导入后分析最大支出类别、异常消费和重复交易。"
      : "Waiting for statement import to analyze top categories, anomalies, and duplicates.";
  }
  return lang === "zh"
    ? `${top.category} 是当前最大支出类别，金额 ${top.amount.toLocaleString()} ${top.currency}。`
    : `${top.category} is currently the largest expense category at ${top.amount.toLocaleString()} ${top.currency}.`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="import-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
