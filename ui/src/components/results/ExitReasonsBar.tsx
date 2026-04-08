import React, { useMemo } from "react";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

const COLORS: Record<string, string> = {
  // Full wins — greens
  TP1: "#22c55e",
  TP2: "#16a34a",
  TP3: "#15803d",
  LOCK_PROFIT: "#06b6d4",
  // Partial wins (TP hit, then SL) — ambers
  "TP1+SL": "#f59e0b",
  "TP2+SL": "#eab308",
  "TP3+SL": "#84cc16",
  // Losses — reds / orange
  SL: "#ef4444",
  CLOSE_BY_CANDLE_SL: "#f97316",
  DISASTER_SL: "#991b1b",
  // Neutral / other
  EOD: "#64748b",
  BREAKEVEN: "#94a3b8",
  TRAILING_STOP: "#a855f7",
  MANUAL: "#a1a1aa",
};

/** Fallback: cycle through a distinct palette for unknown reasons */
const FALLBACK_PALETTE = [
  "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f43f5e", "#0ea5e9",
];
let _fallbackIdx = 0;
const _dynamicColors: Record<string, string> = {};
const getColor = (name: string): string => {
  if (COLORS[name]) return COLORS[name];
  if (!_dynamicColors[name]) {
    _dynamicColors[name] = FALLBACK_PALETTE[_fallbackIdx % FALLBACK_PALETTE.length];
    _fallbackIdx++;
  }
  return _dynamicColors[name];
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

      {/* Stacked Bar — flex: d.value avoids sub-pixel float gaps */}
      <div className="flex h-5 w-full rounded-full overflow-hidden">
        {data.map((d, i) => {
          if (d.value === 0) return null;
          const isFirst = i === data.findIndex((x) => x.value > 0);
          const isLast = i === data.length - 1 - [...data].reverse().findIndex((x) => x.value > 0);
          return (
            <button
              key={d.name}
              onClick={() => handleClick(d.name)}
              title={`${d.name}: ${d.value} trades`}
              className={cn(
                "h-full transition-opacity duration-200 cursor-pointer",
                activeFilter && activeFilter !== d.name
                  ? "opacity-25"
                  : "opacity-100 hover:opacity-80"
              )}
              style={{
                flex: d.value,
                backgroundColor: getColor(d.name),
                borderRadius: isFirst && isLast
                  ? "9999px"
                  : isFirst
                  ? "9999px 0 0 9999px"
                  : isLast
                  ? "0 9999px 9999px 0"
                  : undefined,
              }}
            />
          );
        })}
      </div>

      {/* Legend — larger color swatch so no hovering needed */}
      <div className="flex flex-wrap gap-x-3 gap-y-1.5 items-center mt-2.5">
        {data.map((d) => (
          <button
            key={d.name}
            onClick={() => handleClick(d.name)}
            className={cn(
              "flex items-center gap-1.5 cursor-pointer transition-opacity duration-200",
              activeFilter && activeFilter !== d.name ? "opacity-25" : "opacity-100"
            )}
          >
            <span
              className="w-2.5 h-2.5 rounded-sm shrink-0"
              style={{ backgroundColor: getColor(d.name) }}
            />
            <span className="text-[10px] font-medium text-text-secondary">
              {d.name}
            </span>
            <span className="text-[10px] font-bold text-text-primary">
              {d.value}
            </span>
          </button>
        ))}
      </div>
    </motion.div>
  );
};
