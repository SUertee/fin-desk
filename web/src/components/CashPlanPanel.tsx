import { useEffect, useMemo, useState } from "react";
import { Bot, CalendarDays, ChevronDown, Pencil, Plus, Save, SlidersHorizontal, Trash2, WalletCards } from "lucide-react";

import { useI18n } from "../i18n";
import { fetchCashPlan, saveCashPlan, type CashPlan, type CashPlanEntry, type CashPlanKind, type CashPlanResponse } from "../services/financeApi";

type Props = { userId: string; onAskCfo?: (question: string) => void; onOpenSettings?: () => void };

const kindLabels: Record<CashPlanKind, { zh: string; en: string }> = {
  income: { zh: "收入", en: "Income" }, housing: { zh: "房租", en: "Housing" },
  debt: { zh: "债务", en: "Debt" }, budget: { zh: "生活预算", en: "Living budget" },
  purchase: { zh: "计划购买", en: "Planned purchase" }, other: { zh: "其他", en: "Other" },
};

function blankEntry(): CashPlanEntry {
  return { id: `plan-${Date.now()}`, name: "", kind: "other", amount: 0,
    due_date: new Date().toISOString().slice(0, 10), recurrence: "once",
    recurring_amount: null, remaining_occurrences: null, outstanding_balance: null,
    essential: true, status: "active", notes: "" };
}

function money(value: number, currency = "CNY") {
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
}

export function CashPlanPanel({ userId, onAskCfo, onOpenSettings }: Props) {
  const { lang } = useI18n();
  const zh = lang === "zh";
  const [data, setData] = useState<CashPlanResponse | null>(null);
  const [draft, setDraft] = useState<CashPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [isManaging, setIsManaging] = useState(false);
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [showAllEntries, setShowAllEntries] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    fetchCashPlan(userId).then((next) => {
      if (live) { setData(next); setDraft(next.configured ? next.plan : null); setError(""); }
    }).catch((err) => live && setError(String(err))).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [userId]);

  const grouped = useMemo(() => (draft?.entries ?? [])
    .filter((entry) => entry.kind !== "income" && entry.kind !== "housing")
    .slice().sort((a, b) => a.due_date.localeCompare(b.due_date)), [draft?.entries]);
  const updateEntry = (id: string, patch: Partial<CashPlanEntry>) => setDraft((current) => current ? {
    ...current, entries: current.entries.map((entry) => entry.id === id ? { ...entry, ...patch } : entry),
  } : current);
  const addEntry = () => {
    const entry = blankEntry();
    setDraft((current) => current ? { ...current, entries: [...current.entries, entry] } : current);
    setShowAllEntries(true);
    setEditingEntryId(entry.id);
  };

  const persist = async () => {
    if (!draft) return;
    setSaving(true); setError("");
    try {
      const next = await saveCashPlan(userId, {
        currency: draft.currency, cash_balance: Number(draft.cash_balance),
        daily_budget: Number(draft.daily_budget), monthly_budget: Number(draft.monthly_budget),
        entries: draft.entries.filter((entry) => entry.name.trim() && Number(entry.amount) > 0),
      });
      setData(next); setDraft(next.plan);
    } catch (err) { setError(String(err)); } finally { setSaving(false); }
  };

  if (loading) return <section className="cash-plan-panel cash-plan-loading">{zh ? "正在计算现金流…" : "Calculating cash flow…"}</section>;
  if (data && !data.configured) return <section className="cash-plan-panel cash-plan-error"><strong>{zh ? "现金计划尚未设置" : "Cash plan not configured"}</strong><p>{zh ? "先在设置中填写计划现金、工资、房租和生活预算，FinDesk 才能计算未来余额。" : "Add cash, income, rent and a living budget in Settings before forecasting."}</p><button type="button" onClick={onOpenSettings}>{zh ? "前往设置" : "Open settings"}</button></section>;
  if (!draft || !data) return <section className="cash-plan-panel cash-plan-error">{error || (zh ? "现金计划暂时无法加载。" : "The cash plan could not be loaded.")}</section>;
  const p = data.projection;
  return (
    <section className="cash-plan-panel">
      <div className="cash-plan-head">
        <div>
          <span className="cash-plan-kicker"><WalletCards /> {zh ? "现金流计划" : "CASH PLAN"}</span>
          <h2>{zh ? "接下来会发生什么" : "What happens next"}</h2>
          <p>{zh ? "先看资金是否够用，需要时再展开管理债务和计划。" : "Check whether your cash is enough, then manage the underlying plan when needed."}</p>
        </div>
        <div className="cash-plan-head-actions">
          <button type="button" className="cash-plan-manage" aria-expanded={isManaging} onClick={() => setIsManaging((value) => !value)}>
            <SlidersHorizontal /> {isManaging ? (zh ? "收起管理" : "Close manager") : (zh ? "管理债务和计划" : "Manage plan")}
            <ChevronDown className={isManaging ? "cash-plan-chevron-open" : ""} />
          </button>
          <button type="button" className="cash-plan-cfo" onClick={() => onAskCfo?.(zh
            ? "请结合我的真实消费流水、现金流计划、债务到期日和生活预算，告诉我未来90天最危险的日期、健身计划是否负担得起，以及具体节流与增收安排。"
            : "Review my actual spending, cash plan, debt due dates, and living budget. Identify the riskiest dates in the next 90 days and give me a concrete savings and income plan.")}> <Bot /> {zh ? "和 CFO 讨论" : "Ask CFO"}</button>
        </div>
      </div>

      <div className="cash-plan-summary">
        <article><span>{zh ? "当前现金" : "Cash now"}</span><strong>{money(p.current_cash, p.currency)}</strong></article>
        <article><span>{zh ? "发薪前安全可花" : "Safe before payday"}</span><strong>{money(p.safe_to_spend_until_next_income, p.currency)}</strong></article>
        <article><span>{zh ? "下次工资" : "Next income"}</span><strong>{p.next_income_date ?? "—"}</strong></article>
        <article className={p.funding_gap > 0 ? "cash-plan-risk" : ""}><span>{zh ? "未来资金缺口" : "Projected gap"}</span><strong>{money(p.funding_gap, p.currency)}</strong></article>
      </div>

      <div className="cash-plan-settings-note">
        <span>{zh ? `已知债务 ${money(p.total_debt, p.currency)}。工资、房租和生活预算由个人资料统一管理。` : `Known debt ${money(p.total_debt, p.currency)}. Salary, rent and living budgets are managed in your profile.`}</span>
        <button type="button" onClick={onOpenSettings}>{zh ? "前往设置" : "Open settings"}</button>
      </div>

      {isManaging && <div className="cash-plan-editor">
        <div className="cash-plan-editor-head">
          <div><strong>{zh ? "债务和计划" : "Debts and plans"}</strong><span>{zh ? `共 ${grouped.length} 项，先显示最近到期` : `${grouped.length} items, nearest due first`}</span></div>
          <button type="button" className="cash-plan-add" onClick={addEntry}><Plus /> {zh ? "添加一项" : "Add item"}</button>
        </div>
        <div className="cash-plan-entry-list">
          {grouped.slice(0, showAllEntries ? grouped.length : 5).map((entry) => <article key={entry.id} className={`cash-plan-entry ${entry.status === "paused" ? "cash-plan-paused" : ""}`}>
            <div className="cash-plan-entry-summary">
              <div className="cash-plan-entry-name"><strong>{entry.name || (zh ? "未命名项目" : "Untitled item")}</strong><span>{zh ? kindLabels[entry.kind].zh : kindLabels[entry.kind].en} · {entry.due_date}{entry.recurrence === "monthly" ? (zh ? " · 每月" : " · monthly") : ""}</span></div>
              <strong className="cash-plan-entry-amount">{money(entry.amount, draft.currency)}</strong>
              <button type="button" className="cash-plan-edit-button" aria-expanded={editingEntryId === entry.id} onClick={() => setEditingEntryId((current) => current === entry.id ? null : entry.id)}><Pencil /> {zh ? "编辑" : "Edit"}</button>
            </div>
            {editingEntryId === entry.id && <div className="cash-plan-entry-form">
              <label>{zh ? "名称" : "Name"}<input value={entry.name} onChange={(e) => updateEntry(entry.id, { name: e.target.value })} /></label>
              <label>{zh ? "类型" : "Type"}<select value={entry.kind} onChange={(e) => updateEntry(entry.id, { kind: e.target.value as CashPlanKind })}>{Object.entries(kindLabels).map(([key, label]) => <option value={key} key={key}>{zh ? label.zh : label.en}</option>)}</select></label>
              <label>{zh ? "金额" : "Amount"}<input type="number" value={entry.amount} onChange={(e) => updateEntry(entry.id, { amount: Number(e.target.value) })} /></label>
              <label>{zh ? "到期日" : "Due date"}<input type="date" value={entry.due_date} onChange={(e) => updateEntry(entry.id, { due_date: e.target.value })} /></label>
              <label>{zh ? "频率" : "Repeat"}<select value={entry.recurrence} onChange={(e) => updateEntry(entry.id, { recurrence: e.target.value as "once" | "monthly" })}><option value="once">{zh ? "一次" : "Once"}</option><option value="monthly">{zh ? "每月" : "Monthly"}</option></select></label>
              <label>{zh ? "剩余期数" : "Periods left"}<input type="number" min="1" value={entry.remaining_occurrences ?? ""} placeholder={entry.recurrence === "monthly" ? "12" : "1"} onChange={(e) => updateEntry(entry.id, { remaining_occurrences: e.target.value ? Number(e.target.value) : null })} /></label>
              {entry.kind === "debt" && <label>{zh ? "剩余债务" : "Debt balance"}<input type="number" value={entry.outstanding_balance ?? ""} placeholder="—" onChange={(e) => updateEntry(entry.id, { outstanding_balance: e.target.value ? Number(e.target.value) : null })} /></label>}
              <label>{zh ? "是否计入" : "Status"}<select value={entry.status} onChange={(e) => updateEntry(entry.id, { status: e.target.value as "active" | "paused" })}><option value="active">{zh ? "计入计划" : "Active"}</option><option value="paused">{zh ? "暂不计入" : "Paused"}</option></select></label>
              <button type="button" className="cash-plan-delete-button" onClick={() => { setDraft({ ...draft, entries: draft.entries.filter((item) => item.id !== entry.id) }); setEditingEntryId(null); }}><Trash2 /> {zh ? "删除此项" : "Delete item"}</button>
            </div>}
          </article>)}
        </div>
        {grouped.length > 5 && <button type="button" className="cash-plan-show-all" onClick={() => setShowAllEntries((value) => !value)}>{showAllEntries ? (zh ? "收起其余项目" : "Show fewer") : (zh ? `查看其余 ${grouped.length - 5} 项` : `Show ${grouped.length - 5} more`)}</button>}

        <div className="cash-plan-footer">
          <button type="button" className="cash-plan-save" disabled={saving} onClick={persist}><Save /> {saving ? (zh ? "保存中…" : "Saving…") : (zh ? "保存并重新计算" : "Save and recalculate")}</button>
        </div>
      </div>}
      {error && <p className="cash-plan-error">{error}</p>}

      <div className="cash-plan-timeline">
        <div className="cash-plan-timeline-title"><CalendarDays /> {zh ? `未来 ${isManaging ? 8 : 5} 笔现金事件` : `Next ${isManaging ? 8 : 5} cash events`}</div>
        {p.events.slice(0, isManaging ? 8 : 5).map((event) => <div className="cash-plan-event" key={`${event.entry_id}-${event.date}`}>
          <time>{event.date}</time><span>{event.name}</span><strong className={event.amount < 0 ? "negative" : "positive"}>{event.amount < 0 ? "−" : "+"}{money(Math.abs(event.amount), p.currency)}</strong><em>{zh ? "余" : "bal."} {money(event.running_balance, p.currency)}</em>
        </div>)}
      </div>
    </section>
  );
}
