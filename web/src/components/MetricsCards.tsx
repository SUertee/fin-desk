import React from 'react';
import { TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

const CURRENCY_SYMBOL: Record<string, string> = {
  CNY: '¥',
  AUD: 'A$',
  USD: '$',
  HKD: 'HK$',
  JPY: '¥',
  EUR: '€',
  GBP: '£',
};

export function currencySymbol(code: string): string {
  return CURRENCY_SYMBOL[code] || code + ' ';
}

function formatAmount(amount: number, currency: string): string {
  return `${currencySymbol(currency)}${amount.toFixed(2)}`;
}

interface CurrencySummary {
  currency: string;
  income: number;
  expense: number;
  net: number;
}

interface MetricsCardsProps {
  items: CurrencySummary[];
}

export function MetricsCards({ items }: MetricsCardsProps) {
  return (
    <div className="metrics-cards-grid">
      {/* Total Income Card */}
      <div className="metric-card">
        <div className="metric-card-header">
          <span>Total Income</span>
          <div className="metric-card-icon metric-card-icon-good">
            <TrendingUp />
          </div>
        </div>
        <div className="metric-card-value metric-card-value-good">
          {items.map((s) => (
            <div key={s.currency} className="text-2xl">
              {formatAmount(s.income, s.currency)}
            </div>
          ))}
        </div>
      </div>

      {/* Total Expenses Card */}
      <div className="metric-card">
        <div className="metric-card-header">
          <span>Total Expenses</span>
          <div className="metric-card-icon metric-card-icon-risk">
            <TrendingDown />
          </div>
        </div>
        <div className="metric-card-value metric-card-value-risk">
          {items.map((s) => (
            <div key={s.currency} className="text-2xl">
              {formatAmount(s.expense, s.currency)}
            </div>
          ))}
        </div>
      </div>

      {/* Net Balance Card */}
      <div className="metric-card">
        <div className="metric-card-header">
          <span>Net for Period</span>
          <div className="metric-card-icon">
            <DollarSign />
          </div>
        </div>
        <div className="metric-card-value">
          {items.map((s) => (
            <div key={s.currency} className={s.net >= 0 ? '' : 'metric-card-value-risk'}>
              {formatAmount(s.net, s.currency)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
