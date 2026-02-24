import React from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { WindowBlock } from "./WindowBlock";
import { AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";

export const TimelineVisualization: React.FC = () => {
  const { windows, paramToOptimize } = useWalkForwardStore();

  if (windows.length === 0) {
    return (
      <div className="p-8 rounded-lg bg-bg-elevated border border-dashed border-border-main text-center">
        <p className="text-sm text-text-secondary">
          Run walk-forward optimization to see timeline visualization
        </p>
      </div>
    );
  }

  const paramLabel =
    AVAILABLE_PARAMETERS.find((p) => p.value === paramToOptimize)?.label ||
    paramToOptimize;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">
          Walk-Forward Timeline
        </h3>
        <div className="flex flex-wrap items-center gap-4 text-xs text-text-secondary">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-accent-main/20 border border-accent-main/40 rounded" />
            <span>In-Sample (IS)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-success/10 border border-success/40 rounded" />
            <span>OOS Positive</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-danger/10 border border-danger/40 rounded" />
            <span>OOS Negative</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-bg-elevated border border-border-main rounded" />
            <span>Skipped</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 bg-danger/5 border border-danger/40 rounded" />
            <span>Failed</span>
          </div>
        </div>
      </div>

      {/* Compact grid view of all windows */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-3">
        {windows.map((window) => (
          <WindowBlock
            key={window.index}
            window={window}
            paramName={paramLabel}
            isCompact
          />
        ))}
      </div>

      {/* Data range indicator */}
      <div className="relative pt-8">
        <div className="absolute top-0 left-0 right-0 h-1 bg-border-main rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-main/40 transition-all duration-300"
            style={{
              width: `${(windows.length / (windows.length + 1)) * 100}%`,
            }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-text-tertiary">
          <span>{windows[0]?.isStartDate || "Jan 1, 2024"}</span>
          <span className="text-text-secondary">{windows.length} windows</span>
          <span>
            {windows[windows.length - 1]?.oosEndDate || "Dec 31, 2024"}
          </span>
        </div>
      </div>
    </div>
  );
};
