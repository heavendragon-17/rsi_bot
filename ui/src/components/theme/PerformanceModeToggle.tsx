import React from "react";
import { useThemeStore } from "../../stores/themeStore";
import { cn } from "../../lib/utils";

export const PerformanceModeToggle: React.FC = () => {
  const { performanceMode, togglePerformanceMode } = useThemeStore();

  return (
    <div className="space-y-2">
      <label className="mb-2 block text-xs font-medium text-text-secondary">
        Performance Mode
      </label>

      {/* Toggle Switch */}
      <div className="flex items-center justify-between rounded-lg border border-border-main bg-bg-elevated/50 p-3">
        <div className="flex-1">
          <p className="text-xs text-text-primary">
            Reduce animations for large datasets
          </p>
          <p className="mt-1 text-[10px] text-text-muted">
            Disables chart animations and simplifies transitions
          </p>
        </div>

        <button
          onClick={togglePerformanceMode}
          className={cn(
            "relative ml-3 h-6 w-11 rounded-full transition-colors",
            performanceMode ? "bg-accent-main" : "bg-border-color"
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform",
              performanceMode ? "left-[22px]" : "left-0.5"
            )}
          />
        </button>
      </div>

      {/* Feature List (when enabled) */}
      {performanceMode && (
        <div className="rounded-lg border border-border-main bg-bg-elevated/30 p-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            Active Optimizations
          </p>
          <ul className="space-y-1 text-[10px] text-text-secondary">
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-accent-main" />
              Chart animations disabled
            </li>
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-accent-main" />
              Hover effects simplified
            </li>
            <li className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-accent-main" />
              Backdrop blur reduced
            </li>
          </ul>
        </div>
      )}
    </div>
  );
};
