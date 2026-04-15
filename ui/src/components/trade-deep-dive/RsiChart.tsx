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
  offset?: { top: number; left: number; width: number; height: number };
  chartData?: ChartDataPoint[];
}

function TriangleLayer({ xAxisMap, offset, chartData }: TriangleLayerProps) {
  if (!xAxisMap || !chartData?.length) return null;

  const xAxis = Object.values(xAxisMap)[0] as any;
  const xScale = xAxis?.scale;
  if (!xScale) return null;

  const chartTop = offset?.top ?? CHART_MARGIN.top;
  const chartBottom =
    (offset?.top ?? CHART_MARGIN.top) + (offset?.height ?? 206);

  const entryIdx = chartData.findIndex((d) => d.isEntry);
  const exitIdx = chartData.findLastIndex((d) => d.isExit);

  return (
    <g>
      {entryIdx !== -1 && (() => {
        const cx = xScale(entryIdx);
        const top = chartTop;
        const size = 7;
        const tipY = top + size + 4;
        const pts = `${cx},${tipY} ${cx - size},${top + 4} ${cx + size},${top + 4}`;
        return (
          <g key="entry-flag">
            <polygon points={pts} fill="#22c55e" opacity={0.9} />
            <text
              x={cx}
              y={top + 1}
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
        const cx = xScale(exitIdx);
        const bottom = chartBottom;
        const size = 7;
        const tipY = bottom - size - 4;
        const pts = `${cx},${tipY} ${cx - size},${bottom - 4} ${cx + size},${bottom - 4}`;
        return (
          <g key="exit-flag">
            <polygon points={pts} fill="#ef4444" opacity={0.9} />
            <text
              x={cx}
              y={bottom}
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
// Chart component
// ---------------------------------------------------------------------------

export function RsiChart({ data, indicatorConfig }: RsiChartProps) {
  const config = (indicatorConfig ?? DEFAULT_INDICATOR_CONFIG).oscillator;

  return (
    <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
      <div className="mb-4">
        <h3 className="text-white font-bold mb-1">RSI(21)</h3>
        <p className="text-xs text-slate-400">
          RSI(21), EMA9, WMA45 — OB/OS 70/30. Hover for Spread &amp; EMA21 status.
        </p>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={data} syncId="tradeDeepDive" margin={CHART_MARGIN}>
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

          {/* RSI area */}
          <Area
            type="monotone"
            dataKey={config.rsiDataKey}
            stroke="#06B6D4"
            strokeWidth={2}
            fill="url(#rsiGradientDive)"
            name="RSI"
            connectNulls
            isAnimationActive={false}
          />

          {/* WMA45 of RSI */}
          <Line
            type="monotone"
            dataKey={config.wma45DataKey}
            stroke="#8B5CF6"
            strokeWidth={1.5}
            dot={false}
            name="WMA45"
            connectNulls
            isAnimationActive={false}
          />

          {/* EMA9 of RSI */}
          <Line
            type="monotone"
            dataKey={config.ema9DataKey}
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
