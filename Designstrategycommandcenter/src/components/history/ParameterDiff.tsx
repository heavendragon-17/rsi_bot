import React from "react";
import { type HistoryRun } from "../../stores/historyStore";
import { cn } from "../../lib/utils";
import { AlertCircle } from "lucide-react";

interface ParameterDiffProps {
  run1: HistoryRun;
  run2: HistoryRun;
}

interface ParamComparison {
  key: string;
  label: string;
  value1: any;
  value2: any;
  changed: boolean;
}

export const ParameterDiff: React.FC<ParameterDiffProps> = ({ run1, run2 }) => {
  // Build comparison data
  const allKeys = new Set([
    ...Object.keys(run1.parameters),
    ...Object.keys(run2.parameters),
  ]);

  const comparisons: ParamComparison[] = [];

  // Parameter label mapping
  const labelMap: Record<string, string> = {
    rsi_period: "RSI Period",
    ema_fast: "EMA Fast",
    ema_slow: "EMA Slow",
    tp1_rr: "Take Profit 1 R:R",
    tp2_rr: "Take Profit 2 R:R",
    sl_buffer_pct: "Stop Loss Buffer %",
    capital: "Initial Capital",
    leverage: "Leverage",
    riskPercent: "Risk Per Trade %",
    timeframe: "Timeframe",
    startDate: "Start Date",
    endDate: "End Date",
  };

  allKeys.forEach((key) => {
    const value1 = run1.parameters[key];
    const value2 = run2.parameters[key];

    // Format values for display
    const formatValue = (val: any) => {
      if (val === null || val === undefined) return "—";
      if (typeof val === "number") return val.toString();
      if (val instanceof Date || typeof val === "string") {
        try {
          const date = new Date(val);
          if (!isNaN(date.getTime())) {
            return date.toLocaleDateString("en-US");
          }
        } catch {
          // Not a date
        }
      }
      return String(val);
    };

    const changed = JSON.stringify(value1) !== JSON.stringify(value2);

    comparisons.push({
      key,
      label: labelMap[key] || key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
      value1: formatValue(value1),
      value2: formatValue(value2),
      changed,
    });
  });

  // Sort: changed first, then alphabetically
  comparisons.sort((a, b) => {
    if (a.changed && !b.changed) return -1;
    if (!a.changed && b.changed) return 1;
    return a.label.localeCompare(b.label);
  });

  const changedCount = comparisons.filter((c) => c.changed).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">⚡</span>
        <h3 className="text-base font-semibold text-text-primary">Parameter Diff</h3>
        {changedCount > 0 && (
          <span className="px-2 py-0.5 bg-warning/20 text-warning text-xs font-medium rounded">
            {changedCount} changed
          </span>
        )}
      </div>

      <div className="border border-border-main rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-bg-elevated border-b border-border-main">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Parameter
              </th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Run #{run1.runNumber}
              </th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Run #{run2.runNumber}
              </th>
              <th className="px-4 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-main/30">
            {comparisons.map((comp) => (
              <tr
                key={comp.key}
                className={cn(
                  comp.changed ? "bg-warning/5" : "bg-transparent",
                  "hover:bg-bg-elevated/50 transition-colors"
                )}
              >
                <td className="px-4 py-2.5">
                  <span className="text-sm font-medium text-text-primary">{comp.label}</span>
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={cn(
                      "text-sm font-mono",
                      comp.changed ? "text-text-primary" : "text-text-muted"
                    )}
                  >
                    {comp.value1}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-sm font-mono",
                        comp.changed ? "text-text-primary font-semibold" : "text-text-muted"
                      )}
                    >
                      {comp.value2}
                    </span>
                    {comp.changed && (
                      <span className="text-xs text-warning font-medium">← CHANGED</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  {comp.changed ? (
                    <div className="flex items-center gap-1.5">
                      <AlertCircle size={14} className="text-warning" />
                      <span className="text-xs text-warning font-medium">Modified</span>
                    </div>
                  ) : (
                    <span className="text-xs text-text-muted">Unchanged</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {changedCount === 0 && (
        <div className="p-4 bg-bg-elevated border border-border-main rounded-lg text-center">
          <p className="text-sm text-text-muted">
            No parameter changes detected between these runs
          </p>
        </div>
      )}
    </div>
  );
};
