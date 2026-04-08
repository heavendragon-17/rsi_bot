import React, { useMemo } from "react";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

// ── Color map ──────────────────────────────────────────────────────────────
const COLORS: Record<string, string> = {
  // Pure wins — greens
  TP1:         "#22c55e",
  TP2:         "#16a34a",
  TP3:         "#15803d",
  LOCK_PROFIT: "#06b6d4",
  // Partial wins (TP hit then SL) — ambers
  "TP1+SL":   "#f59e0b",
  "TP2+SL":   "#eab308",
  "TP3+SL":   "#84cc16",
  // Losses — red / orange / dark red
  SL:                  "#ef4444",
  CLOSE_BY_CANDLE_SL:  "#f97316",
  DISASTER_SL:         "#991b1b",
  // Other
  TRAILING_STOP: "#a855f7",
  EOD:           "#64748b",
  BREAKEVEN:     "#94a3b8",
  MANUAL:        "#a1a1aa",
};

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

// ── Group definitions (controls bar order + legend grouping) ───────────────
const GROUPS: { label: string; keys: string[] }[] = [
  { label: "Wins",    keys: ["TP1", "TP2", "TP3", "LOCK_PROFIT"] },
  { label: "Partial", keys: ["TP1+SL", "TP2+SL", "TP3+SL"] },
  { label: "Losses",  keys: ["SL", "CLOSE_BY_CANDLE_SL", "DISASTER_SL"] },
  { label: "Other",   keys: ["TRAILING_STOP", "EOD", "BREAKEVEN", "MANUAL"] },
];

const GROUP_SORT: Record<string, number> = {};
GROUPS.forEach((g, gi) => g.keys.forEach((k, ki) => { GROUP_SORT[k] = gi * 100 + ki; }));

// ── Component ──────────────────────────────────────────────────────────────
export const ExitReasonsBar: React.FC = () => {
  const { exitReasons, setFilter, activeFilter } = useResultsStore();

  // Sort by group order so the bar always reads: Wins → Partial → Losses → Other
  const data = useMemo(() => {
    return Object.entries(exitReasons)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => {
        const ga = GROUP_SORT[a.name] ?? 999;
        const gb = GROUP_SORT[b.name] ?? 999;
        return ga !== gb ? ga - gb : a.name.localeCompare(b.name);
      });
  }, [exitReasons]);

  const total = useMemo(() => data.reduce((s, d) => s + d.value, 0), [data]);

  // Single CSS gradient — zero gaps guaranteed (one DOM element)
  const gradient = useMemo(() => {
    let pos = 0;
    const stops = data.map((d) => {
      const pct = (d.value / total) * 100;
      const stop = `${getColor(d.name)} ${pos.toFixed(6)}% ${(pos + pct).toFixed(6)}%`;
      pos += pct;
      return stop;
    });
    return `linear-gradient(to right, ${stops.join(", ")})`;
  }, [data, total]);

  const handleClick = (name: string) =>
    setFilter(activeFilter === name ? null : name);

  if (total === 0) {
    return (
      <div className="bg-bg-secondary border border-border-main rounded-xl px-3 py-2.5 text-center text-text-muted text-xs">
        No exit data
      </div>
    );
  }

  // Build grouped legend — only show groups that have data
  const legendGroups = GROUPS.map((g) => ({
    label: g.label,
    items: g.keys.map((k) => data.find((d) => d.name === k)).filter(Boolean) as typeof data,
  })).filter((g) => g.items.length > 0);

  const knownKeys = new Set(GROUPS.flatMap((g) => g.keys));
  const unknownItems = data.filter((d) => !knownKeys.has(d.name));
  if (unknownItems.length > 0) legendGroups.push({ label: "Unknown", items: unknownItems });

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

      {/* Bar ── single gradient div = pixel-perfect, zero gaps ── */}
      <div className="relative h-5 w-full rounded-full overflow-hidden">
        {/* Visual layer */}
        <div className="absolute inset-0" style={{ background: gradient }} />
        {/* Interaction overlay — transparent flex buttons on top */}
        <div className="absolute inset-0 flex">
          {data.map((d) => (
            <button
              key={d.name}
              onClick={() => handleClick(d.name)}
              title={`${d.name}: ${d.value} (${((d.value / total) * 100).toFixed(1)}%)`}
              style={{ flex: d.value }}
              className={cn(
                "h-full cursor-pointer transition-all duration-200",
                activeFilter && activeFilter !== d.name
                  ? "bg-black/55"
                  : activeFilter === d.name
                  ? "bg-white/10 ring-1 ring-white/30"
                  : "hover:bg-white/10"
              )}
            />
          ))}
        </div>
      </div>

      {/* Grouped legend */}
      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3">
        {legendGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-0.5">
            <span className="text-[8px] font-semibold uppercase tracking-widest text-text-muted mb-0.5">
              {group.label}
            </span>
            {group.items.map((d) => (
              <button
                key={d.name}
                onClick={() => handleClick(d.name)}
                className={cn(
                  "flex items-center gap-1.5 cursor-pointer transition-opacity duration-200 text-left min-w-[80px]",
                  activeFilter && activeFilter !== d.name ? "opacity-25" : "opacity-100"
                )}
              >
                <span
                  className="w-2.5 h-2.5 rounded-[3px] shrink-0"
                  style={{ backgroundColor: getColor(d.name) }}
                />
                <span className="text-[10px] font-medium text-text-secondary truncate">
                  {d.name}
                </span>
                <span className="text-[10px] font-bold text-text-primary ml-auto pl-2">
                  {d.value}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </motion.div>
  );
};
