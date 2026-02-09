import React from "react";
import { SensitivityResult } from "../../stores/sensitivityStore";
import { cn } from "../../lib/utils";

interface TornadoBarProps {
  result: SensitivityResult;
  maxImpact: number;
}

export const TornadoBar: React.FC<TornadoBarProps> = ({ result, maxImpact }) => {
  // Calculate bar widths as percentage of max impact
  const leftWidth = (Math.abs(result.lowImpactPct) / maxImpact) * 50; // 50% of container
  const rightWidth = (Math.abs(result.highImpactPct) / maxImpact) * 50;

  // Determine if impacts are positive or negative
  const leftIsNegative = result.lowImpactPct < 0;
  const rightIsPositive = result.highImpactPct > 0;

  // Format values
  const formatValue = (val: number) => {
    if (Number.isInteger(val)) return val.toString();
    return val.toFixed(2);
  };

  return (
    <div className="group">
      {/* Parameter Name and Values */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary">
            {result.paramDisplayName}
          </span>
          <span
            className={cn(
              "text-xs px-2 py-0.5 rounded-full font-medium",
              result.sensitivity === "high" && "bg-danger/20 text-danger",
              result.sensitivity === "medium" && "bg-warning/20 text-warning",
              result.sensitivity === "low" && "bg-success/20 text-success"
            )}
          >
            {result.sensitivity.toUpperCase()}
          </span>
        </div>
        <div className="text-xs text-text-muted">
          {formatValue(result.lowValue)} → {formatValue(result.baseValue)} →{" "}
          {formatValue(result.highValue)}
        </div>
      </div>

      {/* Tornado Bars */}
      <div className="relative h-10 flex items-center">
        {/* Container with center line */}
        <div className="absolute inset-0 flex">
          {/* Left side (Low value impact) */}
          <div className="flex-1 flex justify-end items-center pr-1">
            <div
              className={cn(
                "h-8 rounded-l-md transition-all duration-300 relative group-hover:opacity-90",
                leftIsNegative ? "bg-danger" : "bg-success"
              )}
              style={{ width: `${leftWidth}%` }}
            >
              {/* Value label */}
              {Math.abs(result.lowImpactPct) > 2 && (
                <div className="absolute inset-0 flex items-center justify-start pl-2">
                  <span className="text-xs font-medium text-white">
                    {result.lowImpactPct > 0 ? "+" : ""}
                    {result.lowImpactPct.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Center divider */}
          <div className="w-px bg-border-main z-10" />

          {/* Right side (High value impact) */}
          <div className="flex-1 flex justify-start items-center pl-1">
            <div
              className={cn(
                "h-8 rounded-r-md transition-all duration-300 relative group-hover:opacity-90",
                rightIsPositive ? "bg-success" : "bg-danger"
              )}
              style={{ width: `${rightWidth}%` }}
            >
              {/* Value label */}
              {Math.abs(result.highImpactPct) > 2 && (
                <div className="absolute inset-0 flex items-center justify-end pr-2">
                  <span className="text-xs font-medium text-white">
                    {result.highImpactPct > 0 ? "+" : ""}
                    {result.highImpactPct.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* External labels for small impacts */}
        {Math.abs(result.lowImpactPct) <= 2 && (
          <div className="absolute left-0 text-xs text-text-muted">
            {result.lowImpactPct > 0 ? "+" : ""}
            {result.lowImpactPct.toFixed(1)}%
          </div>
        )}
        {Math.abs(result.highImpactPct) <= 2 && (
          <div className="absolute right-0 text-xs text-text-muted">
            {result.highImpactPct > 0 ? "+" : ""}
            {result.highImpactPct.toFixed(1)}%
          </div>
        )}
      </div>

      {/* Hover Tooltip */}
      <div className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-text-muted mt-1">
        Total Impact: {result.totalImpact.toFixed(1)}% • Low: {result.lowMetric.toFixed(2)} •
        Base: {result.baseMetric.toFixed(2)} • High: {result.highMetric.toFixed(2)}
      </div>
    </div>
  );
};
