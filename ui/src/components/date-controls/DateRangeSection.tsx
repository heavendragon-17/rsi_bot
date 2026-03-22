// @ts-nocheck
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { TimezoneSelector } from "./TimezoneSelector";
import { ComputedRangeBadge } from "./ComputedRangeBadge";
import { RelativeTab } from "./RelativeTab";
import { AbsoluteTab } from "./AbsoluteTab";
import { cn } from "../../lib/utils";

export const DateRangeSection: React.FC = () => {
  const { dateMode, setDateMode } = useBacktestStore();

  return (
    <div className="flex flex-col gap-3">
        {/* Header with Timezone */}
        <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-secondary">Date Range</span>
            <TimezoneSelector />
        </div>

        {/* Tab Switcher (Segmented Control) */}
        <div className="flex p-1 bg-bg-elevated rounded-lg">
            <button
                onClick={() => setDateMode("relative")}
                className={cn(
                    "flex-1 py-1 text-[10px] font-medium rounded transition-all",
                    dateMode === "relative"
                        ? "bg-bg-secondary text-text-primary shadow-sm"
                        : "text-text-secondary hover:text-text-primary"
                )}
            >
                Relative (Last X)
            </button>
            <button
                onClick={() => setDateMode("absolute")}
                className={cn(
                    "flex-1 py-1 text-[10px] font-medium rounded transition-all",
                    dateMode === "absolute"
                        ? "bg-bg-secondary text-text-primary shadow-sm"
                        : "text-text-secondary hover:text-text-primary"
                )}
            >
                Absolute (Dates)
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
