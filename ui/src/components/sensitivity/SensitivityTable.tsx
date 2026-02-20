import React from "react";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { Card } from "../ui/card";
import { cn } from "../../lib/utils";

export const SensitivityTable: React.FC = () => {
  const { results, variationPercent, metric } = useSensitivityStore();

  if (results.length === 0) return null;

  const metricLabel = {
    net_pnl: "PnL ($)",
    sharpe: "Sharpe",
    profit_factor: "PF",
    win_rate: "Win Rate (%)",
  }[metric];

  const formatValue = (val: number) => {
    if (metric === "net_pnl") {
      return `$${val.toFixed(0)}`;
    } else if (metric === "win_rate") {
      return `${val.toFixed(1)}%`;
    } else {
      return val.toFixed(2);
    }
  };

  const formatParamValue = (val: number) => {
    if (Number.isInteger(val)) return val.toString();
    return val.toFixed(2);
  };

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold text-text-primary mb-4">Detailed Sensitivity</h2>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-main">
              <th className="text-left py-3 px-4 font-medium text-text-secondary">Parameter</th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                Low Value
                <div className="text-xs font-normal text-text-muted">(-{variationPercent}%)</div>
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                Low {metricLabel}
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                Base Value
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                Base {metricLabel}
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                High Value
                <div className="text-xs font-normal text-text-muted">(+{variationPercent}%)</div>
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                High {metricLabel}
              </th>
              <th className="text-right py-3 px-4 font-medium text-text-secondary">
                Total Impact
              </th>
              <th className="text-center py-3 px-4 font-medium text-text-secondary">
                Sensitivity
              </th>
            </tr>
          </thead>
          <tbody>
            {results.map((result, idx) => (
              <tr
                key={result.paramName}
                className={cn(
                  "border-b border-border-main/50 hover:bg-bg-elevated/50 transition-colors",
                  idx === 0 && "bg-accent-main/5"
                )}
              >
                <td className="py-3 px-4">
                  <div className="font-medium text-text-primary">{result.paramDisplayName}</div>
                  {idx === 0 && (
                    <div className="text-xs text-accent-main">Highest Impact</div>
                  )}
                </td>
                <td className="text-right py-3 px-4 text-text-secondary">
                  {formatParamValue(result.lowValue)}
                </td>
                <td className="text-right py-3 px-4">
                  <div className="text-text-primary">{formatValue(result.lowMetric)}</div>
                  <div
                    className={cn(
                      "text-xs",
                      result.lowImpactPct < 0 ? "text-danger" : "text-success"
                    )}
                  >
                    {result.lowImpactPct > 0 ? "+" : ""}
                    {result.lowImpactPct.toFixed(1)}%
                  </div>
                </td>
                <td className="text-right py-3 px-4 font-medium text-text-secondary">
                  {formatParamValue(result.baseValue)}
                </td>
                <td className="text-right py-3 px-4 font-medium text-text-primary">
                  {formatValue(result.baseMetric)}
                </td>
                <td className="text-right py-3 px-4 text-text-secondary">
                  {formatParamValue(result.highValue)}
                </td>
                <td className="text-right py-3 px-4">
                  <div className="text-text-primary">{formatValue(result.highMetric)}</div>
                  <div
                    className={cn(
                      "text-xs",
                      result.highImpactPct > 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {result.highImpactPct > 0 ? "+" : ""}
                    {result.highImpactPct.toFixed(1)}%
                  </div>
                </td>
                <td className="text-right py-3 px-4">
                  <span className="font-semibold text-text-primary">
                    {result.totalImpact.toFixed(1)}%
                  </span>
                </td>
                <td className="text-center py-3 px-4">
                  <span
                    className={cn(
                      "inline-block px-2 py-1 rounded-full text-xs font-medium",
                      result.sensitivity === "high" && "bg-danger/20 text-danger",
                      result.sensitivity === "medium" && "bg-warning/20 text-warning",
                      result.sensitivity === "low" && "bg-success/20 text-success"
                    )}
                  >
                    {result.sensitivity === "high" && "🔴 HIGH"}
                    {result.sensitivity === "medium" && "🟡 MEDIUM"}
                    {result.sensitivity === "low" && "🟢 LOW"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="mt-6 pt-4 border-t border-border-main">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Sensitivity Categories</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="flex items-start gap-2">
            <span className="text-lg">🔴</span>
            <div>
              <div className="font-medium text-text-primary">HIGH (&gt;20% impact)</div>
              <div className="text-xs text-text-secondary">
                Critical parameter, optimize carefully
              </div>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-lg">🟡</span>
            <div>
              <div className="font-medium text-text-primary">MEDIUM (10-20% impact)</div>
              <div className="text-xs text-text-secondary">Important, worth tuning</div>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-lg">🟢</span>
            <div>
              <div className="font-medium text-text-primary">LOW (&lt;10% impact)</div>
              <div className="text-xs text-text-secondary">Stable, less optimization needed</div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};
