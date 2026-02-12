import React from "react";
import { useGridSearchStore, AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
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

  // Calculate grid size for responsive cell sizing
  const gridSize = Math.max(xValues.length, yValues.length);

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
          value = cell.calmar || cell.sharpe;
          break;
        case "sortino":
          value = cell.sortino || cell.sharpe;
          break;
        default:
          value = cell.netPnL;
      }
      minValue = Math.min(minValue, value);
      maxValue = Math.max(maxValue, value);
    });
  });

  const getParamLabel = (paramValue: string) => {
    const param = AVAILABLE_PARAMETERS.find(
      (p) => p.value === paramValue
    );
    return param?.label || paramValue;
  };

  const metricLabel = 
    metric === "net_pnl" ? "Net PnL" : 
    metric === "sharpe" ? "Sharpe Ratio" : 
    metric === "profit_factor" ? "Profit Factor" : 
    metric === "win_rate" ? "Win Rate %" : 
    metric === "max_dd" ? "Max Drawdown %" : 
    metric === "calmar" ? "Calmar Ratio" :
    metric === "sortino" ? "Sortino Ratio" : metric;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">
          Heatmap: {metricLabel}
        </h3>
        <p className="text-sm text-text-secondary">
          {getParamLabel(xAxisParam)} vs {getParamLabel(yAxisParam)} · Hover over cells for detailed metrics
        </p>
      </div>

      {/* Responsive Grid Layout */}
      <div className="w-full">
        <div className="grid grid-cols-[auto_1fr] gap-4">
          {/* Y-axis label (vertical) */}
          <div className="flex items-center justify-center w-12">
            <div className="transform -rotate-90 whitespace-nowrap text-sm font-medium text-text-secondary">
              {getParamLabel(yAxisParam)}
            </div>
          </div>

          {/* Main grid */}
          <div className="space-y-1">
            {/* X-axis labels */}
            <div 
              className="grid gap-1 mb-2" 
              style={{gridTemplateColumns: `4rem repeat(${xValues.length}, minmax(0, 1fr))`}}
            >
              <div /> {/* Spacer for Y-axis values */}
              {xValues.map((xValue, idx) => (
                <div key={idx} className="text-center text-xs font-medium text-text-secondary">
                  {xValue.toFixed(xValue % 1 === 0 ? 0 : 1)}
                </div>
              ))}
            </div>

            {/* Grid rows */}
            {results.map((row, yIdx) => (
              <div 
                key={yIdx}
                className="grid gap-1"
                style={{gridTemplateColumns: `4rem repeat(${xValues.length}, minmax(0, 1fr))`}}
              >
                {/* Y-axis value */}
                <div className="flex items-center justify-end pr-2 text-xs font-medium text-text-secondary">
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
                    gridSize={gridSize}
                  />
                ))}
              </div>
            ))}

            {/* X-axis label */}
            <div className="text-center text-sm font-medium text-text-secondary mt-2">
              {getParamLabel(xAxisParam)}
            </div>
          </div>
        </div>
      </div>

      {/* Color Scale Legend */}
      <HeatmapColorScale minValue={minValue} maxValue={maxValue} metric={metric} />
    </div>
  );
};