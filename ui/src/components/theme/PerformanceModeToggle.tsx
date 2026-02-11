import React from "react";
import { useThemeStore } from "../../stores/themeStore";
import { cn } from "../../lib/utils";
import { PremiumToggle } from "../ui/PremiumToggle";

export const PerformanceModeToggle: React.FC = () => {
  const { performanceMode, togglePerformanceMode } = useThemeStore();

  return (
    <div className="space-y-4">
      <label className="mb-4 block text-sm font-semibold uppercase tracking-wider text-text-muted">
        Performance Mode
      </label>

      {/* Toggle Switch */}
      <div className="flex items-center justify-between rounded-2xl border border-border-main bg-bg-elevated/50 p-6 sm:p-8">
        <div className="flex-1 pr-4">
          <p className="text-base font-medium text-text-primary">
            Reduce animations for large datasets
          </p>
          <p className="mt-2 text-sm text-text-secondary leading-relaxed">
            Disables chart animations and simplifies transitions to improve
            performance on low-end devices or during heavy computation.
          </p>
        </div>

        <PremiumToggle
          checked={performanceMode}
          onCheckedChange={togglePerformanceMode}
        />
      </div>

      {/* Feature List (when enabled) */}
      {performanceMode && (
        <div className="rounded-2xl border border-border-main bg-bg-elevated/30 p-6 sm:p-8 animate-in zoom-in-95 duration-300">
          <p className="mb-4 text-sm font-bold uppercase tracking-wider text-text-primary">
            Active Optimizations
          </p>
          <ul className="space-y-3">
            {[
              "Chart animations disabled",
              "Hover effects simplified",
              "Backdrop blur reduced",
            ].map((text) => (
              <li
                key={text}
                className="flex items-center gap-3 text-sm text-text-secondary"
              >
                <div className="h-2 w-2 rounded-full bg-accent-main shadow-[0_0_8px_rgba(var(--accent-rgb),0.5)]" />
                {text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
