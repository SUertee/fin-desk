import React from 'react';
import { Wallet, CreditCard, Building2 } from 'lucide-react';
import { currencySymbol } from './MetricsCards';

const SOURCE_CONFIG: Record<string, { label: string; icon: typeof Wallet; color: string; bg: string }> = {
  alipay: { label: '支付宝', icon: Wallet, color: 'text-blue-600', bg: 'bg-blue-50' },
  wechat: { label: '微信', icon: CreditCard, color: 'text-green-600', bg: 'bg-green-50' },
  icbc: { label: '工商银行', icon: Building2, color: 'text-red-600', bg: 'bg-red-50' },
};

interface SourceItem {
  source: string;
  count: number;
  income: number;
  expense: number;
  currency: string;
}

interface SourceBreakdownProps {
  items: SourceItem[];
}

export function SourceBreakdown({ items }: SourceBreakdownProps) {
  // Group by source, then show currency breakdown within each
  const bySource: Record<string, SourceItem[]> = {};
  for (const item of items) {
    if (!bySource[item.source]) bySource[item.source] = [];
    bySource[item.source].push(item);
  }

  const sources = Object.keys(bySource);
  if (sources.length === 0) {
    return (
      <div className="dashboard-card source-breakdown-card">
        <h3 className="dashboard-card-title">Source Breakdown</h3>
        <div className="dashboard-empty">Connect a statement source to see inflows.</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card source-breakdown-card">
      <h3 className="dashboard-card-title">Source Breakdown</h3>
      <div className="source-breakdown-list">
        {sources.map((source) => {
          const config = SOURCE_CONFIG[source] || { label: source, icon: Wallet, color: 'text-gray-600', bg: 'bg-gray-50' };
          const Icon = config.icon;
          const currencyItems = bySource[source];
          const totalCount = currencyItems.reduce((s, i) => s + i.count, 0);

          return (
            <div key={source} className="source-breakdown-item">
              <div className="source-breakdown-head">
                <div className={`w-10 h-10 ${config.bg} rounded-lg flex items-center justify-center`}>
                  <Icon className={`w-5 h-5 ${config.color}`} />
                </div>
                <div>
                  <div className="source-breakdown-name">{config.label}</div>
                  <div className="source-breakdown-count">{totalCount} transactions</div>
                </div>
              </div>
              {currencyItems.map((ci) => (
                <div key={ci.currency} className="source-breakdown-row">
                  <span>+{currencySymbol(ci.currency)}{ci.income.toFixed(2)}</span>
                  <span>-{currencySymbol(ci.currency)}{ci.expense.toFixed(2)}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
