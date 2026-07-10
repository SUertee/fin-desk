import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { currencySymbol } from './MetricsCards';

const COLORS = [
  '#3b82f6', '#ef4444', '#f59e0b', '#10b981', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#84cc16',
];

interface CategoryItem {
  category: string;
  amount: number;
  currency: string;
}

interface CategoryPieChartProps {
  data: CategoryItem[];
}

export function CategoryPieChart({ data }: CategoryPieChartProps) {
  if (data.length === 0) {
    return (
      <div className="dashboard-card">
        <h3 className="dashboard-card-title">Spending by Category</h3>
        <div className="dashboard-empty">Import transactions to see category mix.</div>
      </div>
    );
  }

  // Group by currency
  const byCurrency: Record<string, CategoryItem[]> = {};
  for (const d of data) {
    if (!byCurrency[d.currency]) byCurrency[d.currency] = [];
    byCurrency[d.currency].push(d);
  }

  return (
    <div className="dashboard-card">
      <h3 className="dashboard-card-title">Spending by Category</h3>
      {Object.entries(byCurrency).map(([currency, items]) => {
        // Top 8 + "other"
        const sorted = [...items].sort((a, b) => b.amount - a.amount);
        const top = sorted.slice(0, 8);
        const rest = sorted.slice(8);
        const chartData = [...top];
        if (rest.length > 0) {
          chartData.push({
            category: '其他',
            amount: rest.reduce((s, i) => s + i.amount, 0),
            currency,
          });
        }
        const total = chartData.reduce((s, i) => s + i.amount, 0);
        const sym = currencySymbol(currency);

        return (
          <div key={currency} className="category-chart-layout">
            <div style={{ width: 220, height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="amount"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={85}
                    paddingAngle={2}
                  >
                    {chartData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => `${sym}${value.toFixed(2)}`}
                    contentStyle={{ backgroundColor: 'white', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '12px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="category-legend">
              {Object.keys(byCurrency).length > 1 && (
                <div className="text-xs text-gray-500 mb-2">{currency}</div>
              )}
              <div className="space-y-2">
                {chartData.map((item, index) => {
                  const pct = total > 0 ? ((item.amount / total) * 100).toFixed(1) : '0';
                  return (
                    <div key={item.category} className="flex items-center gap-2 text-xs">
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                      <span className="text-gray-700 flex-1 truncate">{item.category}</span>
                      <span className="text-gray-500 flex-shrink-0">{pct}%</span>
                      <span className="text-gray-900 flex-shrink-0 w-24 text-right">{sym}{item.amount.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
