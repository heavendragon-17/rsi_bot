import React, { useEffect } from 'react';
import { useDataStore } from '../../stores/useDataStore';
import { Eye, ArrowRight } from 'lucide-react';
import { cn } from '../../lib/utils';

export const RunHistoryTable: React.FC = () => {
  const { runHistory, fetchRunHistory, loadRun } = useDataStore();

  useEffect(() => {
    fetchRunHistory();
  }, [fetchRunHistory]);

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h3 className="font-semibold text-text">Recent Runs</h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-hover text-text-muted font-medium">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Strategy</th>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Profit</th>
              <th className="px-4 py-3">Win Rate</th>
              <th className="px-4 py-3">Trades</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {runHistory.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-text-muted">
                  No backtests found. Run one to see results here.
                </td>
              </tr>
            ) : (
              runHistory.map((run) => (
                <tr
                  key={run.run_id}
                  className="hover:bg-surface-hover transition-colors group cursor-pointer"
                  onClick={() => loadRun(run.run_id)}
                >
                  <td className="px-4 py-3 text-text-muted">#{run.run_id}</td>
                  <td className="px-4 py-3 font-medium text-primary">{run.strategy_name}</td>
                  <td className="px-4 py-3 text-text">
                    {run.symbol} <span className="text-xs text-text-muted ml-1">{run.timeframe}</span>
                  </td>
                  <td className={cn(
                    "px-4 py-3 font-medium",
                    run.net_profit_pct >= 0 ? "text-success" : "text-danger"
                  )}>
                    {run.net_profit_pct > 0 ? '+' : ''}{run.net_profit_pct.toFixed(2)}%
                  </td>
                  <td className="px-4 py-3 text-text">{(run.win_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-text">{run.total_trades}</td>
                  <td className="px-4 py-3 text-text-muted text-xs">
                    {new Date(run.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="text-text-muted hover:text-primary p-1">
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {runHistory.length > 0 && (
        <div className="p-3 border-t border-border flex justify-end">
          <button className="text-xs text-primary hover:text-primary-hover flex items-center gap-1 font-medium">
            View All History <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};
