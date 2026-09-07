import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  fetchDailyTotals,
  fetchTransactionsForDay,
  type DailyTotal,
} from "../services/financeApi";
import { currencySymbol } from "./MetricsCards";

interface SpendingCalendarProps {
  userId: string;
  currency?: string;
  defaultMonth?: string; // YYYY-MM; falls back to the current month
  onAskCfo?: (question: string) => void;
}

interface DayTransaction {
  id: string | number;
  date: string;
  description: string;
  counterparty: string;
  category: string;
  amount: number;
  source: string;
  is_duplicate: boolean;
}

const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const shifted = new Date(year, monthNumber - 1 + delta, 1);
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, "0")}`;
}

function compactAmount(value: number): string {
  if (value >= 10000) return `${(value / 1000).toFixed(1)}k`;
  if (value >= 1000) return `${Math.round(value / 100) / 10}k`;
  return `${Math.round(value)}`;
}

export function SpendingCalendar({
  userId,
  currency = "CNY",
  defaultMonth,
  onAskCfo,
}: SpendingCalendarProps) {
  const [month, setMonth] = useState(
    defaultMonth ?? new Date().toISOString().slice(0, 7)
  );
  const [days, setDays] = useState<DailyTotal[]>([]);
  const [totals, setTotals] = useState({ expense: 0, income: 0, count: 0 });
  const [loading, setLoading] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [dayTransactions, setDayTransactions] = useState<DayTransaction[]>([]);

  const sym = currencySymbol(currency);

  useEffect(() => {
    if (defaultMonth) setMonth(defaultMonth);
  }, [defaultMonth]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSelectedDay(null);
    setDayTransactions([]);
    fetchDailyTotals(userId, month)
      .then((result) => {
        if (cancelled) return;
        setDays(result.days);
        setTotals(result.totals);
      })
      .catch(() => {
        if (cancelled) return;
        setDays([]);
        setTotals({ expense: 0, income: 0, count: 0 });
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [userId, month]);

  const handleDayClick = (day: string, hasActivity: boolean) => {
    if (!hasActivity) return;
    if (selectedDay === day) {
      setSelectedDay(null);
      setDayTransactions([]);
      return;
    }
    setSelectedDay(day);
    fetchTransactionsForDay(userId, day)
      .then((result) => setDayTransactions(result.items as DayTransaction[]))
      .catch(() => setDayTransactions([]));
  };

  const { weeks, maxExpense } = useMemo(() => {
    const byDate = new Map(days.map((d) => [d.date, d]));
    const [year, monthNumber] = month.split("-").map(Number);
    const daysInMonth = new Date(year, monthNumber, 0).getDate();
    // Monday-first column index for the 1st of the month
    const firstWeekday = (new Date(year, monthNumber - 1, 1).getDay() + 6) % 7;

    const cells: ({ day: number; iso: string; data?: DailyTotal } | null)[] = [];
    for (let i = 0; i < firstWeekday; i += 1) cells.push(null);
    for (let day = 1; day <= daysInMonth; day += 1) {
      const iso = `${month}-${String(day).padStart(2, "0")}`;
      cells.push({ day, iso, data: byDate.get(iso) });
    }
    while (cells.length % 7 !== 0) cells.push(null);

    const weekRows = [];
    for (let i = 0; i < cells.length; i += 7) {
      const row = cells.slice(i, i + 7);
      const weekExpense = row.reduce((sum, c) => sum + (c?.data?.expense ?? 0), 0);
      weekRows.push({ cells: row, weekExpense });
    }
    return {
      weeks: weekRows,
      maxExpense: Math.max(...days.map((d) => d.expense), 1),
    };
  }, [days, month]);

  return (
    <div className="dashboard-card">
      <div className="calendar-heading"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <h3 className="dashboard-card-title" style={{ marginBottom: 0 }}>
          Spending Calendar
        </h3>
        <div className="calendar-controls" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, color: "#6b7280" }}>
            支出 <strong style={{ color: "#dc2626" }}>{sym}{totals.expense.toFixed(2)}</strong>
            {"  ·  "}
            收入 <strong style={{ color: "#16a34a" }}>{sym}{totals.income.toFixed(2)}</strong>
          </span>
          <button type="button" onClick={() => setMonth((m) => shiftMonth(m, -1))} aria-label="Previous month">
            <ChevronLeft style={{ width: 16, height: 16 }} />
          </button>
          <span style={{ fontWeight: 600, minWidth: 70, textAlign: "center" }}>{month}</span>
          <button type="button" onClick={() => setMonth((m) => shiftMonth(m, 1))} aria-label="Next month">
            <ChevronRight style={{ width: 16, height: 16 }} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="empty-copy">Loading…</div>
      ) : days.length === 0 ? (
        <div className="empty-copy">No transactions in {month}.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 3 }}>
            <thead>
              <tr>
                {WEEKDAY_LABELS.map((label) => (
                  <th key={label} style={{ fontSize: 11, color: "#9ca3af", fontWeight: 500, padding: 2 }}>
                    {label}
                  </th>
                ))}
                <th style={{ fontSize: 11, color: "#9ca3af", fontWeight: 500, padding: 2 }}>周合计</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((week, weekIndex) => (
                <tr key={weekIndex}>
                  {week.cells.map((cell, cellIndex) => {
                    if (!cell) {
                      return <td key={cellIndex} />;
                    }
                    const expense = cell.data?.expense ?? 0;
                    const income = cell.data?.income ?? 0;
                    const hasActivity = Boolean(cell.data && cell.data.count > 0);
                    const intensity = expense > 0 ? 0.08 + 0.42 * (expense / maxExpense) : 0;
                    const isSelected = selectedDay === cell.iso;
                    return (
                      <td
                        key={cellIndex}
                        onClick={() => handleDayClick(cell.iso, hasActivity)}
                        style={{
                          background: isSelected
                            ? "#fde68a"
                            : expense > 0
                              ? `rgba(239, 68, 68, ${intensity.toFixed(2)})`
                              : "#f9fafb",
                          borderRadius: 8,
                          padding: "6px 4px",
                          textAlign: "center",
                          cursor: hasActivity ? "pointer" : "default",
                          minWidth: 52,
                          border: isSelected ? "1px solid #f59e0b" : "1px solid transparent",
                        }}
                        title={
                          hasActivity
                            ? `${cell.iso}: 支出 ${sym}${expense.toFixed(2)}, 收入 ${sym}${income.toFixed(2)} (${cell.data?.count} 笔)`
                            : cell.iso
                        }
                      >
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{cell.day}</div>
                        {expense > 0 && (
                          <div style={{ fontSize: 12, fontWeight: 600, color: intensity > 0.3 ? "#7f1d1d" : "#b91c1c" }}>
                            {compactAmount(expense)}
                          </div>
                        )}
                        {income > 0 && (
                          <div style={{ fontSize: 10, color: "#16a34a" }}>+{compactAmount(income)}</div>
                        )}
                      </td>
                    );
                  })}
                  <td
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: "#374151",
                      textAlign: "right",
                      padding: "0 6px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {week.weekExpense > 0 ? `${sym}${week.weekExpense.toFixed(0)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedDay && (
        <div style={{ marginTop: 12, borderTop: "1px solid #e5e7eb", paddingTop: 10 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {selectedDay} · {dayTransactions.length} 笔
            </span>
            {onAskCfo && (
              <button
                type="button"
                onClick={() => onAskCfo(`帮我逐笔看看 ${selectedDay} 这天的消费，有什么值得注意的？`)}
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#2f6b5f",
                  background: "#e7f3ef",
                  border: "none",
                  borderRadius: 8,
                  padding: "4px 10px",
                  cursor: "pointer",
                }}
              >
                问 CFO 这一天 →
              </button>
            )}
          </div>
          {dayTransactions.map((transaction) => (
            <div
              key={transaction.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                fontSize: 13,
                padding: "4px 0",
                opacity: transaction.is_duplicate ? 0.45 : 1,
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {transaction.description || transaction.counterparty}
                <span style={{ color: "#9ca3af", marginLeft: 6, fontSize: 11 }}>
                  {transaction.category} · {transaction.source}
                  {transaction.is_duplicate ? " · 重复" : ""}
                </span>
              </span>
              <span
                style={{
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  color: transaction.amount < 0 ? "#dc2626" : "#16a34a",
                }}
              >
                {transaction.amount < 0 ? "" : "+"}
                {sym}
                {Math.abs(transaction.amount).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
