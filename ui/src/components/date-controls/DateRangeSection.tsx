import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { TimezoneSelector } from "./TimezoneSelector";
import { ComputedRangeBadge } from "./ComputedRangeBadge";
import { RelativeTab } from "./RelativeTab";
import { AbsoluteTab } from "./AbsoluteTab";
import { cn } from "../../lib/utils";
import { RotateCcw } from "lucide-react";
import { motion } from "motion/react";

export const DateRangeSection: React.FC = () => {
  const { dateMode, setDateMode, resetToDefaults } = useBacktestStore();

  return (
    <div className="flex flex-col gap-3">
      {/* Header with Timezone and Reset */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider">
            Date Range
          </span>
          <button
            onClick={resetToDefaults}
            className="p-1 rounded-md hover:bg-white/5 text-text-muted hover:text-accent-main transition-colors group"
            title="Reset to Defaults"
          >
            <RotateCcw
              size={10}
              className="group-active:rotate-[-90deg] transition-transform"
            />
          </button>
        </div>
        <TimezoneSelector />
      </div>

      {/* Tab Switcher (Segmented Control) */}
      <div className="relative flex p-1 bg-bg-elevated/50 rounded-lg border border-border-main/50 overflow-hidden">
        {/* Sliding Background */}
        <motion.div
          className="absolute inset-y-1 bg-bg-secondary rounded shadow-sm z-0"
          initial={false}
          animate={{
            x: dateMode === "relative" ? 0 : "100%",
          }}
          transition={{ type: "spring", stiffness: 350, damping: 30 }}
          style={{ width: "calc(50% - 4px)" }}
        />

        <button
          onClick={() => setDateMode("relative")}
          className={cn(
            "relative flex-1 py-1.5 text-[10px] font-bold rounded z-10 transition-colors uppercase tracking-tight",
            dateMode === "relative"
              ? "text-text-primary"
              : "text-text-secondary hover:text-text-primary"
          )}
        >
          Relative
        </button>
        <button
          onClick={() => setDateMode("absolute")}
          className={cn(
            "relative flex-1 py-1.5 text-[10px] font-bold rounded z-10 transition-colors uppercase tracking-tight",
            dateMode === "absolute"
              ? "text-text-primary"
              : "text-text-secondary hover:text-text-primary"
          )}
        >
          Absolute
        </button>
      </div>

      {/* Tab Content */}
      <div className="min-h-[80px]">
        {dateMode === "relative" ? <RelativeTab /> : <AbsoluteTab />}
      </div>

      {/* Footer Info */}
      <ComputedRangeBadge />
    </div>
  );
};
