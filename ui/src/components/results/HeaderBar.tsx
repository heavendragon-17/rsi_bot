import React from "react";
import { Download } from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useResultsStore } from "../../stores/resultsStore";
import { exportTradesToCSV } from "../../lib/csv-export";
import { ExportDropdown } from "../export";
import { cn } from "../../lib/utils";

export const HeaderBar: React.FC = () => {
  const { strategy, symbol, timeframe } = useBacktestStore();
  const { feesEnabled, trades } = useResultsStore();

  return (
    <div className="flex items-center justify-between p-4 border-b border-border-main bg-bg-surface/50 backdrop-blur-md sticky top-0 z-20">
      <div className="flex items-center gap-4">
          <div>
              <h1 className="text-lg font-bold text-text-primary flex items-center gap-2">
                  {strategy.replace(/_/g, " ").toUpperCase()}
                  <span className="text-text-secondary text-sm font-normal">•</span>
                  <span className="text-sm font-mono text-accent-main">{symbol}</span>
                  <span className="px-1.5 py-0.5 rounded bg-bg-elevated text-xs font-medium text-text-secondary border border-border-main">
                      {timeframe}
                  </span>
              </h1>
          </div>
      </div>

      <div className="flex items-center gap-3">
          {/* Fees Badge - "The Liar's Toggle" */}
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
