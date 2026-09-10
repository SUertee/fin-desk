import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpRight,
  Bus,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  FileUp,
  Moon,
  PackageOpen,
  Plus,
  ReceiptText,
  RefreshCw,
  RotateCcw,
  ShoppingBasket,
  Sun,
  Sunrise,
  WalletCards,
  X,
} from "lucide-react";

import { currencySymbol } from "../components/MetricsCards";
import { useI18n } from "../i18n";
import { fetchCashPlan, type CashPlanResponse, type DataSourceStatus, type ManualTransactionInput } from "../services/financeApi";
import { financeCategoryLabel, financeSourceLabel } from "../utils/financeLabels";

type TableTransaction = {
  id: string | number;
  date: string;
  month: string;
  merchant: string;
  category: string;
  amount: number;
  gross_amount?: number;
  currency: string;
  source: string;
  payment_method: string;
  status?: string;
  direction?: string;
  type?: string;
  created_at?: string;
  raw?: unknown;
  is_duplicate: boolean;
};

type Props = {
  userId: string;
  dataSourceStatus?: DataSourceStatus | null;
  loading: boolean;
  errMsg: string | null;
  isUploading: boolean;
  primaryCurrency: string;
  tableTransactions: TableTransaction[];
  onReload: () => void;
  onOpenLedger: () => void;
  onOpenCashPlan: () => void;
  onUploadStatement: (file: File) => void;
  onCreateManualTransaction: (input: ManualTransactionInput) => Promise<void>;
};

type NeedItem = {
  id: string;
  title: string;
  body: string;
  action: string;
  icon: typeof AlertTriangle;
  tone: "warn" | "info";
  run: () => void;
};

type EntryType = "expense" | "income" | "refund" | "transfer";
type TemplateId = "breakfast" | "lunch" | "dinner" | "transport" | "groceries" | "daily";

export function FinanceWorkspacePage({
  userId,
  dataSourceStatus,
  loading,
  errMsg,
  isUploading,
  primaryCurrency,
  tableTransactions,
  onReload,
  onOpenLedger,
  onOpenCashPlan,
  onUploadStatement,
  onCreateManualTransaction,
}: Props) {
  const { lang } = useI18n();
  const [cashPlan, setCashPlan] = useState<CashPlanResponse | null>(null);
  const [cashPlanState, setCashPlanState] = useState<"loading" | "ready" | "unconfigured" | "error">("loading");
  const [entryOpen, setEntryOpen] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState<TemplateId | null>(null);
  const [entryType, setEntryType] = useState<EntryType>("expense");
  const [entryAmount, setEntryAmount] = useState("");
  const [entryMerchant, setEntryMerchant] = useState("");
  const [entryPayment, setEntryPayment] = useState("支付宝");
  const [entryDestination, setEntryDestination] = useState("微信");
  const [entryCategory, setEntryCategory] = useState("other");
  const [entryNote, setEntryNote] = useState("");
  const [entryDetailsOpen, setEntryDetailsOpen] = useState(false);
  const [entrySaving, setEntrySaving] = useState(false);
  const [entryError, setEntryError] = useState("");
  const sym = currencySymbol(primaryCurrency);
  const today = new Date().toLocaleDateString("sv-SE");

  useEffect(() => {
    let active = true;
    setCashPlanState("loading");
    fetchCashPlan(userId)
      .then((result) => {
        if (!active) return;
        setCashPlan(result);
        setCashPlanState(result.configured ? "ready" : "unconfigured");
      })
      .catch(() => {
        if (!active) return;
        setCashPlan(null);
        setCashPlanState("error");
      });
    return () => { active = false; };
  }, [userId]);

  const period = useMemo(() => {
    if (!tableTransactions.length) return null;
    const dates = tableTransactions.map((transaction) => transaction.date).sort();
    return { from: dates[0], to: dates.at(-1) as string };
  }, [tableTransactions]);

  const dataAgeDays = period?.to
    ? Math.max(0, Math.floor((dateValue(today) - dateValue(period.to)) / 86400000))
    : null;
  const projection = cashPlan?.configured ? cashPlan.projection : null;
  const nextPayment = projection?.events.find((event) => event.date >= today && event.amount < 0 && event.essential)
    ?? projection?.events.find((event) => event.amount < 0 && event.essential)
    ?? null;
  const daysUntilIncome = projection?.next_income_date
    ? Math.max(0, Math.ceil((dateValue(projection.next_income_date) - dateValue(today)) / 86400000))
    : null;
  const latestDaySpend = useMemo(() => tableTransactions
    .filter((transaction) => !transaction.is_duplicate && transaction.date === period?.to && transaction.amount < 0)
    .reduce((sum, transaction) => sum + Math.abs(transaction.amount), 0), [tableTransactions, period?.to]);

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

  const needs: NeedItem[] = [];
  if (!tableTransactions.length) {
    needs.push({
      id: "first-import",
      title: lang === "zh" ? "导入第一份账单" : "Import your first statement",
      body: lang === "zh" ? "导入后才能查看真实消费、分类和每天的收支。" : "Import data to review spending and categories.",
      action: lang === "zh" ? "选择账单" : "Choose file",
      icon: FileUp,
      tone: "info",
      run: upload,
    });
  } else if (dataAgeDays != null && dataAgeDays >= 7) {
    needs.push({
      id: "stale-ledger",
      title: lang === "zh" ? `流水已有 ${dataAgeDays} 天未更新` : `Ledger is ${dataAgeDays} days old`,
      body: lang === "zh" ? `当前消费分析只覆盖到 ${dateLabel(period?.to, lang)}。` : `Spending data currently ends on ${period?.to}.`,
      action: lang === "zh" ? "更新账单" : "Update ledger",
      icon: RefreshCw,
      tone: "info",
      run: upload,
    });
  }
  if (projection?.funding_gap && projection.funding_gap > 0) {
    needs.push({
      id: "funding-gap",
      title: lang === "zh" ? "未来计划存在资金缺口" : "Your plan has a funding gap",
      body: lang === "zh" ? `按当前计划，最低还缺 ${formatMoney(projection.funding_gap, sym)}。` : `The current plan falls short by ${formatMoney(projection.funding_gap, sym)}.`,
      action: lang === "zh" ? "调整计划" : "Adjust plan",
      icon: AlertTriangle,
      tone: "warn",
      run: onOpenCashPlan,
    });
  }
  const visibleNeeds = needs.slice(0, 2);

  const todayTransactions = useMemo(() => [...tableTransactions]
    .filter((transaction) => !transaction.is_duplicate && transaction.date === today)
    .sort((a, b) => (b.created_at || b.date).localeCompare(a.created_at || a.date)), [tableTransactions, today]);

  const todaySummary = useMemo(() => todayTransactions.reduce((summary, transaction) => {
    const type = manualEntryType(transaction.raw);
    if (type === "transfer") return summary;
    if (type === "refund") summary.refund += Math.abs(transaction.amount);
    else if (transaction.amount < 0) summary.expense += Math.abs(transaction.amount);
    else summary.income += transaction.amount;
    return summary;
  }, { expense: 0, income: 0, refund: 0 }), [todayTransactions]);

  const templateTotals = useMemo(() => {
    const totals: Record<TemplateId, number> = { breakfast: 0, lunch: 0, dinner: 0, transport: 0, groceries: 0, daily: 0 };
    for (const transaction of tableTransactions) {
      if (transaction.date !== today || transaction.is_duplicate || transaction.amount >= 0) continue;
      const tag = manualTemplateId(transaction.raw);
      if (tag) totals[tag] += Math.abs(transaction.amount);
    }
    return totals;
  }, [tableTransactions, today]);

  const dynamicTemplates = useMemo(() => rankTemplates(quickTemplates, tableTransactions), [tableTransactions]);

  const openEntry = (templateId: TemplateId | null = null, type: EntryType = "expense") => {
    const template = quickTemplates.find((item) => item.id === templateId);
    setActiveTemplate(templateId);
    setEntryType(type);
    setEntryAmount("");
    setEntryMerchant("");
    setEntryPayment("支付宝");
    setEntryDestination("微信");
    setEntryCategory(template?.category ?? (type === "income" ? "income" : type === "refund" ? "refund" : "other"));
    setEntryNote("");
    setEntryDetailsOpen(Boolean(templateId));
    setEntryError("");
    setEntryOpen(true);
  };

  const saveEntry = async (event: React.FormEvent) => {
    event.preventDefault();
    const amount = Number(entryAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setEntryError(lang === "zh" ? "请输入大于 0 的金额" : "Enter an amount greater than zero");
      return;
    }
    if (entryType === "transfer" && entryPayment === entryDestination) {
      setEntryError(lang === "zh" ? "转出和转入账户不能相同" : "Source and destination must differ");
      return;
    }
    const template = quickTemplates.find((item) => item.id === activeTemplate);
    setEntrySaving(true);
    setEntryError("");
    try {
      await onCreateManualTransaction({
        amount,
        direction: entryType === "income" || entryType === "refund" ? "income" : "expense",
        entry_type: entryType,
        occurred_at: localIsoNow(),
        counterparty: entryMerchant.trim(),
        description: template ? (lang === "zh" ? template.zh : template.en) : entryTypeLabel(entryType, lang),
        category: entryCategory,
        payment_method: entryPayment,
        note: entryNote.trim(),
        meal_tag: activeTemplate === "breakfast" || activeTemplate === "lunch" || activeTemplate === "dinner" ? activeTemplate : undefined,
        template_id: activeTemplate ?? "",
        destination_account: entryType === "transfer" ? entryDestination : "",
      });
      setEntryOpen(false);
    } catch (error) {
      setEntryError(error instanceof Error ? error.message : (lang === "zh" ? "保存失败" : "Failed to save"));
    } finally {
      setEntrySaving(false);
    }
  };

  return (
    <main className="workspace-main today-workspace">
      <section className={`daily-overview ${projection?.funding_gap && projection.funding_gap > 0 ? "daily-overview-risk" : ""}`}>
        <header className="daily-overview-head">
          <div>
            <span className="daily-overview-kicker">{lang === "zh" ? "今日资金状态" : "TODAY'S MONEY"}</span>
            <p>{period?.to ? (lang === "zh" ? `账本更新至 ${dateLabel(period.to, lang)}` : `Ledger updated through ${period.to}`) : (lang === "zh" ? "账本尚未导入" : "No ledger data yet")}</p>
          </div>
          <button type="button" className="daily-plan-link" onClick={onOpenCashPlan}><WalletCards /> {lang === "zh" ? "查看计划" : "View plan"}</button>
        </header>

        <div className="daily-overview-body">
          <div className="daily-overview-primary">
            <span>{lang === "zh" ? "发薪前可自由支配（计划估算）" : "Free to spend before payday (estimate)"}</span>
            <strong>{projection ? formatMoney(projection.safe_to_spend_until_next_income, sym) : "—"}</strong>
            <h1>{projection
              ? projection.safe_to_spend_until_next_income === 0
                ? (lang === "zh" ? "暂时不要安排新增支出" : "Pause new spending for now")
                : (lang === "zh" ? "今天的消费空间" : "Today's spending room")
              : cashPlanState === "unconfigured"
                ? (lang === "zh" ? "先完善现金计划" : "Complete your cash plan")
                : cashPlanState === "error"
                  ? (lang === "zh" ? "现金计划暂时无法读取" : "Cash plan unavailable")
                  : (lang === "zh" ? "正在读取现金计划" : "Loading cash plan")}</h1>
            <p>{projection?.funding_gap && projection.funding_gap > 0
              ? (lang === "zh" ? `未来计划仍有 ${formatMoney(projection.funding_gap, sym)} 缺口，建议先处理必要支出。` : `The current plan still has a ${formatMoney(projection.funding_gap, sym)} gap.`)
              : projection
                ? (lang === "zh" ? "根据计划现金、发薪前必要付款和生活预算估算；实际流水以账本更新时间为准。" : "Estimated from planned cash, commitments and living budget; actual spending follows ledger freshness.")
                : cashPlanState === "unconfigured"
                  ? (lang === "zh" ? "设置计划现金、收入、必要付款和生活预算后，才能计算安全可花。" : "Add cash, income, commitments and a living budget before calculating.")
                  : cashPlanState === "error"
                    ? (lang === "zh" ? "系统没有用默认金额代替缺失数据，请稍后重试。" : "No default amount has been substituted. Try again later.")
                    : (lang === "zh" ? "正在核对计划数据。" : "Checking plan data.")}</p>
          </div>
          <div className="daily-overview-facts">
            <div><span>{lang === "zh" ? "当前计划现金" : "Planned cash"}</span><strong>{projection ? formatMoney(projection.current_cash, sym) : "—"}</strong><em>{cashPlan?.configured ? (lang === "zh" ? `计划更新于 ${dateLabel(cashPlan.plan.updated_at.slice(0, 10), lang)}` : cashPlan.plan.updated_at.slice(0, 10)) : cashPlanState === "unconfigured" ? (lang === "zh" ? "计划尚未设置" : "Plan not configured") : cashPlanState === "error" ? (lang === "zh" ? "数据暂时不可用" : "Data unavailable") : ""}</em></div>
            <div><span>{lang === "zh" ? "下一笔必须支付" : "Next payment"}</span><strong>{nextPayment ? `${dateLabel(nextPayment.date, lang)} · ${nextPayment.name}` : "—"}</strong><em>{nextPayment ? formatMoney(Math.abs(nextPayment.amount), sym) : ""}</em></div>
            <div><span>{lang === "zh" ? "距离下次收入" : "Until next income"}</span><strong>{daysUntilIncome == null ? "—" : (lang === "zh" ? `${daysUntilIncome} 天` : `${daysUntilIncome} days`)}</strong><em>{projection?.next_income_date ?? ""}</em></div>
            <div><span>{lang === "zh" ? "最近有流水的一天" : "Latest ledger day"}</span><strong>{period?.to ? formatMoney(latestDaySpend, sym) : "—"}</strong><em>{period?.to ? dateLabel(period.to, lang) : ""}</em></div>
          </div>
        </div>
      </section>

      {loading && <div className="workspace-inline-state">{lang === "zh" ? "正在加载财务数据…" : "Loading finance data…"}</div>}
      {errMsg && <div className="workspace-inline-state workspace-inline-error">{lang === "zh" && /failed to fetch/i.test(errMsg) ? "无法连接后端服务" : errMsg}<button onClick={onReload} type="button">{lang === "zh" ? "重试" : "Retry"}</button></div>}

      {!loading && !errMsg && (
        <div className="today-workspace-grid">
          <section className="today-bookkeeping-panel">
            <header>
              <div><span>{lang === "zh" ? "快速记一笔" : "QUICK ENTRY"}</span><h2>{lang === "zh" ? "今天发生的每一笔钱" : "Today's money activity"}</h2><p>{lang === "zh" ? "先记下，上传账单后再自动核对。" : "Capture now and reconcile after import."}</p></div>
              <button type="button" className="today-primary-entry" onClick={() => openEntry()}><Plus />{lang === "zh" ? "记一笔" : "New entry"}</button>
            </header>
            <div className="today-money-summary">
              <div><span>{lang === "zh" ? "今日支出" : "Spent today"}</span><strong className="expense">{formatMoney(todaySummary.expense, sym)}</strong></div>
              <div><span>{lang === "zh" ? "今日收入" : "Income today"}</span><strong>{formatMoney(todaySummary.income, sym)}</strong></div>
              <div><span>{lang === "zh" ? "今日退款" : "Refunds today"}</span><strong>{formatMoney(todaySummary.refund, sym)}</strong></div>
              <div><span>{lang === "zh" ? "安全可花" : "Safe to spend"}</span><strong>{projection ? formatMoney(projection.safe_to_spend_until_next_income, sym) : "—"}</strong></div>
            </div>
            <div className="today-template-list">
              {dynamicTemplates.map((template) => {
                const Icon = template.icon;
                const total = templateTotals[template.id];
                return <button type="button" key={template.id} className={total > 0 ? "recorded" : ""} onClick={() => openEntry(template.id)}><span><Icon /></span><div><strong>{lang === "zh" ? template.zh : template.en}</strong><em>{total > 0 ? (lang === "zh" ? `今天 ${formatMoney(total, sym)}` : `${formatMoney(total, sym)} today`) : (lang === "zh" ? "快速记录" : "Quick log")}</em></div>{total > 0 ? <CheckCircle2 /> : <Plus />}</button>;
              })}
            </div>
          </section>
          <section className="workspace-focus-panel">
            <header><div><span>{lang === "zh" ? "需要处理" : "NEEDS ATTENTION"}</span><h2>{visibleNeeds.length ? (lang === "zh" ? `${visibleNeeds.length} 件事情` : `${visibleNeeds.length} items`) : (lang === "zh" ? "今天已处理完成" : "All caught up")}</h2></div></header>
            {visibleNeeds.length ? (
              <div className="workspace-needs-list">
                {visibleNeeds.map((item) => {
                  const Icon = item.icon;
                  return <article key={item.id} className={`workspace-need workspace-need-${item.tone}`}><span className="workspace-need-icon"><Icon /></span><div><strong>{item.title}</strong><p>{item.body}</p></div><button type="button" onClick={item.run}>{item.action}<ArrowRight /></button></article>;
                })}
              </div>
            ) : (
              <div className="workspace-complete"><CheckCircle2 /><div><strong>{lang === "zh" ? "暂时没有必须处理的事项" : "Nothing requires attention"}</strong><p>{lang === "zh" ? "账本和计划会在需要更新时提醒你。" : "FinDesk will surface ledger and plan updates when needed."}</p></div></div>
            )}
          </section>

          <section className="workspace-activity-panel">
            <header><div><span>{lang === "zh" ? "今日流水" : "TODAY'S LEDGER"}</span><h2>{lang === "zh" ? `${todayTransactions.length} 笔资金记录` : `${todayTransactions.length} entries`}</h2></div><button type="button" onClick={onOpenLedger}>{lang === "zh" ? "全部流水" : "Full ledger"}<ArrowRight /></button></header>
            {todayTransactions.length ? (
              <div className="workspace-activity-list">
                {todayTransactions.slice(0, 6).map((transaction) => (
                  <button type="button" key={transaction.id} onClick={onOpenLedger}>
                    <span className="workspace-activity-icon"><ReceiptText /></span>
                    <span className="workspace-activity-copy"><strong>{transaction.merchant || transaction.description || financeCategoryLabel(transaction.category, lang)}</strong><em>{financeCategoryLabel(transaction.category, lang)} · {financeSourceLabel(transaction.source, lang)} · {transactionStatusLabel(transaction, lang)}</em></span>
                    <b className={manualEntryType(transaction.raw) === "transfer" ? "transfer" : transaction.amount < 0 ? "expense" : "income"}>{manualEntryType(transaction.raw) === "transfer" ? "↔" : transaction.amount < 0 ? "−" : "+"}{formatMoney(transactionDisplayAmount(transaction), currencySymbol(transaction.currency))}</b>
                  </button>
                ))}
              </div>
            ) : (
              <div className="workspace-activity-empty"><ReceiptText /><span>{lang === "zh" ? "今天还没有记录，点击“记一笔”开始。" : "No entries today. Use New entry to begin."}</span></div>
            )}
          </section>
        </div>
      )}
      {entryOpen && (
        <><button type="button" className="quick-entry-backdrop" aria-label={lang === "zh" ? "关闭记账" : "Close entry"} onClick={() => setEntryOpen(false)} /><aside className="quick-entry-panel" role="dialog" aria-modal="true" aria-label={lang === "zh" ? "快速记账" : "Quick entry"}>
          <header><div><CircleDollarSign /><span>{lang === "zh" ? "快速记账" : "Quick entry"}</span></div><button type="button" aria-label={lang === "zh" ? "关闭记账" : "Close entry"} onClick={() => setEntryOpen(false)}><X /></button></header>
          <form onSubmit={saveEntry}>
            <div className="quick-entry-title"><span>{lang === "zh" ? "记录" : "Log"}</span><h2>{activeTemplate ? (lang === "zh" ? quickTemplates.find((item) => item.id === activeTemplate)?.zh : quickTemplates.find((item) => item.id === activeTemplate)?.en) : entryTypeLabel(entryType, lang)}</h2><p>{lang === "zh" ? "保存后立即进入今日流水，并等待后续账单核对。" : "Saved to today's ledger and queued for reconciliation."}</p></div>
            <div className="quick-entry-types" aria-label={lang === "zh" ? "交易类型" : "Entry type"}>{entryTypes.map((item) => { const Icon = item.icon; return <button type="button" key={item.id} className={entryType === item.id ? "active" : ""} onClick={() => { setEntryType(item.id); setEntryCategory(item.id === "income" ? "income" : item.id === "refund" ? "refund" : item.id === "transfer" ? "transfer" : activeTemplate ? quickTemplates.find((template) => template.id === activeTemplate)?.category ?? "other" : "other"); if (item.id === "transfer") setEntryDetailsOpen(true); }}><Icon />{lang === "zh" ? item.zh : item.en}</button>; })}</div>
            <label className="quick-entry-amount"><span>{lang === "zh" ? "金额" : "Amount"}</span><div><b>{sym}</b><input autoFocus inputMode="decimal" value={entryAmount} onChange={(event) => setEntryAmount(event.target.value)} placeholder="0.00" /></div></label>
            <button type="button" className="quick-entry-details-toggle" onClick={() => setEntryDetailsOpen((open) => !open)}>{entryDetailsOpen ? (lang === "zh" ? "收起详细信息" : "Hide details") : (lang === "zh" ? "补充商户、分类和账户" : "Add merchant, category and account")}<ChevronDown className={entryDetailsOpen ? "open" : ""} /></button>
            {entryDetailsOpen && <div className="quick-entry-details">
              <label><span>{lang === "zh" ? (entryType === "income" ? "来源（选填）" : "商户（选填）") : "Merchant or source"}</span><input value={entryMerchant} onChange={(event) => setEntryMerchant(event.target.value)} placeholder={lang === "zh" ? "例如：公司食堂、兼职收入" : "e.g. cafeteria or freelance"} /></label>
              <label><span>{lang === "zh" ? (entryType === "transfer" ? "转出账户" : "账户或付款方式") : "Account or payment"}</span><select value={entryPayment} onChange={(event) => setEntryPayment(event.target.value)}><option value="支付宝">支付宝</option><option value="微信">微信</option><option value="银行卡">银行卡</option><option value="现金">现金</option></select></label>
              {entryType === "transfer" && <label><span>{lang === "zh" ? "转入账户" : "Destination account"}</span><select value={entryDestination} onChange={(event) => setEntryDestination(event.target.value)}><option value="支付宝">支付宝</option><option value="微信">微信</option><option value="银行卡">银行卡</option><option value="现金">现金</option></select></label>}
              {entryType !== "transfer" && <label><span>{lang === "zh" ? "分类" : "Category"}</span><select value={entryCategory} onChange={(event) => setEntryCategory(event.target.value)}>{categoryOptions.map((category) => <option key={category.id} value={category.id}>{lang === "zh" ? category.zh : category.en}</option>)}</select></label>}
              <label><span>{lang === "zh" ? "备注（选填）" : "Note (optional)"}</span><input value={entryNote} onChange={(event) => setEntryNote(event.target.value)} /></label>
            </div>}
            {entryError && <p className="quick-entry-error">{entryError}</p>}
            <button type="submit" className="quick-entry-submit" disabled={entrySaving}>{entrySaving ? (lang === "zh" ? "保存中…" : "Saving…") : (lang === "zh" ? "保存到流水" : "Save to ledger")}</button>
          </form>
        </aside></>
      )}
    </main>
  );
}

const quickTemplates = [
  { id: "breakfast" as const, zh: "早餐", en: "Breakfast", icon: Sunrise, category: "dining" },
  { id: "lunch" as const, zh: "午餐", en: "Lunch", icon: Sun, category: "dining" },
  { id: "dinner" as const, zh: "晚餐", en: "Dinner", icon: Moon, category: "dining" },
  { id: "transport" as const, zh: "交通", en: "Transport", icon: Bus, category: "transportation" },
  { id: "groceries" as const, zh: "买菜", en: "Groceries", icon: ShoppingBasket, category: "groceries" },
  { id: "daily" as const, zh: "日用品", en: "Daily goods", icon: PackageOpen, category: "shopping" },
];

const entryTypes = [
  { id: "expense" as const, zh: "支出", en: "Expense", icon: ArrowUpRight },
  { id: "income" as const, zh: "收入", en: "Income", icon: ArrowDownLeft },
  { id: "refund" as const, zh: "退款", en: "Refund", icon: RotateCcw },
  { id: "transfer" as const, zh: "转账", en: "Transfer", icon: ArrowLeftRight },
];

const categoryOptions = [
  { id: "other", zh: "其他", en: "Other" },
  { id: "dining", zh: "餐饮", en: "Dining" },
  { id: "groceries", zh: "买菜日用", en: "Groceries" },
  { id: "transportation", zh: "交通", en: "Transport" },
  { id: "shopping", zh: "购物", en: "Shopping" },
  { id: "housing", zh: "住房", en: "Housing" },
  { id: "healthcare", zh: "健康医疗", en: "Healthcare" },
  { id: "entertainment", zh: "休闲娱乐", en: "Entertainment" },
  { id: "income", zh: "收入", en: "Income" },
  { id: "refund", zh: "退款", en: "Refund" },
];

function manualMetadata(raw: unknown): Record<string, unknown> | null {
  if (!raw) return null;
  let value = raw;
  if (typeof value === "string") {
    try { value = JSON.parse(value); } catch { return null; }
  }
  if (!value || typeof value !== "object") return null;
  const manual = (value as Record<string, unknown>).manual;
  if (!manual || typeof manual !== "object") return null;
  return manual as Record<string, unknown>;
}

function manualTemplateId(raw: unknown): TemplateId | null {
  const manual = manualMetadata(raw);
  const id = manual?.template_id || manual?.meal_tag;
  return quickTemplates.some((template) => template.id === id) ? id as TemplateId : null;
}

function manualEntryType(raw: unknown): EntryType | null {
  const type = manualMetadata(raw)?.entry_type;
  return type === "expense" || type === "income" || type === "refund" || type === "transfer" ? type : null;
}

function transactionDisplayAmount(transaction: TableTransaction): number {
  if (manualEntryType(transaction.raw) === "transfer") {
    const entered = Number(manualMetadata(transaction.raw)?.entered_amount ?? transaction.gross_amount ?? 0);
    return Number.isFinite(entered) ? entered : 0;
  }
  return Math.abs(transaction.amount);
}

function transactionStatusLabel(transaction: TableTransaction, lang: string): string {
  if (transaction.is_duplicate) return lang === "zh" ? "疑似重复" : "Possible duplicate";
  if (transaction.status === "awaiting_statement") return lang === "zh" ? "等待账单核对" : "Awaiting statement";
  if (transaction.source === "manual") return lang === "zh" ? "手动记录" : "Manual entry";
  return lang === "zh" ? "账单已确认" : "Statement confirmed";
}

function entryTypeLabel(type: EntryType, lang: string): string {
  const item = entryTypes.find((entry) => entry.id === type)!;
  return lang === "zh" ? item.zh : item.en;
}

function rankTemplates(templates: typeof quickTemplates, transactions: TableTransaction[]) {
  const hour = new Date().getHours();
  const timePriority: Partial<Record<TemplateId, number>> = hour < 10
    ? { breakfast: 30, transport: 20 }
    : hour < 15
      ? { lunch: 30, transport: 10 }
      : { dinner: 30, groceries: 20, daily: 10 };
  const frequency = transactions.slice(-120).reduce((counts, transaction) => {
    const id = manualTemplateId(transaction.raw);
    if (id) counts[id] = (counts[id] ?? 0) + 1;
    return counts;
  }, {} as Partial<Record<TemplateId, number>>);
  return [...templates].sort((left, right) =>
    ((timePriority[right.id] ?? 0) + (frequency[right.id] ?? 0) * 2)
    - ((timePriority[left.id] ?? 0) + (frequency[left.id] ?? 0) * 2));
}

function dateValue(value: string): number {
  return new Date(`${value}T00:00:00`).getTime();
}

function localIsoNow(): string {
  const now = new Date();
  const offsetMinutes = -now.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const pad = (value: number) => String(value).padStart(2, "0");
  const offsetHours = Math.floor(Math.abs(offsetMinutes) / 60);
  const offsetRemainder = Math.abs(offsetMinutes) % 60;
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}${sign}${pad(offsetHours)}:${pad(offsetRemainder)}`;
}

function dateLabel(value: string | undefined, lang: string): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return lang === "zh" ? `${Number(month)} 月 ${Number(day)} 日` : `${year}-${month}-${day}`;
}

function formatMoney(value: number, symbol: string): string {
  return `${symbol}${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}
