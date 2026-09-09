import { useCallback, useMemo, useState } from "react";
import {
  ArrowUpDown, ChevronLeft, ChevronRight, Download, Eye, EyeOff,
  ReceiptText, Search, X,
} from "lucide-react";

import { useI18n } from "../i18n";
import { financeCategoryLabel, financeSourceLabel } from "../utils/financeLabels";
import { currencySymbol } from "./MetricsCards";

interface Transaction {
  id: string | number;
  date: string;
  month: string;
  merchant: string;
  description: string;
  category: string;
  amount: number;
  gross_amount: number;
  currency: string;
  source: string;
  payment_method: string;
  status: string;
  direction: string;
  type: string;
  created_at: string;
  note: string;
  external_id: string;
  merchant_order_id: string;
  source_file: string;
  raw: unknown;
  matched_sources: string[];
  matched_source_file: string;
  matched_external_id: string;
  matched_merchant_order_id: string;
  matched_raw: unknown;
  is_duplicate: boolean;
}

interface TransactionsTableProps { transactions: Transaction[]; }
type SortKey = "date" | "amount";
type SortDir = "asc" | "desc";

const ITEMS_PER_PAGE = 15;
const GENERIC_LABELS = new Set(["消费", "支出", "付款", "交易", "payment", "purchase"]);

export function TransactionsTable({ transactions }: TransactionsTableProps) {
  const { lang } = useI18n();
  const [currentPage, setCurrentPage] = useState(1);
  const [monthFilter, setMonthFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Transaction | null>(null);

  const months = useMemo(() => {
    const values = new Set(transactions.map((transaction) => transaction.month));
    return Array.from(values).sort().reverse();
  }, [transactions]);

  const filtered = useMemo(() => {
    let result = showDuplicates ? transactions : transactions.filter((transaction) => !transaction.is_duplicate);
    if (monthFilter !== "all") result = result.filter((transaction) => transaction.month === monthFilter);
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (normalizedQuery) {
      result = result.filter((transaction) =>
        [transaction.merchant, transaction.description, transaction.payment_method, transaction.category]
          .some((value) => value.toLocaleLowerCase().includes(normalizedQuery))
      );
    }
    return [...result].sort((left, right) => {
      const diff = sortKey === "amount"
        ? Math.abs(left.amount) - Math.abs(right.amount)
        : left.date.localeCompare(right.date);
      return sortDir === "desc" ? -diff : diff;
    });
  }, [monthFilter, query, showDuplicates, sortDir, sortKey, transactions]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentTransactions = filtered.slice(startIndex, endIndex);
  const duplicateCount = transactions.filter((transaction) => transaction.is_duplicate).length;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((direction) => direction === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
    setCurrentPage(1);
  };

  const exportCSV = useCallback(() => {
    const header = "日期,来源,交易对方,商品或说明,分类,支付方式,金额,币种,重复\n";
    const quote = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const rows = filtered.map((transaction) => [
      transaction.date, financeSourceLabel(transaction.source, lang), quote(transaction.merchant),
      quote(transaction.description), financeCategoryLabel(transaction.category, lang),
      quote(transaction.payment_method), transaction.amount, transaction.currency, transaction.is_duplicate,
    ].join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + header + rows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `transactions${monthFilter !== "all" ? `_${monthFilter}` : ""}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [filtered, lang, monthFilter]);

  return (
    <div className="transactions-card transactions-card-detailed">
      <div className="transactions-header">
        <div className="transactions-title-copy">
          <h3>{lang === "zh" ? "全部交易" : "All transactions"}</h3>
          <span>{lang === "zh" ? "商户和商品直接展示，点击可查看账单原始信息" : "Merchant and item are shown directly; open a row for source details"}</span>
        </div>
        <div className="transactions-controls">
          <label className="transactions-search"><Search /><input value={query} onChange={(event) => { setQuery(event.target.value); setCurrentPage(1); }} placeholder={lang === "zh" ? "搜索商户或商品" : "Search merchant or item"} /></label>
          <select value={monthFilter} onChange={(event) => { setMonthFilter(event.target.value); setCurrentPage(1); }}>
            <option value="all">{lang === "zh" ? "全部月份" : "All months"}</option>
            {months.map((month) => <option key={month} value={month}>{month}</option>)}
          </select>
          <button type="button" className={sortKey === "date" ? "active" : ""} onClick={() => toggleSort("date")}>{lang === "zh" ? "按日期" : "Date"}<ArrowUpDown /></button>
          <button type="button" className={sortKey === "amount" ? "active" : ""} onClick={() => toggleSort("amount")}>{lang === "zh" ? "按金额" : "Amount"}<ArrowUpDown /></button>
          {duplicateCount > 0 && <button type="button" className={showDuplicates ? "duplicate-active" : ""} onClick={() => { setShowDuplicates((value) => !value); setCurrentPage(1); }}>{showDuplicates ? <Eye /> : <EyeOff />}{duplicateCount} {lang === "zh" ? "笔重复" : "duplicates"}</button>}
          <button type="button" onClick={exportCSV}><Download />{lang === "zh" ? "导出" : "Export"}</button>
        </div>
      </div>

      <div className="transactions-table-scroll">
        <table className="transactions-table-detailed">
          <colgroup><col className="transaction-date-col" /><col className="transaction-direction-col" /><col /><col className="transaction-category-col" /><col className="transaction-payment-col" /><col className="transaction-amount-col" /></colgroup>
          <thead><tr><th>{lang === "zh" ? "日期与来源" : "Date & source"}</th><th>{lang === "zh" ? "类型" : "Type"}</th><th>{lang === "zh" ? "交易内容" : "Transaction"}</th><th>{lang === "zh" ? "分类" : "Category"}</th><th>{lang === "zh" ? "支付方式" : "Payment"}</th><th>{lang === "zh" ? "金额" : "Amount"}</th></tr></thead>
          <tbody>
            {currentTransactions.map((transaction) => (
              <tr key={transaction.id} className={transaction.is_duplicate ? "is-duplicate" : ""} onClick={() => setSelected(transaction)}>
                <td><div className="transaction-date-cell"><strong>{transaction.date}</strong><span>{financeSourceLabel(transaction.source, lang)}</span></div></td>
                <td><span className={`transaction-direction ${transactionTone(transaction)}`}>{transactionTypeLabel(transaction, lang)}</span></td>
                <td><button type="button" className="transaction-description-button" onClick={(event) => { event.stopPropagation(); setSelected(transaction); }}><strong>{meaningfulMerchant(transaction, lang)}</strong>{secondaryDescription(transaction) && <span>{secondaryDescription(transaction)}</span>}</button>{transaction.is_duplicate && <span className="transaction-duplicate-label">{lang === "zh" ? "重复" : "Duplicate"}</span>}</td>
                <td><span className="transaction-category-pill">{financeCategoryLabel(transaction.category, lang)}</span></td>
                <td className="transaction-payment">{transaction.payment_method || "—"}</td>
                <td className={`transaction-amount ${transactionTone(transaction)}`}>{transactionPrefix(transaction)}{currencySymbol(transaction.currency)}{transactionDisplayAmount(transaction).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="transactions-pagination">
          <span>{filtered.length > 0 ? `${startIndex + 1}–${Math.min(endIndex, filtered.length)} / ${filtered.length}` : (lang === "zh" ? "暂无交易" : "No transactions")}</span>
          <div><button type="button" onClick={() => setCurrentPage((page) => Math.max(page - 1, 1))} disabled={safePage === 1}><ChevronLeft />{lang === "zh" ? "上一页" : "Prev"}</button><span>{safePage} / {totalPages}</span><button type="button" onClick={() => setCurrentPage((page) => Math.min(page + 1, totalPages))} disabled={safePage === totalPages}>{lang === "zh" ? "下一页" : "Next"}<ChevronRight /></button></div>
        </div>
      </div>
      {selected && <TransactionDetail transaction={selected} lang={lang} onClose={() => setSelected(null)} />}
    </div>
  );
}

function meaningfulMerchant(transaction: Transaction, lang: "zh" | "en") {
  const merchant = transaction.merchant.trim();
  const description = transaction.description.trim();
  if (merchant && !GENERIC_LABELS.has(merchant.toLocaleLowerCase())) return merchant;
  if (description && !GENERIC_LABELS.has(description.toLocaleLowerCase())) return description;
  return lang === "zh" ? "未识别商户" : "Unknown merchant";
}

function secondaryDescription(transaction: Transaction) {
  const merchant = transaction.merchant.trim();
  const description = transaction.description.trim();
  if (!description || description === merchant || GENERIC_LABELS.has(description.toLocaleLowerCase())) return "";
  return description;
}

function rawDetailRows(raw: unknown): Array<[string, string]> {
  if (!raw) return [];
  let value = raw;
  if (typeof raw === "string") {
    try { value = JSON.parse(raw); } catch { return [["原始内容", raw]]; }
  }
  if (!value || typeof value !== "object") return [];
  const root = value as Record<string, unknown>;
  const row = root.row && typeof root.row === "object" ? root.row as Record<string, unknown> : root;
  return Object.entries(row).filter(([, field]) => field !== null && field !== undefined && String(field).trim() !== "").slice(0, 18).map(([key, field]) => [key, String(field)]);
}

function transactionStatusLabel(status: string, lang: "zh" | "en") {
  if (lang === "en") return status || "—";
  return ({ imported: "已导入", success: "成功", completed: "已完成", pending: "处理中", awaiting_statement: "等待账单核对", failed: "失败" } as Record<string, string>)[status.toLocaleLowerCase()] || status || "—";
}

function transactionTone(transaction: Transaction) {
  if (transaction.type === "manual_transfer") return "transfer";
  return transaction.amount > 0 ? "income" : "expense";
}

function transactionTypeLabel(transaction: Transaction, lang: "zh" | "en") {
  if (transaction.type === "manual_transfer") return lang === "zh" ? "转账" : "Transfer";
  if (transaction.type === "manual_refund") return lang === "zh" ? "退款" : "Refund";
  return transaction.amount > 0 ? (lang === "zh" ? "收入" : "Income") : (lang === "zh" ? "支出" : "Expense");
}

function transactionPrefix(transaction: Transaction) {
  if (transaction.type === "manual_transfer") return "↔";
  return transaction.amount > 0 ? "+" : "−";
}

function transactionDisplayAmount(transaction: Transaction) {
  return transaction.type === "manual_transfer" ? transaction.gross_amount : Math.abs(transaction.amount);
}

function TransactionDetail({ transaction, lang, onClose }: { transaction: Transaction; lang: "zh" | "en"; onClose: () => void }) {
  const rawRows = rawDetailRows(transaction.raw);
  const matchedRawRows = rawDetailRows(transaction.matched_raw);
  const sourceNames = [financeSourceLabel(transaction.source, lang), ...transaction.matched_sources.map((source) => financeSourceLabel(source, lang))];
  const detailRows = [
    [lang === "zh" ? "交易日期" : "Date", transaction.date],
    [lang === "zh" ? "来源" : "Source", sourceNames.join(lang === "zh" ? " · 关联 " : " · matched with ")],
    [lang === "zh" ? "交易对方" : "Counterparty", transaction.merchant],
    [lang === "zh" ? "商品或说明" : "Item or description", transaction.description || "—"],
    [lang === "zh" ? "分类" : "Category", financeCategoryLabel(transaction.category, lang)],
    [lang === "zh" ? "支付方式" : "Payment method", transaction.payment_method || "—"],
    [lang === "zh" ? "交易状态" : "Status", transactionStatusLabel(transaction.status, lang)],
    [lang === "zh" ? "备注" : "Note", transaction.note || "—"],
  ];
  return (
    <><button type="button" className="transaction-detail-backdrop" aria-label={lang === "zh" ? "关闭交易详情" : "Close transaction details"} onClick={onClose} /><aside className="transaction-detail-panel" role="dialog" aria-modal="true" aria-label={lang === "zh" ? "交易详情" : "Transaction details"}>
      <header><div><ReceiptText /><span>{lang === "zh" ? "交易详情" : "Transaction details"}</span></div><button type="button" onClick={onClose} aria-label={lang === "zh" ? "关闭交易详情" : "Close transaction details"}><X /></button></header>
      <div className="transaction-detail-summary"><span>{transactionTypeLabel(transaction, lang)}</span><strong className={transactionTone(transaction)}>{transactionPrefix(transaction)}{currencySymbol(transaction.currency)}{transactionDisplayAmount(transaction).toFixed(2)}</strong><h2>{meaningfulMerchant(transaction, lang)}</h2>{secondaryDescription(transaction) && <p>{secondaryDescription(transaction)}</p>}</div>
      <dl className="transaction-detail-list">{detailRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {(transaction.external_id || transaction.merchant_order_id || transaction.source_file) && <section className="transaction-reference"><h3>{lang === "zh" ? "账单凭据" : "Statement reference"}</h3>{transaction.external_id && <p><span>{lang === "zh" ? "交易单号" : "Transaction ID"}</span><code>{transaction.external_id}</code></p>}{transaction.merchant_order_id && <p><span>{lang === "zh" ? "商户单号" : "Merchant order"}</span><code>{transaction.merchant_order_id}</code></p>}{transaction.source_file && <p><span>{lang === "zh" ? "来源文件" : "Source file"}</span><b>{transaction.source_file}</b></p>}</section>}
      {(transaction.matched_external_id || transaction.matched_merchant_order_id || transaction.matched_source_file) && <section className="transaction-reference matched"><h3>{lang === "zh" ? "关联账单凭据" : "Matched statement reference"}</h3>{transaction.matched_external_id && <p><span>{lang === "zh" ? "交易单号" : "Transaction ID"}</span><code>{transaction.matched_external_id}</code></p>}{transaction.matched_merchant_order_id && <p><span>{lang === "zh" ? "商户单号" : "Merchant order"}</span><code>{transaction.matched_merchant_order_id}</code></p>}{transaction.matched_source_file && <p><span>{lang === "zh" ? "来源文件" : "Source file"}</span><b>{transaction.matched_source_file}</b></p>}</section>}
      {rawRows.length > 0 && <details className="transaction-raw"><summary>{lang === "zh" ? "查看账单原始字段" : "View original statement fields"}</summary><dl>{rawRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details>}
      {matchedRawRows.length > 0 && <details className="transaction-raw"><summary>{lang === "zh" ? "查看关联账单原始字段" : "View matched statement fields"}</summary><dl>{matchedRawRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details>}
    </aside></>
  );
}
