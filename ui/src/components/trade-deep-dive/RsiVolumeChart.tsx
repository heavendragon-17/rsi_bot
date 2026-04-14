import React from "react";
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { ChartDataPoint } from "./chart-utils";
import { dateBreakFormatter } from "./chart-utils";

interface RsiVolumeChartProps {
  data: ChartDataPoint[];
}

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(15, 23, 42, 0.95)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  borderRadius: "8px",
  padding: "12px",
};

const TOOLTIP_LABEL_STYLE = { color: "#94a3b8", fontSize: "12px" };
const TOOLTIP_ITEM_STYLE = {
  color: "#e2e8f0",
  fontSize: "12px",
  fontFamily: "monospace",
};

interface TooltipPayloadEntry {
  name: string;
  value: number | boolean | null;
  color?: string;
}

function CustomTooltip({
  active,
  payload,
  label,
  data,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: number;
  data: ChartDataPoint[];
}) {
  if (!active || !payload?.length) return null;
  const point = data[label ?? 0];
  if (!point) return null;

  return (
    <div style={TOOLTIP_STYLE}>
      <p style={TOOLTIP_LABEL_STYLE} className="mb-1">
        {point.dateLabel}
      </p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ ...TOOLTIP_ITEM_STYLE, color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(2) : String(entry.value)}
        </p>
      ))}
      {point.spread !== null && (
        <p style={{ ...TOOLTIP_ITEM_STYLE, color: "#a78bfa" }}>
          Spread: {(point.spread ?? 0) > 0 ? "+" : ""}
          {(point.spread ?? 0).toFixed(2)}
        </p>
      )}
      {point.above_ema21 !== null && (
        <p style={{ ...TOOLTIP_ITEM_STYLE, color: "#fbbf24" }}>
          Above EMA21: {point.above_ema21 ? "Yes" : "No"}
        </p>
      )}
    </div>
  );
}

export function RsiVolumeChart({ data }: RsiVolumeChartProps) {
  const entryIdx = data.findIndex((d) => d.isEntry);
  const exitIdx = data.findLastIndex((d) => d.isExit);

  return (
    <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
      <div className="mb-4">
        <h3 className="text-white font-bold mb-1">RSI + Volume</h3>
        <p className="text-xs text-slate-400">
          RSI (14), EMA9, WMA45 — Volume on right axis. Hover for Spread &amp; EMA21 status.
        </p>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={data} syncId="tradeDeepDive">
          <defs>
            <linearGradient id="rsiGradientDive" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06B6D4" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#06B6D4" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
          <XAxis
            dataKey="index"
            stroke="#64748b"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickFormatter={(value: number) => dateBreakFormatter(data, value)}
          />
          {/* Left axis: RSI 0-100 */}
          <YAxis
            yAxisId="rsi"
            stroke="#64748b"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            domain={[0, 100]}
            width={35}
          />
          {/* Right axis: Volume (auto-scaled) */}
          <YAxis
            yAxisId="volume"
            orientation="right"
            stroke="#64748b"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickFormatter={(v: number) =>
              v >= 1_000_000
                ? `${(v / 1_000_000).toFixed(1)}M`
                : v >= 1_000
                ? `${(v / 1_000).toFixed(0)}K`
                : String(v)
            }
            width={45}
          />
          <Tooltip
            content={<CustomTooltip data={data} />}
          />

          {/* Overbought/Oversold reference lines */}
          <ReferenceLine
            yAxisId="rsi"
            y={70}
            stroke="#F43F5E"
            strokeDasharray="3 3"
            strokeOpacity={0.5}
          />
          <ReferenceLine
            yAxisId="rsi"
            y={30}
            stroke="#10B981"
            strokeDasharray="3 3"
            strokeOpacity={0.5}
          />

          {/* Entry vertical line */}
          {entryIdx !== -1 && (
            <ReferenceLine
              yAxisId="rsi"
              x={entryIdx}
              stroke="#22c55e"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
          )}

          {/* Exit vertical line */}
          {exitIdx !== -1 && (
            <ReferenceLine
              yAxisId="rsi"
              x={exitIdx}
              stroke="#ef4444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
          )}

          {/* Volume bars (right axis, behind RSI) */}
          <Bar
            yAxisId="volume"
            dataKey="volume"
            fill="#475569"
            fillOpacity={0.3}
            radius={[2, 2, 0, 0]}
            name="Volume"
            isAnimationActive={false}
          />

          {/* RSI area */}
          <Area
            yAxisId="rsi"
            type="monotone"
            dataKey="rsi"
            stroke="#06B6D4"
            strokeWidth={2}
            fill="url(#rsiGradientDive)"
            name="RSI"
            connectNulls
            isAnimationActive={false}
          />

          {/* WMA45 of RSI */}
          <Line
            yAxisId="rsi"
            type="monotone"
            dataKey="wma45"
            stroke="#8B5CF6"
            strokeWidth={1.5}
            dot={false}
            name="WMA45"
            connectNulls
            isAnimationActive={false}
          />

          {/* EMA9 of RSI */}
          <Line
            yAxisId="rsi"
            type="monotone"
            dataKey="ema9"
            stroke="#34D399"
            strokeWidth={1.5}
            dot={false}
            name="EMA9"
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
