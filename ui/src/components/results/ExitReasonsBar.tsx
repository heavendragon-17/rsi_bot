import React, { useMemo, useState } from "react";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

// ── Color map ──────────────────────────────────────────────────────────────
const COLORS: Record<string, string> = {
  TP1:                "#22c55e",
  TP2:                "#16a34a",
  TP3:                "#15803d",
  LOCK_PROFIT:        "#06b6d4",
  "TP1+SL":           "#f59e0b",
  "TP2+SL":           "#eab308",
  "TP3+SL":           "#84cc16",
  SL:                 "#ef4444",
  CLOSE_BY_CANDLE_SL: "#f97316",
  DISASTER_SL:        "#991b1b",
  TRAILING_STOP:      "#a855f7",
  EOD:                "#64748b",
  BREAKEVEN:          "#94a3b8",
  MANUAL:             "#a1a1aa",
};
const FALLBACK_PALETTE = ["#3b82f6","#8b5cf6","#ec4899","#14b8a6","#f43f5e","#0ea5e9"];
let _fi = 0;
const _dc: Record<string, string> = {};
const getColor = (name: string) => {
  if (COLORS[name]) return COLORS[name];
  if (!_dc[name]) _dc[name] = FALLBACK_PALETTE[_fi++ % FALLBACK_PALETTE.length];
  return _dc[name];
};

// ── Groups ─────────────────────────────────────────────────────────────────
const GROUPS = [
  { label: "Wins",    keys: ["TP1","TP2","TP3","LOCK_PROFIT"] },
  { label: "Partial", keys: ["TP1+SL","TP2+SL","TP3+SL"] },
  { label: "Losses",  keys: ["SL","CLOSE_BY_CANDLE_SL","DISASTER_SL"] },
  { label: "Other",   keys: ["TRAILING_STOP","EOD","BREAKEVEN","MANUAL"] },
];
const GROUP_SORT: Record<string, number> = {};
GROUPS.forEach((g, gi) => g.keys.forEach((k, ki) => { GROUP_SORT[k] = gi * 100 + ki; }));

// ── Helpers ────────────────────────────────────────────────────────────────
/** Build a CSS linear-gradient from [{name,value}] data */
const buildGradient = (
  data: { name: string; value: number }[],
  total: number,
  colorFn: (name: string) => string,
) => {
  let pos = 0;
  return `linear-gradient(to right, ${data.map((d) => {
    const pct = (d.value / total) * 100;
    const s = `${colorFn(d.name)} ${pos.toFixed(6)}% ${(pos + pct).toFixed(6)}%`;
    pos += pct;
    return s;
  }).join(", ")})`;
};

/** Given a click X ratio (0–1), return the segment name */
const segmentAtRatio = (
  ratio: number,
  data: { name: string; value: number }[],
  total: number,
) => {
  let cum = 0;
  for (const d of data) {
    cum += d.value / total;
    if (ratio <= cum) return d.name;
  }
  return data[data.length - 1]?.name ?? null;
};

// ── Component ──────────────────────────────────────────────────────────────
export const ExitReasonsBar: React.FC = () => {
  const { exitReasons, setFilter, activeFilter } = useResultsStore();
  const [tooltip, setTooltip] = useState<{ name: string; value: number; pct: string; xPct: number } | null>(null);

  const data = useMemo(() =>
    Object.entries(exitReasons)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => (GROUP_SORT[a.name] ?? 999) - (GROUP_SORT[b.name] ?? 999) || a.name.localeCompare(b.name)),
    [exitReasons],
  );

  const total = useMemo(() => data.reduce((s, d) => s + d.value, 0), [data]);

  // Visual gradient — single element, zero gaps
  const gradient = useMemo(() => buildGradient(data, total, getColor), [data, total]);

  // Dimming overlay — transparent over active segment, dark over others
  const dimmingGradient = useMemo(() => {
    if (!activeFilter) return null;
    return buildGradient(
      data,
      total,
      (name) => name === activeFilter ? "rgba(0,0,0,0)" : "rgba(0,0,0,0.55)",
    );
  }, [data, total, activeFilter]);

  const getRatio = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  };

  const handleBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const name = segmentAtRatio(getRatio(e), data, total);
    if (name) setFilter(activeFilter === name ? null : name);
  };

  const handleBarMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const ratio = getRatio(e);
    const name = segmentAtRatio(ratio, data, total);
    if (!name) { setTooltip(null); return; }
    const seg = data.find((d) => d.name === name);
    // Clamp xPct so tooltip never overflows the card edges
    const xPct = Math.min(Math.max(ratio * 100, 5), 95);
    if (seg) setTooltip({ name, value: seg.value, pct: ((seg.value / total) * 100).toFixed(1), xPct });
  };

  if (total === 0) {
    return (
      <div className="bg-bg-secondary border border-border-main rounded-xl px-3 py-2.5 text-center text-text-muted text-xs">
        No exit data
      </div>
    );
  }

  const legendGroups = GROUPS
    .map((g) => ({ label: g.label, items: g.keys.map((k) => data.find((d) => d.name === k)).filter(Boolean) as typeof data }))
    .filter((g) => g.items.length > 0);
  const knownKeys = new Set(GROUPS.flatMap((g) => g.keys));
  const unknowns = data.filter((d) => !knownKeys.has(d.name));
  if (unknowns.length) legendGroups.push({ label: "Unknown", items: unknowns });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="bg-bg-secondary border border-border-main rounded-xl px-3 py-2.5 shadow-sm"
    >
      {/* Header — right side shows hover info inline, no floating tooltip */}
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
              <X size={10} /> {activeFilter}
            </button>
          )}
        </div>
        {tooltip ? (
          <span className="text-[10px] font-medium" style={{ color: getColor(tooltip.name) }}>
            {tooltip.name}
            <span className="text-text-secondary font-normal ml-1">
              {tooltip.value} ({tooltip.pct}%)
            </span>
          </span>
        ) : (
          <span className="text-[9px] text-text-muted">{total} trades</span>
        )}
      </div>

      {/* Bar — two CSS gradient divs, zero overlay elements */}
      <div
        className="relative h-5 w-full rounded-full overflow-hidden cursor-pointer"
        onClick={handleBarClick}
        onMouseMove={handleBarMove}
        onMouseLeave={() => setTooltip(null)}
      >
        <div className="absolute inset-0 rounded-full" style={{ background: gradient }} />
        {dimmingGradient && (
          <div className="absolute inset-0 rounded-full transition-all" style={{ background: dimmingGradient }} />
        )}
      </div>

      {/* Grouped legend — each group in its own card */}
      <div className="flex flex-wrap gap-2 mt-3">
        {legendGroups.map((group) => (
          <div
            key={group.label}
            className="flex flex-col gap-0.5 bg-bg-primary/50 border border-border-main/40 rounded-lg px-2.5 py-2"
          >
            <span className="text-[8px] font-bold uppercase tracking-widest text-text-muted mb-1 border-b border-border-main/30 pb-1">
              {group.label}
            </span>
            {group.items.map((d) => (
              <button
                key={d.name}
                onClick={() => setFilter(activeFilter === d.name ? null : d.name)}
                className={cn(
                  "flex items-center gap-1.5 cursor-pointer transition-opacity duration-200 text-left",
                  activeFilter && activeFilter !== d.name ? "opacity-25" : "opacity-100",
                )}
              >
                <span className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ backgroundColor: getColor(d.name) }} />
                <span className="text-[10px] font-medium text-text-secondary">{d.name}</span>
                <span className="text-[10px] font-bold text-text-primary ml-auto pl-3">{d.value}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </motion.div>
  );
};
