import React from "react";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { TornadoBar } from "./TornadoBar";
import { Card } from "../ui/card";

export const TornadoChart: React.FC = () => {
  const { results, metric } = useSensitivityStore();

  if (results.length === 0) return null;

  // Get max absolute impact for scaling
  const maxImpact = Math.max(
    ...results.map((r) => Math.max(Math.abs(r.lowImpactPct), Math.abs(r.highImpactPct)))
  );

  // Format metric name
  const metricLabel = {
    net_pnl: "Net PnL",
    sharpe: "Sharpe Ratio",
    profit_factor: "Profit Factor",
    win_rate: "Win Rate",
  }[metric];

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">Tornado Chart</h2>
          <p className="text-sm text-text-secondary mt-1">
            Impact on {metricLabel} • Sorted by Total Impact
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-4 h-3 bg-danger rounded" />
            <span className="text-text-secondary">Negative Impact</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-3 bg-success rounded" />
            <span className="text-text-secondary">Positive Impact</span>
          </div>
        </div>
      </div>

      {/* Chart Container */}
      <div className="space-y-3">
        {results.map((result) => (
          <TornadoBar key={result.paramName} result={result} maxImpact={maxImpact} />
        ))}
      </div>

      {/* X-Axis Labels */}
      <div className="mt-4 relative h-8 border-t border-border-main">
        <div className="absolute inset-0 flex items-center justify-between text-xs text-text-muted px-4">
          <span>-{Math.round(maxImpact)}%</span>
          <span>-{Math.round(maxImpact / 2)}%</span>
          <span className="font-medium text-text-primary">0%</span>
          <span>+{Math.round(maxImpact / 2)}%</span>
          <span>+{Math.round(maxImpact)}%</span>
        </div>
        {/* Center line marker */}
        <div className="absolute left-1/2 top-0 w-px h-full bg-border-main" />
      </div>

      {/* Key Insight */}
      {results.length > 0 && results[0].sensitivity === "high" && (
        <div className="mt-4 px-4 py-3 bg-danger/10 border border-danger/30 rounded-lg">
          <p className="text-sm text-text-primary">
            <span className="font-semibold">📊 Key Insight:</span>{" "}
            <span className="font-medium">{results[0].paramDisplayName}</span> has the highest
            sensitivity ({Math.round(results[0].totalImpact)}% total impact). Small changes to
            this parameter cause large performance swings. Handle with care during optimization.
          </p>
        </div>
      )}
    </Card>
  );
};
