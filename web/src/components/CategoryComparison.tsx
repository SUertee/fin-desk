import React from 'react';
import { currencySymbol } from './MetricsCards';

interface CategoryComparisonItem {
  category: string;
  currentMonth: number;
  average: number;
  currency: string;
}

interface CategoryComparisonProps {
  data: CategoryComparisonItem[];
}

export function CategoryComparison({ data }: CategoryComparisonProps) {
  if (data.length === 0) return null;

  const sorted = [...data].sort((a, b) => b.currentMonth - a.currentMonth);

  return (
    <div className="bg-white p-5 rounded-lg border border-gray-200">
      <h3 className="text-sm text-gray-900 mb-4">This Month vs Average</h3>
      <div className="space-y-3">
        {sorted.map((item) => {
          const diff = item.average > 0
            ? ((item.currentMonth - item.average) / item.average) * 100
            : 0;
          const sym = currencySymbol(item.currency);
          const pct = Math.min(item.currentMonth / (Math.max(item.average, item.currentMonth) * 1.2) * 100, 100);
          const avgPct = item.average > 0 ? Math.min(item.average / (Math.max(item.average, item.currentMonth) * 1.2) * 100, 100) : 0;

          return (
            <div key={item.category + item.currency}>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-gray-700">{item.category}</span>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-900">{sym}{item.currentMonth.toFixed(0)}</span>
                  {item.average > 0 && (
                    <span className={`${diff > 15 ? 'text-red-500' : diff < -15 ? 'text-green-500' : 'text-gray-400'}`}>
                      {diff > 0 ? '+' : ''}{diff.toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
              <div className="relative w-full h-2 bg-gray-100 rounded-full">
                {/* Average line */}
                {avgPct > 0 && (
                  <div
                    className="absolute top-0 h-2 w-0.5 bg-gray-400 z-10"
                    style={{ left: `${avgPct}%` }}
                    title={`Avg: ${sym}${item.average.toFixed(0)}`}
                  />
                )}
                {/* Current bar */}
                <div
                  className={`h-full rounded-full ${diff > 15 ? 'bg-red-400' : diff < -15 ? 'bg-green-400' : 'bg-blue-400'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-3 text-[10px] text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-400 inline-block" /> Avg</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block" /> Over +15%</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-400 inline-block" /> Under -15%</span>
      </div>
    </div>
  );
}
