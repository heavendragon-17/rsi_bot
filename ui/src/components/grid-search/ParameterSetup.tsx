import React from "react";
import { Play, AlertCircle } from "lucide-react";
import { useGridSearchStore, AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Input } from "../ui/input";
import { Alert, AlertDescription } from "../ui/alert";

export const ParameterSetup: React.FC = () => {
  const {
    xAxisParam,
    xAxisMin,
    xAxisMax,
    xAxisStep,
    yAxisParam,
    yAxisMin,
    yAxisMax,
    yAxisStep,
    metric,
    symbol,
    totalCombinations,
    estimatedTimeMinutes,
    isRunning,
    setXAxisParam,
    setXAxisRange,
    setYAxisParam,
    setYAxisRange,
    setMetric,
    runGridSearch,
  } = useGridSearchStore();

  const handleXParamChange = (value: string) => {
    setXAxisParam(value);
  };

  const handleYParamChange = (value: string) => {
    setYAxisParam(value);
  };

  const handleRun = () => {
    console.log("[ParameterSetup] Run button clicked!");
    console.log("[ParameterSetup] Calling runGridSearch...");
    runGridSearch();
    console.log("[ParameterSetup] runGridSearch called (async, will execute in background)");
  };

  const isHighCombinationCount = totalCombinations > 100;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text-primary mb-4">Parameter Configuration</h2>
        <div className="h-px bg-border-main mb-6" />
      </div>

      {/* X-Axis Configuration */}
      <div className="space-y-3">
        <Label className="text-sm font-medium text-text-primary">X-Axis Parameter</Label>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Parameter</Label>
            <Select value={xAxisParam} onValueChange={handleXParamChange} disabled={isRunning}>
              <SelectTrigger className="bg-bg-secondary border-border-main">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AVAILABLE_PARAMETERS.map((param) => (
                  <SelectItem key={param.value} value={param.value}>
                    {param.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Min</Label>
            <Input
              type="number"
              value={xAxisMin}
              onChange={(e) => setXAxisRange(parseFloat(e.target.value), xAxisMax, xAxisStep)}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Max</Label>
            <Input
              type="number"
              value={xAxisMax}
              onChange={(e) => setXAxisRange(xAxisMin, parseFloat(e.target.value), xAxisStep)}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Step</Label>
            <Input
              type="number"
              value={xAxisStep}
              onChange={(e) => setXAxisRange(xAxisMin, xAxisMax, parseFloat(e.target.value))}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
              step="0.1"
            />
          </div>
        </div>
      </div>

      {/* Y-Axis Configuration */}
      <div className="space-y-3">
        <Label className="text-sm font-medium text-text-primary">Y-Axis Parameter</Label>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Parameter</Label>
            <Select value={yAxisParam} onValueChange={handleYParamChange} disabled={isRunning}>
              <SelectTrigger className="bg-bg-secondary border-border-main">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AVAILABLE_PARAMETERS.map((param) => (
                  <SelectItem key={param.value} value={param.value}>
                    {param.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Min</Label>
            <Input
              type="number"
              value={yAxisMin}
              onChange={(e) => setYAxisRange(parseFloat(e.target.value), yAxisMax, yAxisStep)}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Max</Label>
            <Input
              type="number"
              value={yAxisMax}
              onChange={(e) => setYAxisRange(yAxisMin, parseFloat(e.target.value), yAxisStep)}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-text-secondary">Step</Label>
            <Input
              type="number"
              value={yAxisStep}
              onChange={(e) => setYAxisRange(yAxisMin, yAxisMax, parseFloat(e.target.value))}
              disabled={isRunning}
              className="bg-bg-secondary border-border-main"
              step="0.1"
            />
          </div>
        </div>
      </div>

      {/* Optimization Settings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-text-primary">Optimize For</Label>
          <Select value={metric} onValueChange={(value: any) => setMetric(value)} disabled={isRunning}>
            <SelectTrigger className="bg-bg-secondary border-border-main">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="net_pnl">Net PnL</SelectItem>
              <SelectItem value="sharpe">Sharpe Ratio</SelectItem>
              <SelectItem value="profit_factor">Profit Factor</SelectItem>
              <SelectItem value="win_rate">Win Rate</SelectItem>
              <SelectItem value="max_dd">Max Drawdown (minimize)</SelectItem>
              <SelectItem value="calmar">Calmar Ratio</SelectItem>
              <SelectItem value="sortino">Sortino Ratio</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-text-primary">Symbol</Label>
          <Input
            value={symbol}
            disabled
            className="bg-bg-elevated border-border-main text-text-secondary"
          />
        </div>
      </div>

      {/* Estimation */}
      <div className="rounded-lg bg-bg-elevated border border-border-main p-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-text-secondary mb-1">Total Combinations</p>
            <p className="text-2xl font-bold text-text-primary">{totalCombinations}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary mb-1">Estimated Time</p>
            <p className="text-2xl font-bold text-text-primary">~{estimatedTimeMinutes} min</p>
          </div>
        </div>
      </div>

      {/* Warning for high combination count */}
      {isHighCombinationCount && (
        <Alert className="bg-warning/10 border-warning/30">
          <AlertCircle className="h-4 w-4 text-warning" />
          <AlertDescription className="text-sm text-text-primary">
            <strong>High combination count detected.</strong> This search may take a while. Consider
            reducing the parameter ranges or increasing the step size.
          </AlertDescription>
        </Alert>
      )}

      {/* Run Button */}
      <Button
        onClick={handleRun}
        disabled={isRunning}
        className="w-full gap-2 bg-accent-main hover:bg-accent-hover text-white"
        size="lg"
      >
        <Play className="w-4 h-4" />
        {isRunning ? "Running..." : "Run Grid Search"}
      </Button>
    </div>
  );
};
