import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useResultsStore } from "../../stores/resultsStore";
import { ExportDropdown } from "../export";
import { cn } from "../../lib/utils";

export const HeaderBar: React.FC = () => {
  const { strategy, symbol, timeframe } = useBacktestStore();
  const { feesEnabled } = useResultsStore();

  return (
    <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-border-main bg-bg-surface/50 backdrop-blur-md sticky top-0 z-20 min-h-[56px]">
      {/* Left: strategy + symbol + timeframe — allow wrap on small screens */}
      <div className="flex items-center gap-2 flex-wrap min-w-0">
        <h1 className="text-base font-bold text-text-primary whitespace-nowrap">
          {strategy.replace(/_/g, " ").toUpperCase()}
        </h1>
        <span className="text-text-secondary text-sm">·</span>
        <span className="text-sm font-mono text-accent-main font-semibold whitespace-nowrap">
          {symbol}
        </span>
        <span className="px-2 py-0.5 rounded-md bg-bg-elevated text-xs font-semibold text-text-secondary border border-border-main whitespace-nowrap">
          {timeframe}
        </span>
      </div>

      {/* Right: fees badge + export */}
      <div className="flex items-center gap-3 shrink-0">
        <div
          className={cn(
            "px-2.5 py-1 rounded-full text-xs font-bold border flex items-center gap-1.5 select-none whitespace-nowrap",
            feesEnabled
              ? "bg-success/10 border-success/30 text-success"
              : "bg-warning/10 border-warning/30 text-warning"
          )}
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              feesEnabled ? "bg-success" : "bg-warning"
            )}
          />
          Fees: {feesEnabled ? "ON" : "OFF"}
        </div>

        <ExportDropdown />
      </div>
    </div>
  );
};
