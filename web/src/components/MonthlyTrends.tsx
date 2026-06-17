import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { currencySymbol } from './MetricsCards';

interface MonthlyData {
  month: string;
  income: number;
  expenses: number;
}

interface MonthlyTrendsProps {
  data: MonthlyData[];
  currency?: string;
}

export function MonthlyTrends({ data, currency = 'CNY' }: MonthlyTrendsProps) {
  const sym = currencySymbol(currency);
  return (
    <div className="bg-white p-5 rounded-lg border border-gray-200">
      <h3 className="text-sm text-gray-900 mb-4">Monthly Breakdown</h3>
      
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis 
            dataKey="month" 
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
          />
          <YAxis 
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
            tickFormatter={(value) => `${sym}${value}`}
          />
          <Tooltip
            formatter={(value: number) => `${sym}${value.toFixed(2)}`}
            contentStyle={{ 
              backgroundColor: 'white', 
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontSize: '12px'
            }}
          />
          <Legend 
            wrapperStyle={{ paddingTop: '16px', fontSize: '12px' }}
            iconType="circle"
          />
          <Bar 
            dataKey="income" 
            fill="#10b981" 
            name="Income"
            radius={[4, 4, 0, 0]}
          />
          <Bar 
            dataKey="expenses" 
            fill="#ef4444" 
            name="Expenses"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}