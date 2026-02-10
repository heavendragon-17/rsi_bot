import React, { useState } from 'react';
import { DashboardStats } from './DashboardStats';
import { BacktestRunner } from './BacktestRunner';
import { RunHistoryTable } from '../history/RunHistoryTable';
import { ChartsContainer } from '../charts';
import { ExitPieChart } from '../charts';
import { TradesTable } from '../tables';
import { useDataStore } from '../../stores/useDataStore';
import { ChevronDown, ChevronUp } from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { runHistory, activeRun, activeRunTimeseries, activeRunTrades } = useDataStore();
  const [showTrades, setShowTrades] = useState(false);

  // Compute aggregate stats from history or use active run
  const defaultStats = { totalProfit: 0, winRate: 0, totalTrades: 0, profitFactor: 0, runs: 0 };

  const historyStats = runHistory.reduce((acc, run) => ({
    totalProfit: acc.totalProfit + (run.net_profit_pct * 1000),
    winRate: acc.winRate + run.win_rate,
    totalTrades: acc.totalTrades + run.total_trades,
    profitFactor: acc.profitFactor + 1.5, // Placeholder
    runs: acc.runs + 1
  }), defaultStats);

  const displayStats = activeRun ? {
    totalProfit: activeRun.results.net_profit,
    winRate: activeRun.results.win_rate,
    totalTrades: activeRun.results.total_trades,
    profitFactor: activeRun.results.profit_factor
  } : {
    totalProfit: historyStats.totalProfit,
    winRate: historyStats.runs ? historyStats.winRate / historyStats.runs : 0,
    totalTrades: historyStats.totalTrades,
    profitFactor: historyStats.runs ? historyStats.profitFactor / historyStats.runs : 0
  };

  // Compute pie data
  const exitCounts = activeRunTrades.reduce((acc, trade) => {
    acc[trade.exit_reason] = (acc[trade.exit_reason] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const pieData = Object.entries(exitCounts).map(([name, value]) => ({ name, value }));

  const handleExport = async () => {
    if (activeRun) {
      try {
        const res = await window.pywebview.api.export_results(activeRun.run.id, 'json');
        if (res.success) {
          // Ideally show a toast here, but for now just console
          console.log(`Exported to ${res.file_path}`);
        }
      } catch (e) {
        console.error(e);
      }
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        {activeRun && (
          <button
            onClick={handleExport}
            className="text-sm text-primary hover:text-primary-hover font-medium"
          >
            Export Results (JSON)
          </button>
        )}
      </div>
      <DashboardStats stats={displayStats} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <BacktestRunner />
          {activeRun && activeRunTimeseries && (
            <ChartsContainer data={activeRunTimeseries} />
          )}
        </div>

        <div className="space-y-6">
          {activeRun && (
            <div className="bg-surface border border-border rounded-xl p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-text-muted mb-2">Exit Distribution</h3>
              <ExitPieChart data={pieData.length > 0 ? pieData : [{name: 'No Trades', value: 1}]} />
            </div>
          )}

          <div className="bg-surface border border-border rounded-xl p-4 shadow-sm">
             <h3 className="text-sm font-semibold text-text-muted mb-2">Recent Activity</h3>
             <div className="text-xs text-text-muted">
               {runHistory.slice(0, 5).map(run => (
                 <div key={run.run_id} className="flex justify-between py-2 border-b border-border last:border-0">
                   <span>#{run.run_id} {run.strategy_name}</span>
                   <span className={run.net_profit_pct >= 0 ? "text-success" : "text-danger"}>
                     {run.net_profit_pct.toFixed(2)}%
                   </span>
                 </div>
               ))}
             </div>
          </div>
        </div>
      </div>

      {activeRun && (
        <div className="space-y-2">
          <button
            onClick={() => setShowTrades(!showTrades)}
            className="flex items-center gap-2 text-sm font-medium text-primary hover:text-primary-hover transition-colors"
          >
            {showTrades ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            {showTrades ? 'Hide Trades' : 'View Trades'}
          </button>

          {showTrades && <TradesTable trades={activeRunTrades} />}
        </div>
      )}

      <div className="mt-8 pt-8 border-t border-border">
        <RunHistoryTable />
      </div>
    </div>
  );
};
