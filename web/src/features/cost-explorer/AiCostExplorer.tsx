import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronLeft,
  CircleDollarSign,
  CloudOff,
  Coins,
  Database,
  RefreshCw,
  ServerCog,
  WalletCards,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useI18n } from "../../i18n";
import type {
  AiCostBreakdownItem,
  AiCostItem,
  MoneyAmount,
} from "../../services/financeApi";
import {
  currentMonthValue,
  useAiCostExplorer,
} from "./useAiCostExplorer";

type AiCostExplorerProps = {
  userId: string;
  onBack: () => void;
};

const REPORTING_CURRENCIES = ["CNY", "USD", "AUD"];

export function AiCostExplorer({ userId, onBack }: AiCostExplorerProps) {
  const { lang } = useI18n();
  const [month, setMonth] = useState(currentMonthValue);
  const [currencyOverride, setCurrencyOverride] = useState<string>();
  const [selectedItem, setSelectedItem] = useState<AiCostItem | null>(null);
  const { data, loading, error, reload } = useAiCostExplorer(
    userId,
    month,
    currencyOverride
  );

  const currency = data?.reporting_currency ?? currencyOverride ?? "CNY";

  return (
    <section className="cost-explorer" aria-label="AI Cost Explorer">
      <header className="cost-explorer-head">
        <div className="cost-explorer-title-row">
          <button type="button" className="cost-back" onClick={onBack}>
            <ChevronLeft />
            {lang === "zh" ? "返回分类" : "Back to categories"}
          </button>
          <div className="cost-title-mark"><Coins /></div>
          <div>
            <div className="cost-kicker">AI COSTS · PRODUCT CATEGORY</div>
            <h2>{lang === "zh" ? "AI 成本" : "AI Costs"}</h2>
            <p>
              {lang === "zh"
                ? "把模型 API 消耗作为真实财务支出管理，并保留原币与历史汇率证据。"
                : "Manage model API usage as real financial spend with native-currency and historical FX evidence."}
            </p>
          </div>
        </div>
        <div className="cost-controls">
          <label>
            <span>{lang === "zh" ? "月份" : "Period"}</span>
            <input
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
          <label>
            <span>{lang === "zh" ? "报告货币" : "Reporting currency"}</span>
            <select
              value={currency}
              onChange={(event) => setCurrencyOverride(event.target.value)}
            >
              {REPORTING_CURRENCIES.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {loading && <CostLoading />}
      {!loading && error && <CostError message={error} onRetry={reload} />}
      {!loading && !error && data?.status === "empty" && (
        <CostEmpty currency={currency} />
      )}
      {!loading && !error && data && data.status !== "empty" && (
        <>
          <CoverageBanner data={data} />
          <SummaryCards data={data} />
          <div className="cost-analytics-grid">
            <CostTrend data={data.trend} currency={data.reporting_currency} />
            <CostBreakdown
              items={data.breakdowns.providers}
              currency={data.reporting_currency}
            />
          </div>
          <CostItems
            items={data.items}
            currency={data.reporting_currency}
            onSelect={setSelectedItem}
          />
        </>
      )}

      {selectedItem && (
        <CostDetailDrawer
          item={selectedItem}
          reportingCurrency={currency}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </section>
  );
}

function CoverageBanner({ data }: { data: NonNullable<ReturnType<typeof useAiCostExplorer>["data"]> }) {
  const { lang } = useI18n();
  const partial = data.status === "partial";
  return (
    <div className={`cost-coverage ${partial ? "cost-coverage-partial" : ""}`}>
      <div className="cost-coverage-icon">
        {partial ? <AlertTriangle /> : <CheckCircle2 />}
      </div>
      <div>
        <strong>
          {partial
            ? lang === "zh" ? "成本覆盖不完整" : "Cost coverage is partial"
            : lang === "zh" ? "本期 API 成本已完成换算" : "API costs are fully converted"}
        </strong>
        <span>
          {partial
            ? lang === "zh"
              ? "缺少价格或历史汇率的运行不会计入汇总金额；原币记录仍保留。"
              : "Runs missing pricing or historical FX are excluded from totals while native amounts remain visible."
            : lang === "zh"
              ? `${data.coverage.billable_run_count} 次计费运行 · ${data.coverage.provider_count} 个供应商`
              : `${data.coverage.billable_run_count} billable runs · ${data.coverage.provider_count} providers`}
        </span>
      </div>
      <div className="cost-coverage-facts">
        <span>{data.reporting_currency}</span>
        <span>
          FX {data.coverage.latest_exchange_rate_date ?? (lang === "zh" ? "同币种" : "identity")}
        </span>
      </div>
    </div>
  );
}

function SummaryCards({ data }: { data: NonNullable<ReturnType<typeof useAiCostExplorer>["data"]> }) {
  const { lang } = useI18n();
  const budget = data.summary.budget;
  return (
    <div className="cost-summary-grid">
      <SummaryCard
        icon={<CircleDollarSign />}
        label={lang === "zh" ? "已追踪 AI 成本" : "Tracked AI cost"}
        value={formatMoneyOrUnavailable(data.summary.tracked_total, lang)}
        note={
          data.status === "partial"
            ? lang === "zh" ? "等待缺失成本完成换算" : "Waiting for missing cost conversion"
            : lang === "zh" ? "本期可审计合计" : "Auditable period total"
        }
        tone={data.status === "partial" ? "watch" : "good"}
      />
      <SummaryCard
        icon={<ServerCog />}
        label={lang === "zh" ? "API 使用费用" : "API usage"}
        value={formatMoneyOrUnavailable(data.summary.api_usage_total, lang)}
        note={lang === "zh" ? "来自 FinDesk Agent Runs" : "From FinDesk Agent Runs"}
      />
      <SummaryCard
        icon={<WalletCards />}
        label={lang === "zh" ? "AI 订阅" : "AI subscriptions"}
        value={lang === "zh" ? "未连接" : "Not connected"}
        note={lang === "zh" ? "不会估算或伪造订阅费用" : "Subscription spend is never estimated"}
        tone="muted"
      />
      <SummaryCard
        icon={<Bot />}
        label={lang === "zh" ? "月度预算" : "Monthly budget"}
        value={budgetValue(budget.status, budget.utilization_percent, lang)}
        note={budget.limit ? formatMoney(budget.limit) : lang === "zh" ? "在设置中配置" : "Configure in Settings"}
        tone={budget.status === "over_budget" ? "risk" : budget.status === "watch" ? "watch" : "good"}
      />
    </div>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  note,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
  tone?: "default" | "good" | "watch" | "risk" | "muted";
}) {
  return (
    <article className={`cost-summary-card cost-tone-${tone}`}>
      <div className="cost-summary-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function CostTrend({
  data,
  currency,
}: {
  data: Array<{ date: string; reporting_total: MoneyAmount | null; run_count: number }>;
  currency: string;
}) {
  const { lang } = useI18n();
  const chartData = data.map((point) => ({
    date: point.date.slice(5),
    cost: point.reporting_total ? Number(point.reporting_total.amount) : null,
    runs: point.run_count,
  }));
  return (
    <article className="cost-panel cost-trend-panel">
      <div className="cost-panel-head">
        <div>
          <span>SPEND VELOCITY</span>
          <h3>{lang === "zh" ? "每日 API 成本" : "Daily API cost"}</h3>
        </div>
        <small>{currency}</small>
      </div>
      {chartData.length > 0 ? (
        <div className="cost-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 12, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#709b37" stopOpacity={0.32} />
                  <stop offset="100%" stopColor="#709b37" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e9ece5" strokeDasharray="4 5" vertical={false} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: "#809087", fontSize: 11 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: "#809087", fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => formatMoney({ amount: String(value), currency })}
                contentStyle={{ border: "1px solid #dfe5df", borderRadius: 12, boxShadow: "0 12px 28px rgba(7,31,24,.1)" }}
              />
              <Area type="monotone" dataKey="cost" stroke="#4f7f2a" strokeWidth={2.5} fill="url(#costFill)" connectNulls={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="cost-panel-empty">{lang === "zh" ? "暂无趋势数据" : "No trend data"}</div>
      )}
    </article>
  );
}

function CostBreakdown({
  items,
  currency,
}: {
  items: AiCostBreakdownItem[];
  currency: string;
}) {
  const { lang } = useI18n();
  return (
    <article className="cost-panel">
      <div className="cost-panel-head">
        <div>
          <span>PROVIDER MIX</span>
          <h3>{lang === "zh" ? "供应商分布" : "Provider breakdown"}</h3>
        </div>
        <small>{items.length} {lang === "zh" ? "个供应商" : "providers"}</small>
      </div>
      {items.length > 0 ? (
        <div className="cost-breakdown-list">
          {items.map((item) => (
            <div key={item.key} className="cost-breakdown-row">
              <div className="cost-breakdown-copy">
                <strong>{providerLabel(item.label)}</strong>
                <span>{item.run_count} runs · {Number(item.share_percent).toFixed(1)}%</span>
              </div>
              <div className="cost-breakdown-value">
                <strong>{formatMoney(item.reporting_total)}</strong>
                <div><span style={{ width: `${Math.max(3, Number(item.share_percent))}%` }} /></div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="cost-panel-empty">
          {lang === "zh" ? "覆盖不完整，暂不计算供应商占比" : `Partial coverage prevents ${currency} provider shares`}
        </div>
      )}
    </article>
  );
}

function CostItems({
  items,
  currency,
  onSelect,
}: {
  items: AiCostItem[];
  currency: string;
  onSelect: (item: AiCostItem) => void;
}) {
  const { lang } = useI18n();
  return (
    <article className="cost-items-panel">
      <div className="cost-panel-head">
        <div>
          <span>COST LEDGER</span>
          <h3>{lang === "zh" ? "AI 成本记录" : "AI cost items"}</h3>
        </div>
        <small>{items.length} {lang === "zh" ? "条运行" : "runs"}</small>
      </div>
      <div className="cost-items-table" role="table">
        <div className="cost-items-head" role="row">
          <span>{lang === "zh" ? "时间" : "Time"}</span>
          <span>{lang === "zh" ? "供应商 / 模型" : "Provider / model"}</span>
          <span>{lang === "zh" ? "入口" : "Entrypoint"}</span>
          <span>{lang === "zh" ? "原币" : "Native cost"}</span>
          <span>{currency}</span>
          <span />
        </div>
        {items.map((item) => (
          <button
            type="button"
            role="row"
            key={item.request_id}
            className="cost-item-row"
            onClick={() => onSelect(item)}
          >
            <span>{formatDate(item.occurred_at, lang)}</span>
            <span className="cost-item-model">
              <strong>{item.providers.map(providerLabel).join(", ") || "Unknown"}</strong>
              <small>{item.models.join(", ") || "Model unavailable"}</small>
            </span>
            <span className="cost-entrypoint">{item.entrypoint}</span>
            <span>{item.billing_totals.map(formatMoney).join(" + ") || "Unavailable"}</span>
            <span className={item.status === "partial" ? "cost-partial-text" : ""}>
              {item.reporting_total ? formatMoney(item.reporting_total) : lang === "zh" ? "待换算" : "Pending"}
            </span>
            <ArrowRight />
          </button>
        ))}
      </div>
    </article>
  );
}

function CostDetailDrawer({
  item,
  reportingCurrency,
  onClose,
}: {
  item: AiCostItem;
  reportingCurrency: string;
  onClose: () => void;
}) {
  const { lang } = useI18n();
  return (
    <div className="cost-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="cost-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="AI cost detail"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span>AGENT RUN COST</span>
            <h3>{item.providers.map(providerLabel).join(" + ") || "AI provider"}</h3>
          </div>
          <button type="button" onClick={onClose} title="Close"><X /></button>
        </header>
        <div className="cost-drawer-total">
          <span>{lang === "zh" ? "报告金额" : "Reporting total"}</span>
          <strong>{item.reporting_total ? formatMoney(item.reporting_total) : lang === "zh" ? "无法换算" : "Unavailable"}</strong>
          <small>{formatDate(item.occurred_at, lang)} · {item.entrypoint}</small>
        </div>
        <DrawerSection title={lang === "zh" ? "原币账单" : "Native billing"} icon={<Coins />}>
          {item.billing_totals.length > 0
            ? item.billing_totals.map((amount) => (
                <StatusPair key={amount.currency} label={amount.currency} value={formatMoney(amount)} />
              ))
            : <p className="cost-drawer-note">{lang === "zh" ? "该运行缺少供应商价格。" : "Provider pricing is missing for this run."}</p>}
        </DrawerSection>
        <DrawerSection title={lang === "zh" ? "汇率证据" : "Exchange-rate evidence"} icon={<Database />}>
          {item.exchange_rate_snapshots.length > 0 ? item.exchange_rate_snapshots.map((snapshot) => (
            <div className="cost-fx-card" key={`${snapshot.billing_currency}-${snapshot.exchange_rate_date}`}>
              <strong>{snapshot.billing_currency} → {snapshot.reporting_currency}</strong>
              <span>1 {snapshot.billing_currency} = {snapshot.exchange_rate} {snapshot.reporting_currency}</span>
              <small>{snapshot.exchange_rate_date} · {snapshot.exchange_rate_source}</small>
            </div>
          )) : (
            <p className="cost-drawer-note">
              {item.billing_totals.every((amount) => amount.currency === reportingCurrency)
                ? lang === "zh" ? "原币与报告货币相同，无需外汇换算。" : "Native and reporting currencies match; no FX conversion was needed."
                : lang === "zh" ? "没有可用的历史汇率快照。" : "No historical exchange-rate snapshot is available."}
            </p>
          )}
        </DrawerSection>
        <DrawerSection title={lang === "zh" ? "运行标识" : "Run reference"} icon={<ServerCog />}>
          <code>{item.request_id}</code>
          <p className="cost-drawer-note">
            {lang === "zh"
              ? "Token、阶段耗时和 trace 保留在 Developer Observability，不在财务主页面常驻。"
              : "Tokens, stage latency, and trace details remain in Developer Observability."}
          </p>
        </DrawerSection>
        {item.issues.length > 0 && (
          <DrawerSection title={lang === "zh" ? "数据缺口" : "Coverage issues"} icon={<AlertTriangle />}>
            <ul>{item.issues.map((issue) => <li key={issue}>{issueLabel(issue, lang)}</li>)}</ul>
          </DrawerSection>
        )}
      </aside>
    </div>
  );
}

function DrawerSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return <section className="cost-drawer-section"><h4>{icon}{title}</h4>{children}</section>;
}

function StatusPair({ label, value }: { label: string; value: string }) {
  return <div className="cost-status-pair"><span>{label}</span><strong>{value}</strong></div>;
}

function CostLoading() {
  return <div className="cost-state"><RefreshCw className="cost-spin" /><strong>Loading AI cost ledger</strong><span>Reconciling native charges and historical exchange rates.</span></div>;
}

function CostError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { lang } = useI18n();
  return <div className="cost-state cost-state-error"><CloudOff /><strong>{lang === "zh" ? "AI 成本暂时不可用" : "AI costs are unavailable"}</strong><span>{message}</span><button type="button" onClick={onRetry}><RefreshCw />{lang === "zh" ? "重试" : "Retry"}</button></div>;
}

function CostEmpty({ currency }: { currency: string }) {
  const { lang } = useI18n();
  return <div className="cost-state cost-state-empty"><div className="cost-empty-orbit"><Bot /><span /></div><strong>{lang === "zh" ? "本期还没有可计费的 Agent Run" : "No billable Agent Runs in this period"}</strong><span>{lang === "zh" ? `开始使用 CFO 后，API 原币费用会在这里换算为 ${currency}。` : `Once the CFO uses a model API, native charges will be reported here in ${currency}.`}</span></div>;
}

function formatMoney(amount: MoneyAmount) {
  const value = Number(amount.amount);
  if (!Number.isFinite(value)) return `${amount.amount} ${amount.currency}`;
  const maxDigits = Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 6 : 2;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: amount.currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: maxDigits,
  }).format(value);
}

function formatMoneyOrUnavailable(amount: MoneyAmount | null, lang: string) {
  return amount ? formatMoney(amount) : lang === "zh" ? "数据不完整" : "Incomplete";
}

function formatDate(value: string, lang: string) {
  const parsed = new Date(value);
  return parsed.toLocaleString(lang === "zh" ? "zh-CN" : "en-AU", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function providerLabel(value: string) {
  return value === "deepseek" ? "DeepSeek" : value === "openai" ? "OpenAI" : value;
}

function budgetValue(status: string, utilization: string | null, lang: string) {
  if (status === "not_configured") return lang === "zh" ? "未配置" : "Not set";
  if (status === "unavailable") return lang === "zh" ? "不可计算" : "Unavailable";
  if (utilization == null) return lang === "zh" ? "已配置" : "Configured";
  return `${Number(utilization).toFixed(1)}%`;
}

function issueLabel(issue: string, lang: string) {
  const labels: Record<string, { zh: string; en: string }> = {
    missing_exchange_rate: { zh: "缺少该运行日期的历史汇率", en: "Historical exchange rate is missing" },
    missing_pricing: { zh: "缺少供应商模型价格", en: "Provider model pricing is missing" },
    historical_v1_detail_unavailable: { zh: "历史记录没有阶段级成本明细", en: "Historical run lacks stage-level cost detail" },
  };
  return labels[issue]?.[lang === "zh" ? "zh" : "en"] ?? issue;
}
