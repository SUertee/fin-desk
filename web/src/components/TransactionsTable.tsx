import React, { useCallback, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ArrowUpDown, Eye, EyeOff, Download } from 'lucide-react';
import { currencySymbol } from './MetricsCards';

const SOURCE_LABEL: Record<string, string> = {
  alipay: '支付宝',
  wechat: '微信',
  icbc: '工商银行',
};

interface Transaction {
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
}

interface TransactionsTableProps {
  transactions: Transaction[];
}

type SortKey = 'date' | 'amount';
type SortDir = 'asc' | 'desc';

const ITEMS_PER_PAGE = 15;

export function TransactionsTable({ transactions }: TransactionsTableProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [monthFilter, setMonthFilter] = useState<string>('all');
  const [sortKey, setSortKey] = useState<SortKey>('date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [showDuplicates, setShowDuplicates] = useState(false);

  // Available months for filter
  const months = useMemo(() => {
    const set = new Set(transactions.map((t) => t.month));
    return Array.from(set).sort().reverse();
  }, [transactions]);

  // Filter + sort
  const filtered = useMemo(() => {
    let result = transactions;
    if (!showDuplicates) {
      result = result.filter((t) => !t.is_duplicate);
    }
    if (monthFilter !== 'all') {
      result = result.filter((t) => t.month === monthFilter);
    }
    result = [...result].sort((a, b) => {
      if (sortKey === 'amount') {
        const diff = Math.abs(a.amount) - Math.abs(b.amount);
        return sortDir === 'desc' ? -diff : diff;
      }
      // date
      const diff = a.date.localeCompare(b.date);
      return sortDir === 'desc' ? -diff : diff;
    });
    return result;
  }, [transactions, monthFilter, sortKey, sortDir, showDuplicates]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentTransactions = filtered.slice(startIndex, endIndex);

  const dupCount = transactions.filter((t) => t.is_duplicate).length;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
    setCurrentPage(1);
  };

  const exportCSV = useCallback(() => {
    const header = 'Date,Source,Description,Category,Payment Method,Amount,Currency,Duplicate\n';
    const rows = filtered.map((t) =>
      [t.date, SOURCE_LABEL[t.source] || t.source, `"${t.merchant.replace(/"/g, '""')}"`, t.category, `"${t.payment_method.replace(/"/g, '""')}"`, t.amount, t.currency, t.is_duplicate].join(',')
    ).join('\n');
    const blob = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transactions${monthFilter !== 'all' ? '_' + monthFilter : ''}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filtered, monthFilter]);

  return (
    <div className="transactions-card">
      {/* Header with filters */}
      <div className="transactions-header">
        <h3>Recent Transactions</h3>
        <div className="transactions-controls">
          {/* Month filter */}
          <select
            value={monthFilter}
            onChange={(e) => { setMonthFilter(e.target.value); setCurrentPage(1); }}
            className="px-2 py-1 text-xs border border-gray-300 rounded-md bg-white text-gray-700"
          >
            <option value="all">All Months</option>
            {months.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>

          {/* Sort buttons */}
          <button
            onClick={() => toggleSort('date')}
            className={`px-2 py-1 text-xs border rounded-md flex items-center gap-1 ${
              sortKey === 'date' ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-600'
            }`}
          >
            Date <ArrowUpDown className="w-3 h-3" />
          </button>
          <button
            onClick={() => toggleSort('amount')}
            className={`px-2 py-1 text-xs border rounded-md flex items-center gap-1 ${
              sortKey === 'amount' ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-600'
            }`}
          >
            Amount <ArrowUpDown className="w-3 h-3" />
          </button>

          {/* Duplicate toggle */}
          {dupCount > 0 && (
            <button
              onClick={() => { setShowDuplicates((v) => !v); setCurrentPage(1); }}
              className={`px-2 py-1 text-xs border rounded-md flex items-center gap-1 ${
                showDuplicates ? 'border-amber-400 text-amber-600 bg-amber-50' : 'border-gray-300 text-gray-500'
              }`}
            >
              {showDuplicates ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
              {dupCount} duplicates
            </button>
          )}

          {/* CSV Export */}
          <button
            onClick={exportCSV}
            className="px-2 py-1 text-xs border border-gray-300 rounded-md text-gray-600 flex items-center gap-1 hover:bg-gray-50"
          >
            <Download className="w-3 h-3" /> Export
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full table-fixed">
          <colgroup>
            <col className="w-[100px]" />
            <col className="w-[80px]" />
            <col />
            <col className="w-[110px]" />
            <col className="w-[160px]" />
            <col className="w-[110px]" />
          </colgroup>
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs text-gray-600">Date</th>
              <th className="px-4 py-3 text-left text-xs text-gray-600">Source</th>
              <th className="px-4 py-3 text-left text-xs text-gray-600">Description</th>
              <th className="px-4 py-3 text-left text-xs text-gray-600">Category</th>
              <th className="px-4 py-3 text-left text-xs text-gray-600">Payment</th>
              <th className="px-4 py-3 text-right text-xs text-gray-600">Amount</th>
            </tr>
          </thead>
          <tbody>
            {currentTransactions.map((t) => (
              <tr
                key={t.id}
                className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${
                  t.is_duplicate ? 'opacity-50' : ''
                }`}
              >
                <td className="px-4 py-3 text-xs text-gray-700 whitespace-nowrap">{t.date}</td>
                <td className="px-4 py-3">
                  <span className="inline-block px-2 py-0.5 text-xs rounded-md bg-gray-100 text-gray-700">
                    {SOURCE_LABEL[t.source] || t.source}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-900 max-w-[200px] truncate">
                  {t.merchant}
                  {t.is_duplicate && <span className="ml-1 text-amber-500">(dup)</span>}
                </td>
                <td className="px-4 py-3">
                  <span className="inline-block px-2 py-0.5 text-xs rounded-md bg-slate-100 text-slate-700">
                    {t.category}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 max-w-[140px] truncate">
                  {t.payment_method || '—'}
                </td>
                <td className={`px-4 py-3 text-right text-xs whitespace-nowrap ${
                  t.amount > 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {t.amount > 0 ? '+' : ''}{currencySymbol(t.currency)}{Math.abs(t.amount).toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="px-5 py-3 bg-gray-50 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {filtered.length > 0 ? `${startIndex + 1}–${Math.min(endIndex, filtered.length)} of ${filtered.length}` : 'No transactions'}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
              disabled={safePage === 1}
              className="px-3 py-1.5 rounded-md border border-gray-300 bg-white text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              <ChevronLeft className="w-3 h-3" /> Prev
            </button>
            <div className="px-3 text-xs text-gray-700">{safePage} / {totalPages}</div>
            <button
              onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
              disabled={safePage === totalPages}
              className="px-3 py-1.5 rounded-md border border-gray-300 bg-white text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              Next <ChevronRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
