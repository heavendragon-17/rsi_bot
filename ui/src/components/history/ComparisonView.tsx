import React, { useState } from 'react';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { ComparisonResult } from '../../types/pywebview';
import { cn } from '../../lib/utils';

interface ComparisonViewProps {
  runId1: number;
}

export const ComparisonView: React.FC<ComparisonViewProps> = ({ runId1 }) => {
  const { runHistory } = useDataStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [runId2, setRunId2] = useState<number | ''>('');
  const [result, setResult] = useState<ComparisonResult | null>(null);

  const handleCompare = async () => {
    if (!runId2) {
      addToast({ type: 'error', message: 'Select a run to compare' });
      return;
    }

    setLoading(true);
    try {
      const res = await window.pywebview.api.compare_runs(runId1, Number(runId2));
      setResult(res);
    } catch (e) {
      addToast({ type: 'error', message: 'Comparison failed' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-6 mt-6">
      <div className="flex items-center gap-4 mb-6">
        <h3 className="text-lg font-semibold text-text">Compare Runs</h3>

        <select
          value={runId2}
          onChange={(e) => setRunId2(Number(e.target.value))}
          className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
        >
          <option value="" disabled>Select Run to Compare</option>
          {runHistory.filter(r => r.run_id !== runId1).map(r => (
            <option key={r.run_id} value={r.run_id}>
              #{r.run_id} - {r.strategy_name} ({r.net_profit_pct.toFixed(2)}%)
            </option>
          ))}
        </select>

        <button
          onClick={handleCompare}
          disabled={isLoading || !runId2}
          className="bg-primary hover:bg-primary-hover disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          Compare
        </button>
      </div>

      {result && (
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-4">
            <h4 className="font-semibold text-primary">Run #{result.run_1.id}</h4>
            <MetricRow label="Profit" value={`$${result.run_1.net_profit}`} />
            <MetricRow label="Win Rate" value={`${(result.run_1.win_rate * 100).toFixed(1)}%`} />
            <MetricRow label="Trades" value={result.run_1.total_trades} />
            <MetricRow label="Drawdown" value={`${result.run_1.max_drawdown_pct}%`} />
          </div>

          <div className="space-y-4">
            <h4 className="font-semibold text-text-muted text-center">Difference</h4>
            <DiffRow value={result.differences.net_profit} format="$" />
            <DiffRow value={result.differences.win_rate * 100} format="%" />
            <DiffRow value={result.differences.total_trades} />
            <DiffRow value={result.differences.max_drawdown_pct} format="%" inverse />
          </div>

          <div className="space-y-4 text-right">
            <h4 className="font-semibold text-info">Run #{result.run_2.id}</h4>
            <MetricRow label="Profit" value={`$${result.run_2.net_profit}`} align="right" />
            <MetricRow label="Win Rate" value={`${(result.run_2.win_rate * 100).toFixed(1)}%`} align="right" />
            <MetricRow label="Trades" value={result.run_2.total_trades} align="right" />
            <MetricRow label="Drawdown" value={`${result.run_2.max_drawdown_pct}%`} align="right" />
          </div>
        </div>
      )}

      {result && (
        <div className="mt-6 p-4 bg-surface-hover rounded-lg text-center font-medium text-text">
          Verdict: {result.verdict}
        </div>
      )}
    </div>
  );
};

const MetricRow = ({ label, value, align = "left" }: any) => (
  <div className={`flex flex-col ${align === "right" ? "items-end" : "items-start"}`}>
    <span className="text-xs text-text-muted uppercase">{label}</span>
    <span className="text-lg font-medium text-text">{value}</span>
  </div>
);

const DiffRow = ({ value, format = "", inverse = false }: any) => {
  const isPositive = value > 0;
  const isGood = inverse ? !isPositive : isPositive;
  const color = value === 0 ? "text-text-muted" : isGood ? "text-success" : "text-danger";

  return (
    <div className={`flex justify-center items-center h-[52px]`}>
      <span className={cn("font-bold", color)}>
        {value > 0 ? '+' : ''}{value?.toFixed(2) || '0.00'}{format}
      </span>
    </div>
  );
};
