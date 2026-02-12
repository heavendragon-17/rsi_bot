import React from "react";
import { GridMetric } from "../../stores/gridSearchStore";

interface HeatmapColorScaleProps {
  minValue: number;
  maxValue: number;
  metric: GridMetric;
}

export const HeatmapColorScale: React.FC<HeatmapColorScaleProps> = ({
  minValue,
  maxValue,
  metric,
}) => {
  const formatValue = (value: number) => {
    if (metric === "net_pnl") {
      return `$${value >= 0 ? "+" : ""}${value.toFixed(0)}`;
    } else if (metric === "win_rate" || metric === "max_dd") {
      return `${value.toFixed(1)}%`;
    } else {
      return value.toFixed(2);
    }
  };

  // Generate 5 points along the scale
  const range = maxValue - minValue;
  const points = [
    minValue,
    minValue + range * 0.25,
    minValue + range * 0.5,
    minValue + range * 0.75,
    maxValue,
  ];

  const colors = [
    "bg-red-600",
    "bg-red-400",
    "bg-yellow-400",
    "bg-green-400",
    "bg-green-600",
  ];

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-text-primary">Color Scale</div>
      
      <div className="flex items-center gap-1">
        {colors.map((color, idx) => (
          <div key={idx} className="flex-1 space-y-1">
            <div className={`h-8 ${color} border border-border-main/30 rounded`} />
            <div className="text-xs text-center text-text-secondary font-mono">
              {formatValue(points[idx])}
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-between text-xs text-text-secondary/70 italic mt-1">
        <span>← Worse</span>
        <span>Better →</span>
      </div>
    </div>
  );
};
