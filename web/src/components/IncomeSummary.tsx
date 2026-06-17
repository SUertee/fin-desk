import React from 'react';
import { Banknote, PiggyBank, TrendingDown } from 'lucide-react';
import { currencySymbol } from './MetricsCards';

interface IncomeSummaryProps {
  monthlyIncome: number;
  currentMonthExpense: number;
  currency?: string;
}

export function IncomeSummary({ monthlyIncome, currentMonthExpense, currency = 'CNY' }: IncomeSummaryProps) {
  if (monthlyIncome <= 0) return null;

  const sym = currencySymbol(currency);
  const disposable = monthlyIncome - currentMonthExpense;
  const savingsRate = ((disposable / monthlyIncome) * 100);
  const spendRate = ((currentMonthExpense / monthlyIncome) * 100);

  return (
    <div className="bg-white p-5 rounded-lg border border-gray-200 mb-6">
      <h3 className="text-sm text-gray-900 mb-4">Income vs Spending (This Month)</h3>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Spent {spendRate.toFixed(0)}%</span>
          <span>Salary {sym}{monthlyIncome.toFixed(0)}</span>
        </div>
        <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${spendRate > 100 ? 'bg-red-500' : spendRate > 80 ? 'bg-amber-500' : 'bg-green-500'}`}
            style={{ width: `${Math.min(spendRate, 100)}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
            <Banknote className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <div className="text-xs text-gray-500">Salary</div>
            <div className="text-sm font-medium">{sym}{monthlyIncome.toFixed(0)}</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center">
            <TrendingDown className="w-4 h-4 text-red-600" />
          </div>
          <div>
            <div className="text-xs text-gray-500">Spent</div>
            <div className="text-sm font-medium">{sym}{currentMonthExpense.toFixed(0)}</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className={`w-8 h-8 ${disposable >= 0 ? 'bg-green-50' : 'bg-red-50'} rounded-lg flex items-center justify-center`}>
            <PiggyBank className={`w-4 h-4 ${disposable >= 0 ? 'text-green-600' : 'text-red-600'}`} />
          </div>
          <div>
            <div className="text-xs text-gray-500">Savings Rate</div>
            <div className={`text-sm font-medium ${disposable >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {savingsRate.toFixed(1)}%
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
