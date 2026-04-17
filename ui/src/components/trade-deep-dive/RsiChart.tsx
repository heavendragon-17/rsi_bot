import React from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Customized,
} from "recharts";
import type { ChartDataPoint } from "./chart-utils";
import { dateBreakFormatter } from "./chart-utils";
import type { IndicatorConfig } from "./indicator-config";
import { DEFAULT_INDICATOR_CONFIG } from "./indicator-config";

interface RsiChartProps {
  data: ChartDataPoint[];
  indicatorConfig?: IndicatorConfig;
}

const CHART_MARGIN = { top: 24, right: 20, bottom: 20, left: 0 };

// Colors picked for maximum hue separation on a dark slate background.
// Using three widely-spaced hues (warm yellow, cool blue, warm pink) so that
// even users with red-green colorblindness can tell the series apart.
const COLOR_RSI = "#FBBF24";   // amber-400  — the primary signal
const COLOR_EMA9 = "#38BDF8";  // sky-400    — fast moving average
const COLOR_WMA45 = "#F472B6"; // pink-400   — slow moving average (dashed)

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

// ---------------------------------------------------------------------------
// Triangle flags via Customized — Recharts does not support a `content` render
// prop on ReferenceLine in this version, so we render annotations here.
// ---------------------------------------------------------------------------

interface TriangleLayerProps {
  xAxisMap?: Record<string, any>;
  yAxisMap?: Record<string, any>;
  offset?: { top: number; left: number; width: number; height: number };
  chartData?: ChartDataPoint[];
}

function TriangleLayer({ xAxisMap, yAxisMap, chartData }: TriangleLayerProps) {
  if (!xAxisMap || !yAxisMap || !chartData?.length) return null;

  const xAxis = Object.values(xAxisMap)[0] as any;
  const yAxis = Object.values(yAxisMap)[0] as any;
  const xScale = xAxis?.scale;
  const yScale = yAxis?.scale;
  if (!xScale || !yScale) return null;

  const entryIdx = chartData.findIndex((d) => d.isEntry);
  const exitIdx = chartData.findLastIndex((d) => d.isExit);

  return (
    <g>
      {entryIdx !== -1 && (() => {
        const rsiVal = chartData[entryIdx].rsi;
        if (rsiVal === null) return null;
        const cx = xScale(entryIdx);
        const yRsi = yScale(rsiVal);
        const size = 7;
        const spacing = 5;
        const tipY = yRsi - spacing;
        const baseY = tipY - size;
        const pts = `${cx},${tipY} ${cx - size},${baseY} ${cx + size},${baseY}`;
        return (
          <g key="entry-flag">
            <polygon points={pts} fill="#22c55e" opacity={0.9} />
            <text
              x={cx}
              y={baseY - 2}
              textAnchor="middle"
              dominantBaseline="auto"
              fill="#22c55e"
              fontSize={9}
              fontFamily="monospace"
            >
              Entry
            </text>
          </g>
        );
      })()}

      {exitIdx !== -1 && (() => {
        const rsiVal = chartData[exitIdx].rsi;
        if (rsiVal === null) return null;
        const cx = xScale(exitIdx);
        const yRsi = yScale(rsiVal);
        const size = 7;
        const spacing = 5;
        const tipY = yRsi + spacing;
        const baseY = tipY + size;
        const pts = `${cx},${tipY} ${cx - size},${baseY} ${cx + size},${baseY}`;
        return (
          <g key="exit-flag">
            <polygon points={pts} fill="#ef4444" opacity={0.9} />
            <text
              x={cx}
              y={baseY + 9}
              textAnchor="middle"
              dominantBaseline="auto"
              fill="#ef4444"
              fontSize={9}
              fontFamily="monospace"
            >
              Exit
            </text>
          </g>
        );
      })()}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip (includes spread and above_ema21)
// ---------------------------------------------------------------------------

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
          {entry.name}:{" "}
          {typeof entry.value === "number"
            ? entry.value.toFixed(2)
            : String(entry.value)}
        </p>
      ))}
      {point.spread !== null && (
        <p style={{ ...TOOLTIP_ITEM_STYLE, color: "#a78bfa" }}>
          Spread:{" "}
          {(point.spread ?? 0) > 0 ? "+" : ""}
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

// ---------------------------------------------------------------------------
// Legend swatch — tiny colored bar + label, mirrors the line style on the chart
// ---------------------------------------------------------------------------

function LegendItem({
  color,
  label,
  thick,
  dashed,
}: {
  color: string;
  label: string;
  thick?: boolean;
  dashed?: boolean;
}) {
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap">
      <svg width={16} height={8} aria-hidden>
        <line
          x1={0}
          y1={4}
          x2={16}
          y2={4}
          stroke={color}
          strokeWidth={thick ? 2.5 : 1.5}
          strokeDasharray={dashed ? "4 2" : undefined}
          strokeLinecap="round"
        />
      </svg>
      <span style={{ color }}>{label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Chart component
// ---------------------------------------------------------------------------

export function RsiChart({ data, indicatorConfig }: RsiChartProps) {
  const config = (indicatorConfig ?? DEFAULT_INDICATOR_CONFIG).oscillator;

  return (
    <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-white font-bold mb-1">RSI(21)</h3>
          <p className="text-xs text-slate-400">
            OB/OS 70/30. Hover for Spread &amp; EMA21 status.
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono pt-1 shrink-0">
          <LegendItem color={COLOR_RSI} label="RSI(21)" thick />
          <LegendItem color={COLOR_EMA9} label="EMA9" />
          <LegendItem color={COLOR_WMA45} label="WMA45" dashed />
        </div>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={data} syncId="tradeDeepDive" margin={CHART_MARGIN}>
          <defs>
            <linearGradient id="rsiGradientDive" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLOR_RSI} stopOpacity={0.22} />
              <stop offset="100%" stopColor={COLOR_RSI} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
          <XAxis
            type="number"
            dataKey="index"
            domain={[-0.5, data.length - 0.5]}
            stroke="#64748b"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickFormatter={(value: number) => dateBreakFormatter(data, value)}
          />
          <YAxis
            stroke="#64748b"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            domain={[0, 100]}
            width={35}
          />
          <Tooltip content={<CustomTooltip data={data} />} />

          {/* OB/OS reference lines */}
          <ReferenceLine
            y={config.obLevel}
            stroke="#F43F5E"
            strokeDasharray="3 3"
            strokeOpacity={0.5}
          />
          <ReferenceLine
            y={config.osLevel}
            stroke="#10B981"
            strokeDasharray="3 3"
            strokeOpacity={0.5}
          />

          {/* Entry/exit triangle flags via Customized */}
          <Customized component={TriangleLayer} chartData={data} />

          {/* RSI area — primary signal, drawn first so the MAs sit on top */}
          <Area
            type="monotone"
            dataKey={config.rsiDataKey}
            stroke={COLOR_RSI}
            strokeWidth={2}
            fill="url(#rsiGradientDive)"
            name="RSI(21)"
            connectNulls
            isAnimationActive={false}
          />

          {/* WMA45 of RSI — slow MA, dashed so it's clearly the "other" MA */}
          <Line
            type="monotone"
            dataKey={config.wma45DataKey}
            stroke={COLOR_WMA45}
            strokeWidth={1.25}
            strokeDasharray="5 3"
            dot={false}
            name="WMA45"
            connectNulls
            isAnimationActive={false}
          />

          {/* EMA9 of RSI — fast MA, solid thin line */}
          <Line
            type="monotone"
            dataKey={config.ema9DataKey}
            stroke={COLOR_EMA9}
            strokeWidth={1.25}
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
