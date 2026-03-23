import React from "react";
import { Download } from "lucide-react";
import { useBacktestStore } from "../../../stores/backtestStore";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";
import { ExportDropdown } from "../../export";
import { cn } from "../../../lib/utils";

export const BatchHeaderBar: React.FC = () => {
  const { strategy } = useBacktestStore();
  const { symbols, allocationMode, hasBatchResults } = useBatchResultsStore();

  // Hardcoded Fees for consistency with main header
  const feesEnabled = true;

  if (!hasBatchResults) return null;

  return (
    <div className="flex items-center justify-between p-4 border-b border-border-main bg-bg-surface/50 backdrop-blur-md sticky top-0 z-20">
      <div className="flex items-center gap-4">
          <div>
              <h1 className="text-lg font-bold text-text-primary flex items-center gap-2">
                  {strategy.replace(/_/g, " ").toUpperCase()}
                  <span className="text-text-secondary text-sm font-normal">•</span>
                  <span className="text-sm font-mono text-accent-main">BATCH ({symbols.length} symbols)</span>
              </h1>
          </div>

          <div className="px-2 py-0.5 rounded bg-accent-main/10 border border-accent-main/30 text-accent-main text-xs font-medium uppercase tracking-wide">
              {allocationMode.replace("_", " ")}
          </div>
      </div>

      <div className="flex items-center gap-3">
          {/* Fees Badge */}
          <div className={cn(
              "px-2.5 py-1 rounded-full text-xs font-bold border flex items-center gap-1.5 select-none",
              feesEnabled
                  ? "bg-success/10 border-success/30 text-success"
                  : "bg-warning/10 border-warning/30 text-warning"
          )}>
              <span className={cn("w-1.5 h-1.5 rounded-full", feesEnabled ? "bg-success" : "bg-warning")} />
              Fees: {feesEnabled ? "ON" : "OFF"}
          </div>

          <ExportDropdown />
      </div>
    </div>
  );
};
