import React from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign } from 'lucide-react';
import { useDataStore } from '../stores/useDataStore';

const DashboardStats: React.FC = () => {
  const { runs } = useDataStore();

  // Calculate stats from runs
  const totalRuns = runs.length;
  const profitableRuns = runs.filter(r => r.net_profit_pct > 0).length;
  const winRate = totalRuns > 0 ? (profitableRuns / totalRuns) * 100 : 0;
  
  // Create a simplified aggregate view (this would ideally come from a dedicated API endpoint)
  const averageProfit = totalRuns > 0 
    ? runs.reduce((acc, r) => acc + r.net_profit_pct, 0) / totalRuns 
    : 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
      <div className="bg-[var(--bg-surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-[var(--text-secondary)]">Win Rate</h3>
          <Activity className="w-4 h-4 text-[var(--text-muted)]" />
        </div>
        <div className="flex items-baseline">
          <span className="text-2xl font-bold text-[var(--text-primary)]">
            {winRate.toFixed(1)}%
          </span>
          <span className="ml-2 text-sm text-[var(--text-muted)]">
            across {totalRuns} runs
          </span>
        </div>
      </div>

      <div className="bg-[var(--bg-surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-[var(--text-secondary)]">Avg. Net Profit</h3>
          <DollarSign className="w-4 h-4 text-[var(--text-muted)]" />
        </div>
        <div className="flex items-baseline">
          <span className={`text-2xl font-bold ${averageProfit >= 0 ? 'text-[var(--success)]' : 'text-[var(--error)]'}`}>
            {averageProfit > 0 ? '+' : ''}{averageProfit.toFixed(2)}%
          </span>
          <div className="ml-2">
            {averageProfit >= 0 ? (
                <TrendingUp className="w-4 h-4 text-[var(--success)]" />
            ) : (
                <TrendingDown className="w-4 h-4 text-[var(--error)]" />
            )}
          </div>
        </div>
      </div>

      <div className="bg-[var(--bg-surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-[var(--text-secondary)]">Total Runs</h3>
          <Activity className="w-4 h-4 text-[var(--text-muted)]" />
        </div>
        <div className="text-2xl font-bold text-[var(--text-primary)]">
          {totalRuns}
        </div>
      </div>
    </div>
  );
};

export default DashboardStats;
