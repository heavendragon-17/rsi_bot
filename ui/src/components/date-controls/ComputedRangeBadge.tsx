import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";
import { Info } from "lucide-react";

export const ComputedRangeBadge: React.FC = () => {
  const estimatedBars = useBacktestStore((state) => state.getEstimatedBars());

  // Logic from prompt
  // > 1M: Danger
  // > 100k: Warning
  // > 10k: Standard
  // < 10k: Muted (Fast)

  let colorClass = "text-text-muted";
  if (estimatedBars > 10000) colorClass = "text-text-secondary";
  if (estimatedBars > 100000) colorClass = "text-warning";
  if (estimatedBars > 1000000) colorClass = "text-danger";

  // Rough size calc: ~80 bytes per bar (OHLCV + Time + Indicators)
  const sizeBytes = estimatedBars * 80;
  const sizeMB = (sizeBytes / 1024 / 1024).toFixed(1);
  const displaySize = sizeMB === "0.0" ? "< 0.1MB" : `${sizeMB}MB`;

  return (
    <div className="flex items-center gap-1.5 px-3 py-2 mt-3 rounded-md bg-bg-elevated/30 border border-border-main/50">
      <Info size={12} className={colorClass} />
      <span className={cn("text-xs font-medium font-mono", colorClass)}>
        ~{estimatedBars.toLocaleString()} bars
      </span>
      <span className="text-[10px] text-text-muted ml-auto">
        Est. Data: {displaySize}
      </span>
    </div>
  );
};
