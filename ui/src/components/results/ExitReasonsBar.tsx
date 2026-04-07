import React, { useMemo } from "react";
import { useResultsStore } from "../../stores/resultsStore";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";

const COLORS: Record<string, string> = {
  TP1: "#22c55e",
  TP2: "#16a34a",
  TP3: "#15803d",
  LOCK_PROFIT: "#06b6d4",
  SL: "#ef4444",
  DISASTER_SL: "#7f1d1d",
  MANUAL: "#a1a1aa",
};

export const ExitReasonsBar: React.FC = () => {
  const { exitReasons, setFilter, activeFilter } = useResultsStore();

  const data = useMemo(() => {
    const entries = Object.entries(exitReasons).filter(([, v]) => v > 0);
    const total = entries.reduce((sum, [, v]) => sum + v, 0);
    return { entries, total };
  }, [exitReasons]);

  if (data.total === 0) return null;

  const handleClick = (reason: string) => {
    setFilter(activeFilter === reason ? null : reason);
  };

  return (
    <div className="border border-border-main rounded-xl bg-bg-surface p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Exit Reasons
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-muted font-mono">
            {data.total} trades
          </span>
          {activeFilter && (
            <button
              onClick={() => setFilter(null)}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-main/10 text-accent-main text-[10px] font-medium hover:bg-accent-main/20 transition-colors"
            >
              <X size={10} />
              {activeFilter}
            </button>
          )}
        </div>
      </div>

      {/* Stacked horizontal bar */}
      <div className="flex h-6 rounded-full overflow-hidden">
        {data.entries.map(([reason, count]) => {
          const pct = (count / data.total) * 100;
          const isActive = !activeFilter || activeFilter === reason;
          return (
            <button
              key={reason}
              onClick={() => handleClick(reason)}
              className={cn(
                "transition-opacity duration-200 hover:brightness-110 cursor-pointer",
                isActive ? "opacity-100" : "opacity-30"
              )}
              style={{
                width: `${pct}%`,
                backgroundColor: COLORS[reason] || "#888",
                minWidth: pct > 0 ? "4px" : 0,
              }}
              title={`${reason}: ${count} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3">
        {data.entries.map(([reason, count]) => {
          const isActive = !activeFilter || activeFilter === reason;
          return (
            <button
              key={reason}
              onClick={() => handleClick(reason)}
              className={cn(
                "flex items-center gap-1.5 text-[11px] transition-opacity duration-200 cursor-pointer hover:opacity-80",
                isActive ? "opacity-100" : "opacity-30"
              )}
            >
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: COLORS[reason] || "#888" }}
              />
              <span className="text-text-secondary font-medium">{reason}</span>
              <span className="text-text-muted font-mono">{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
