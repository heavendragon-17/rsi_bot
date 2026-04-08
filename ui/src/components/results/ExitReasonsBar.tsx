import React, { useMemo } from "react";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

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

  const data = useMemo(
    () => Object.entries(exitReasons).map(([name, value]) => ({ name, value })),
    [exitReasons]
  );

  const total = useMemo(
    () => data.reduce((sum, d) => sum + d.value, 0),
    [data]
  );

  const handleClick = (name: string) => {
    setFilter(activeFilter === name ? null : name);
  };

  if (total === 0) {
    return (
      <div className="bg-bg-secondary border border-border-main rounded-xl px-3 py-2.5 text-center text-text-muted text-xs">
        No exit data
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="bg-bg-secondary border border-border-main rounded-xl px-3 py-2.5 shadow-sm"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-text-secondary">
            Exit Reasons
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
        <span className="text-[9px] text-text-muted">{total} trades</span>
      </div>

      {/* Stacked Bar */}
      <div className="flex h-5 rounded-[10px] overflow-hidden w-full">
        {data.map((d) => {
          const pct = (d.value / total) * 100;
          if (pct === 0) return null;
          return (
            <button
              key={d.name}
              onClick={() => handleClick(d.name)}
              title={`${d.name}: ${d.value} trades`}
              className={cn(
                "h-full transition-opacity duration-200 cursor-pointer",
                activeFilter && activeFilter !== d.name
                  ? "opacity-30"
                  : "opacity-100 hover:opacity-80"
              )}
              style={{
                width: `${pct}%`,
                backgroundColor: COLORS[d.name] || "#888",
              }}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 items-center mt-2">
        {data.map((d) => (
          <button
            key={d.name}
            onClick={() => handleClick(d.name)}
            className={cn(
              "flex items-center gap-1 cursor-pointer transition-opacity duration-200",
              activeFilter && activeFilter !== d.name ? "opacity-30" : "opacity-100"
            )}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: COLORS[d.name] || "#888" }}
            />
            <span className="text-[9px] font-medium text-text-secondary">
              {d.name}
            </span>
            <span className="text-[9px] font-bold text-text-muted">
              {d.value}
            </span>
          </button>
        ))}
      </div>
    </motion.div>
  );
};
