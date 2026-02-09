import { Trophy, TrendingDown, Activity } from 'lucide-react';

interface RunComparisonData {
  id: number;
  strategy: string;
  config: any;
  metrics: {
    net_profit_pct: number;
    win_rate: number;
    max_drawdown_pct: number;
    sharpe_ratio: number;
    total_trades: number;
  };
}

interface ComparisonViewProps {
  runs: RunComparisonData[];
  onClose: () => void;
}

export function ComparisonView({ runs, onClose }: ComparisonViewProps) {
  if (!runs || runs.length === 0) return null;

  // Find best performer for highlighting
  const bestProfit = Math.max(...runs.map(r => r.metrics.net_profit_pct));
  
  return (
    <div className="flex flex-col h-full bg-[var(--color-bg)]">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <h2 className="text-xl font-bold flex items-center gap-2 text-[var(--color-text)]">
          <Activity className="text-[var(--color-primary)]" />
          Run Comparison
        </h2>
        <button 
          onClick={onClose}
          className="px-4 py-2 text-sm bg-[var(--color-surface-hover)] rounded hover:bg-[var(--color-border)] transition-colors text-[var(--color-text)]"
        >
          Close Comparison
        </button>
      </div>

      {/* Comparison Grid */}
      <div className="flex-1 overflow-auto p-6">
        <div className={`grid gap-6 grid-cols-1 md:grid-cols-${Math.min(runs.length, 3)}`}>
          {runs.map((run) => {
            const isWinner = run.metrics.net_profit_pct === bestProfit && runs.length > 1;
            
            return (
              <div 
                key={run.id} 
                className={`
                  relative flex flex-col rounded-xl border bg-[var(--color-surface)] p-6 shadow-sm transition-all
                  ${isWinner ? 'border-[var(--color-primary)] ring-2 ring-[var(--color-primary)]/20 shadow-xl scale-[1.02]' : 'border-[var(--color-border)]'}
                `}
              >
                {isWinner && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[var(--color-primary)] text-white px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1 shadow-md">
                    <Trophy size={12} /> BEST PERFORMER
                  </div>
                )}

                {/* Header Info */}
                <div className="mb-6 text-center">
                  <span className="text-xs font-mono text-[var(--color-text-muted)] bg-[var(--color-bg)] px-2 py-1 rounded">
                    RUN #{run.id}
                  </span>
                  <h3 className="text-lg font-bold mt-2 text-[var(--color-text)]">{run.strategy}</h3>
                  <div className="text-sm text-[var(--color-text-muted)] mt-1">
                    {run.config.symbol} • {run.config.timeframe}
                  </div>
                </div>

                {/* Key Metrics */}
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="p-3 bg-[var(--color-bg)] rounded-lg text-center">
                    <div className="text-xs text-[var(--color-text-muted)] mb-1">Net Profit</div>
                    <div className={`text-xl font-bold ${run.metrics.net_profit_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {run.metrics.net_profit_pct > 0 ? '+' : ''}{run.metrics.net_profit_pct.toFixed(2)}%
                    </div>
                  </div>
                  <div className="p-3 bg-[var(--color-bg)] rounded-lg text-center">
                    <div className="text-xs text-[var(--color-text-muted)] mb-1">Win Rate</div>
                    <div className="text-xl font-bold text-[var(--color-text)]">
                      {run.metrics.win_rate.toFixed(1)}%
                    </div>
                  </div>
                </div>

                {/* Detailed Stats */}
                <div className="space-y-3 flex-1">
                  <div className="flex justify-between items-center py-2 border-b border-[var(--color-border)]">
                    <span className="text-sm text-[var(--color-text-muted)] flex items-center gap-2">
                       <TrendingDown size={14} /> Max Drawdown
                    </span>
                    <span className="font-mono font-medium text-red-400">
                      {run.metrics.max_drawdown_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b border-[var(--color-border)]">
                    <span className="text-sm text-[var(--color-text-muted)] flex items-center gap-2">
                       <Activity size={14} /> Sharpe Ratio
                    </span>
                    <span className="font-mono font-medium text-[var(--color-text)]">
                      {run.metrics.sharpe_ratio.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b border-[var(--color-border)]">
                    <span className="text-sm text-[var(--color-text-muted)] flex items-center gap-2">
                       # Total Trades
                    </span>
                    <span className="font-mono font-medium text-[var(--color-text)]">
                      {run.metrics.total_trades}
                    </span>
                  </div>
                </div>

                {/* Config Diff (Simplified) */}
                <div className="mt-6 pt-4 border-t border-dashed border-[var(--color-border)]">
                  <h4 className="text-xs font-semibold uppercase text-[var(--color-text-muted)] mb-2">Key Parameters</h4>
                  <div className="space-y-1">
                    {Object.entries(run.config.strategy_params || {}).slice(0, 4).map(([key, val]) => (
                      <div key={key} className="flex justify-between text-xs">
                        <span className="text-[var(--color-text-muted)] truncate max-w-[120px]">{key}</span>
                        <span className="font-mono text-[var(--color-text)]">{String(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
