import React from "react";
import { Star } from "lucide-react";
import { GridSearchResult, useGridSearchStore, AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";

interface HeatmapCellProps {
  result: GridSearchResult;
  x: number;
  y: number;
  minValue: number;
  maxValue: number;
  isBest: boolean;
  gridSize: number; // NEW: for responsive sizing
}

export const HeatmapCell: React.FC<HeatmapCellProps> = ({
  result,
  x,
  y,
  minValue,
  maxValue,
  isBest,
  gridSize, // NEW
}) => {
  const { metric, setHoveredCell, xAxisParam, yAxisParam } = useGridSearchStore();

  // Get the value based on current metric
  let value: number;
  let displayValue: string;
  
  switch (metric) {
    case "net_pnl":
      value = result.netPnL;
      displayValue = `$${value >= 0 ? "+" : ""}${value.toFixed(0)}`;
      break;
    case "sharpe":
      value = result.sharpe;
      displayValue = value.toFixed(2);
      break;
    case "profit_factor":
      value = result.profitFactor;
      displayValue = value.toFixed(2);
      break;
    case "win_rate":
      value = result.winRate;
      displayValue = `${value.toFixed(1)}%`;
      break;
    case "max_dd":
      value = -result.maxDrawdownPct;
      displayValue = `${result.maxDrawdownPct.toFixed(1)}%`;
      break;
    case "calmar":
      value = result.calmar || result.sharpe; // Fallback
      displayValue = value.toFixed(2);
      break;
    case "sortino":
      value = result.sortino || result.sharpe; // Fallback
      displayValue = value.toFixed(2);
      break;
    default:
      value = result.netPnL;
      displayValue = `$${value.toFixed(0)}`;
  }

  // Calculate color based on value range
  const getColor = () => {
    if (maxValue === minValue) return "bg-yellow-500/50";

    const normalized = (value - minValue) / (maxValue - minValue);

    if (normalized < 0.2) return "bg-red-600"; // Dark red
    if (normalized < 0.4) return "bg-red-400"; // Light red
    if (normalized < 0.6) return "bg-yellow-400"; // Yellow
    if (normalized < 0.8) return "bg-green-400"; // Light green
    return "bg-green-600"; // Dark green
  };

  const getTextColor = () => {
    const normalized = (value - minValue) / (maxValue - minValue);
    return normalized < 0.3 || normalized > 0.7 ? "text-white" : "text-gray-900";
  };

  const getParamLabel = (paramValue: string) => {
    const param = AVAILABLE_PARAMETERS.find((p) => p.value === paramValue);
    return param?.label || paramValue;
  };

  // Responsive sizing based on grid density
  const getCellClasses = () => {
    if (gridSize <= 6) return 'h-20 text-sm'; // Large cells for small grids
    if (gridSize <= 10) return 'h-16 text-xs'; // Medium cells for medium grids
    return 'h-12 text-[10px]'; // Small cells for large grids
  };

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={`
              ${getCellClasses()}
              relative flex items-center justify-center
              ${getColor()} ${getTextColor()}
              border border-border-main/30
              transition-all duration-150
              hover:scale-105 hover:z-10 hover:shadow-lg
              cursor-pointer
              ${isBest ? "ring-4 ring-yellow-400 shadow-xl z-20" : ""}
            `}
            onMouseEnter={() => setHoveredCell({ x, y })}
            onMouseLeave={() => setHoveredCell(null)}
          >
            <div className="text-center">
              {isBest && (
                <div className="absolute -top-2 -right-2 bg-yellow-400 rounded-full p-1">
                  <Star className="w-3 h-3 text-gray-900 fill-gray-900" />
                </div>
              )}
              <div className="text-xs font-semibold leading-tight">
                {displayValue}
              </div>
              {isBest && (
                <div className="text-[10px] font-bold mt-0.5">
                  BEST
                </div>
              )}
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="bg-card border-border-main p-4 max-w-xs"
        >
          <div className="space-y-2">
            <div className="font-semibold text-text-primary border-b border-border-main pb-2">
              Parameter Values
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-text-secondary">{getParamLabel(xAxisParam)}:</div>
              <div className="font-mono font-semibold text-text-primary">
                {result.xValue.toFixed(result.xValue % 1 === 0 ? 0 : 2)}
              </div>
              <div className="text-text-secondary">{getParamLabel(yAxisParam)}:</div>
              <div className="font-mono font-semibold text-text-primary">
                {result.yValue.toFixed(result.yValue % 1 === 0 ? 0 : 2)}
              </div>
            </div>

            <div className="font-semibold text-text-primary border-b border-t border-border-main py-2">
              Performance Metrics
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-text-secondary">Net PnL:</div>
              <div className={`font-semibold ${result.netPnL >= 0 ? "text-success" : "text-danger"}`}>
                ${result.netPnL >= 0 ? "+" : ""}{result.netPnL.toFixed(2)} ({result.netPnLPct >= 0 ? "+" : ""}{result.netPnLPct.toFixed(2)}%)
              </div>

              <div className="text-text-secondary">Sharpe:</div>
              <div className="font-semibold text-text-primary">{result.sharpe.toFixed(2)}</div>

              <div className="text-text-secondary">Win Rate:</div>
              <div className="font-semibold text-text-primary">{result.winRate.toFixed(1)}%</div>

              <div className="text-text-secondary">Profit Factor:</div>
              <div className="font-semibold text-text-primary">{result.profitFactor.toFixed(2)}</div>

              <div className="text-text-secondary">Max DD:</div>
              <div className="font-semibold text-danger">{result.maxDrawdownPct.toFixed(2)}%</div>

              <div className="text-text-secondary">Trades:</div>
              <div className="font-semibold text-text-primary">{result.tradeCount}</div>
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};