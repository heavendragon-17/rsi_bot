import React from "react";
import { Play, StopCircle } from "lucide-react";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { Card } from "../ui/card";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";

export const SensitivityConfig: React.FC = () => {
  const {
    variationPercent,
    customVariation,
    metric,
    isRunning,
    setVariationPercent,
    setCustomVariation,
    setMetric,
    runSensitivityAnalysis,
    cancelRun,
  } = useSensitivityStore();

  const { params, strategy } = useBacktestStore();

  const handleVariationClick = (percent: number) => {
    setVariationPercent(percent);
  };

  const handleCustomChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setCustomVariation(value);
    const num = parseFloat(value);
    if (!isNaN(num) && num > 0 && num <= 100) {
      setVariationPercent(num);
    }
  };

  const handleRun = () => {
    if (isRunning) {
      cancelRun();
    } else {
      runSensitivityAnalysis();
    }
  };

  // Count parameters
  const paramCount = Object.keys(params).filter((key) => !key.startsWith("_")).length;

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold text-text-primary mb-4">Configuration</h2>

      <div className="space-y-6">
        {/* Base Settings */}
        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">
            Base Settings
          </label>
          <div className="px-4 py-3 bg-bg-elevated rounded-lg">
            <div className="text-sm text-text-secondary">
              Strategy: <span className="text-text-primary font-medium">{strategy}</span>
            </div>
            <div className="text-xs text-text-muted mt-1">
              Testing {paramCount} parameters with current values as baseline
            </div>
          </div>
        </div>

        {/* Variation Amount */}
        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">
            Variation Amount
          </label>
          <div className="flex items-center gap-2">
            {[10, 20, 30].map((percent) => (
              <button
                key={percent}
                onClick={() => handleVariationClick(percent)}
                disabled={isRunning}
                className={cn(
                  "px-4 py-2 rounded-md text-sm font-medium transition-colors",
                  variationPercent === percent
                    ? "bg-accent-main text-white"
                    : "bg-bg-elevated text-text-secondary hover:text-text-primary hover:bg-bg-elevated/80",
                  isRunning && "opacity-50 cursor-not-allowed"
                )}
              >
                ±{percent}%
              </button>
            ))}
            <div className="flex items-center gap-2 px-3 py-2 bg-bg-elevated rounded-md">
              <span className="text-sm text-text-secondary">Custom:</span>
              <input
                type="number"
                value={customVariation}
                onChange={handleCustomChange}
                placeholder="e.g., 15"
                disabled={isRunning}
                className="w-16 bg-transparent border-none outline-none text-sm text-text-primary disabled:opacity-50"
                min="1"
                max="100"
              />
              <span className="text-sm text-text-secondary">%</span>
            </div>
          </div>
          <p className="text-xs text-text-muted mt-2">
            Each parameter will be tested at Base − {variationPercent}%, Base, and Base +{" "}
            {variationPercent}%
          </p>
        </div>

        {/* Metric Selection */}
        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">
            Metric to Measure
          </label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as any)}
            disabled={isRunning}
            className="w-full px-4 py-2 bg-bg-elevated border border-border-main rounded-md text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-main disabled:opacity-50"
          >
            <option value="net_pnl">Net PnL ($)</option>
            <option value="sharpe">Sharpe Ratio</option>
            <option value="profit_factor">Profit Factor</option>
            <option value="win_rate">Win Rate (%)</option>
          </select>
        </div>

        {/* Summary Info */}
        <div className="px-4 py-3 bg-bg-elevated/50 rounded-lg border border-border-main">
          <div className="text-sm text-text-secondary">
            Total Tests: <span className="text-text-primary font-medium">{paramCount * 3}</span>{" "}
            <span className="text-text-muted">({paramCount} params × 3 values)</span>
          </div>
          <div className="text-xs text-text-muted mt-1">
            Estimated time: ~{Math.ceil(paramCount * 0.6)} seconds
          </div>
        </div>

        {/* Run Button */}
        <Button
          onClick={handleRun}
          disabled={paramCount === 0}
          className={cn(
            "w-full gap-2",
            isRunning && "bg-danger hover:bg-danger/90"
          )}
        >
          {isRunning ? (
            <>
              <StopCircle className="w-4 h-4" />
              Cancel Analysis
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Sensitivity Analysis
            </>
          )}
        </Button>
      </div>
    </Card>
  );
};
