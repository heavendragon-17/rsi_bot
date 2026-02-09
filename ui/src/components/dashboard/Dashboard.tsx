import React from 'react';
import { DashboardStats } from './DashboardStats';
import { BacktestRunner } from './BacktestRunner';
import { RunHistoryTable } from '../history/RunHistoryTable';
import { useDataStore } from '../../stores/useDataStore';

export const Dashboard: React.FC = () => {
  const { runHistory } = useDataStore();

  // Compute aggregate stats from history
  const stats = runHistory.reduce((acc, run) => ({
    totalProfit: acc.totalProfit + (run.net_profit_pct * 1000), // Approximate
    winRate: acc.winRate + run.win_rate,
    totalTrades: acc.totalTrades + run.total_trades,
    runs: acc.runs + 1
  }), { totalProfit: 0, winRate: 0, totalTrades: 0, runs: 0 });

  const avgStats = {
    ...stats,
    winRate: stats.runs ? stats.winRate / stats.runs : 0,
    profitFactor: 1.5 // Placeholder
  };

  return (
    <div className="space-y-6">
      <DashboardStats stats={avgStats} />

      <BacktestRunner />

      <div className="mt-8">
        <RunHistoryTable />
      </div>
    </div>
  );
};
