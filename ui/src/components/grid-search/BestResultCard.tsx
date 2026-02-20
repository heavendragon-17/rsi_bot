import React from "react";
import { Star, Check, FileText } from "lucide-react";
import { useGridSearchStore, AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { toast } from "sonner";

export const BestResultCard: React.FC = () => {
  const { bestResult, xAxisParam, yAxisParam, metric, applyBestSettings } = useGridSearchStore();

  if (!bestResult) return null;

  const getParamLabel = (paramValue: string) => {
    const param = AVAILABLE_PARAMETERS.find((p) => p.value === paramValue);
    return param?.label || paramValue;
  };

  const getMetricLabel = () => {
    switch (metric) {
      case "net_pnl":
        return "Net PnL";
      case "sharpe":
        return "Sharpe Ratio";
      case "profit_factor":
        return "Profit Factor";
      case "win_rate":
        return "Win Rate";
      case "max_dd":
        return "Max Drawdown";
      case "calmar":
        return "Calmar Ratio";
      case "sortino":
        return "Sortino Ratio";
      default:
        return metric;
    }
  };

  const handleApplySettings = () => {
    applyBestSettings();
    toast.success("Settings Applied", {
      description: `Parameters updated: ${getParamLabel(xAxisParam)} = ${bestResult.xValue.toFixed(2)}, ${getParamLabel(yAxisParam)} = ${bestResult.yValue.toFixed(2)}`,
    });
  };

  const result = bestResult.fullResults;

  return (
    <Card className="p-6 bg-gradient-to-br from-yellow-500/10 to-yellow-600/5 border-yellow-500/30">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-yellow-400">
            <Star className="w-5 h-5 text-gray-900 fill-gray-900" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-text-primary">Optimal Parameters Found</h3>
            <p className="text-sm text-text-secondary">
              Best result based on {getMetricLabel()}
            </p>
          </div>
        </div>

        <div className="h-px bg-border-main" />

        {/* Parameter Values */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <p className="text-xs text-text-secondary uppercase tracking-wide">
              {getParamLabel(xAxisParam)}
            </p>
            <p className="text-3xl font-bold text-text-primary font-mono">
              {bestResult.xValue.toFixed(bestResult.xValue % 1 === 0 ? 0 : 2)}
            </p>
          </div>
          <div className="space-y-2">
            <p className="text-xs text-text-secondary uppercase tracking-wide">
              {getParamLabel(yAxisParam)}
            </p>
            <p className="text-3xl font-bold text-text-primary font-mono">
              {bestResult.yValue.toFixed(bestResult.yValue % 1 === 0 ? 0 : 2)}
            </p>
          </div>
        </div>

        {/* Results Grid */}
        <div className="rounded-lg bg-bg-secondary border border-border-main p-4">
          <p className="text-sm font-semibold text-text-primary mb-3">Performance Metrics</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-text-secondary mb-1">Net PnL</p>
              <p className={`text-lg font-bold ${result.netPnL >= 0 ? "text-success" : "text-danger"}`}>
                ${result.netPnL >= 0 ? "+" : ""}{result.netPnL.toFixed(2)}
              </p>
              <p className="text-xs text-text-secondary">
                ({result.netPnLPct >= 0 ? "+" : ""}{result.netPnLPct.toFixed(2)}%)
              </p>
            </div>

            <div>
              <p className="text-xs text-text-secondary mb-1">Sharpe Ratio</p>
              <p className="text-lg font-bold text-text-primary">{result.sharpe.toFixed(2)}</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary mb-1">Win Rate</p>
              <p className="text-lg font-bold text-text-primary">{result.winRate.toFixed(1)}%</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary mb-1">Profit Factor</p>
              <p className="text-lg font-bold text-text-primary">{result.profitFactor.toFixed(2)}</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary mb-1">Max Drawdown</p>
              <p className="text-lg font-bold text-danger">{result.maxDrawdownPct.toFixed(2)}%</p>
            </div>

            <div>
              <p className="text-xs text-text-secondary mb-1">Total Trades</p>
              <p className="text-lg font-bold text-text-primary">{result.tradeCount}</p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3">
          <Button
            onClick={handleApplySettings}
            className="flex-1 gap-2 bg-accent-main hover:bg-accent-hover text-white"
          >
            <Check className="w-4 h-4" />
            Apply These Settings
          </Button>
          
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => {
              // In a real app, this would navigate to a detailed report
              toast.info("Feature Coming Soon", {
                description: "Detailed report view will be available in the next update.",
              });
            }}
          >
            <FileText className="w-4 h-4" />
            View Full Report
          </Button>
        </div>
      </div>
    </Card>
  );
};
