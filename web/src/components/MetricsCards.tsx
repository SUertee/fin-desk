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
    <div className="grid grid-cols-3 gap-4 mb-6">
      {/* Total Income Card */}
      <div className="bg-white p-5 rounded-lg border border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-600">Total Income</span>
          <div className="w-8 h-8 bg-green-50 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-green-600" />
          </div>
        </div>
        <div className="text-green-600">
          {items.map((s) => (
            <div key={s.currency} className="text-2xl">
              {formatAmount(s.income, s.currency)}
            </div>
          ))}
        </div>
      </div>

      {/* Total Expenses Card */}
      <div className="bg-white p-5 rounded-lg border border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-600">Total Expenses</span>
          <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center">
            <TrendingDown className="w-4 h-4 text-red-600" />
          </div>
        </div>
        <div className="text-red-600">
          {items.map((s) => (
            <div key={s.currency} className="text-2xl">
              {formatAmount(s.expense, s.currency)}
            </div>
          ))}
        </div>
      </div>

      {/* Net Balance Card */}
      <div className="bg-white p-5 rounded-lg border border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-600">Net for Period</span>
          <div className="w-8 h-8 bg-slate-50 rounded-lg flex items-center justify-center">
            <DollarSign className="w-4 h-4 text-slate-600" />
          </div>
        </div>
        <div>
          {items.map((s) => (
            <div key={s.currency} className={`text-2xl ${s.net >= 0 ? 'text-slate-900' : 'text-red-600'}`}>
              {formatAmount(s.net, s.currency)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
