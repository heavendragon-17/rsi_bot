import React from "react";
import { useGridSearchStore } from "../../stores/gridSearchStore";
import { HeatmapCell } from "./HeatmapCell";
import { HeatmapColorScale } from "./HeatmapColorScale";

export const Heatmap: React.FC = () => {
  const {
    results,
    bestResult,
    xAxisParam,
    yAxisParam,
    xAxisMin,
    xAxisStep,
    yAxisMin,
    yAxisStep,
    metric,
  } = useGridSearchStore();

  if (!results) return null;

  // Generate X and Y axis labels
  const xValues: number[] = [];
  results[0]?.forEach((cell) => {
    xValues.push(cell.xValue);
  });

  const yValues: number[] = [];
  results.forEach((row) => {
    if (row[0]) yValues.push(row[0].yValue);
  });

  // Find min/max values for color scaling
  let minValue = Infinity;
  let maxValue = -Infinity;

  results.forEach((row) => {
    row.forEach((cell) => {
      let value: number;
      switch (metric) {
        case "net_pnl":
          value = cell.netPnL;
          break;
        case "sharpe":
          value = cell.sharpe;
          break;
        case "profit_factor":
          value = cell.profitFactor;
          break;
        case "win_rate":
          value = cell.winRate;
          break;
        case "max_dd":
          value = -cell.maxDrawdownPct;
          break;
        case "calmar":
          value = cell.calmar || cell.sharpe; // Fallback to sharpe if not available
          break;
        case "sortino":
          value = cell.sortino || cell.sharpe; // Fallback to sharpe if not available
          break;
        default:
          value = cell.netPnL;
      }
      minValue = Math.min(minValue, value);
      maxValue = Math.max(maxValue, value);
    });
  });

  const getParamLabel = (paramValue: string) => {
    const param = require("../../stores/gridSearchStore").AVAILABLE_PARAMETERS.find(
      (p: any) => p.value === paramValue
    );
    return param?.label || paramValue;
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">
          Heatmap: {metric === "net_pnl" ? "Net PnL" :
                    metric === "sharpe" ? "Sharpe Ratio" :
                    metric === "profit_factor" ? "Profit Factor" :
                    metric === "win_rate" ? "Win Rate %" :
                    metric === "max_dd" ? "Max Drawdown %" :
                    metric === "calmar" ? "Calmar Ratio" :
                    metric === "sortino" ? "Sortino Ratio" : metric}
        </h3>
        <p className="text-sm text-text-secondary">
          {getParamLabel(xAxisParam)} vs {getParamLabel(yAxisParam)} · Hover over cells for detailed metrics
        </p>
      </div>

      <div className="h-px bg-border-main" />

      {/* Heatmap Grid */}
      <div className="overflow-x-auto">
        <div className="inline-block min-w-full">
          <div className="flex">
            {/* Y-axis label (vertical) */}
            <div className="flex items-center justify-center pr-4 min-w-[60px]">
              <div className="transform -rotate-90 whitespace-nowrap text-sm font-medium text-text-secondary">
                {getParamLabel(yAxisParam)}
              </div>
            </div>

            {/* Grid container */}
            <div className="flex-1">
              {/* X-axis labels */}
              <div className="flex mb-2">
                <div className="w-24" /> {/* Spacer for Y-axis values */}
                {xValues.map((xValue, xIdx) => (
                  <div
                    key={xIdx}
                    className="flex-1 min-w-[80px] text-center text-xs font-medium text-text-secondary"
                  >
                    {xValue.toFixed(xValue % 1 === 0 ? 0 : 1)}
                  </div>
                ))}
              </div>

              {/* Grid rows */}
              {results.map((row, yIdx) => (
                <div key={yIdx} className="flex mb-1">
                  {/* Y-axis value */}
                  <div className="w-24 flex items-center justify-end pr-3 text-xs font-medium text-text-secondary">
                    {yValues[yIdx].toFixed(yValues[yIdx] % 1 === 0 ? 0 : 1)}
                  </div>

                  {/* Cells */}
                  {row.map((cell, xIdx) => (
                    <HeatmapCell
                      key={`${xIdx}-${yIdx}`}
                      result={cell}
                      x={xIdx}
                      y={yIdx}
                      minValue={minValue}
                      maxValue={maxValue}
                      isBest={bestResult?.x === xIdx && bestResult?.y === yIdx}
                    />
                  ))}
                </div>
              ))}

              {/* X-axis label */}
              <div className="text-center text-sm font-medium text-text-secondary mt-3">
                {getParamLabel(xAxisParam)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Color Scale Legend */}
      <HeatmapColorScale minValue={minValue} maxValue={maxValue} metric={metric} />
    </div>
  );
};
