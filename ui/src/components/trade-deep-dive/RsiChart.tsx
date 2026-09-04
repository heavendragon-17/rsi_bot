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

// Colors match the signal-review chart: black RSI, green EMA9, red WMA45
// on a beige background (same palette as the reference TradingView theme).
const COLOR_RSI = "#000000";   // black      — the primary signal
const COLOR_EMA9 = "#16A34A";  // green-600  — fast moving average
const COLOR_WMA45 = "#DC2626"; // red-600    — slow moving average

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(231, 226, 198, 0.97)",
  border: "1px solid rgba(120, 113, 86, 0.5)",
  borderRadius: "8px",
  padding: "12px",
};

const TOOLTIP_LABEL_STYLE = { color: "#57534E", fontSize: "12px" };
const TOOLTIP_ITEM_STYLE = {
  color: "#1C1917",
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
            <polygon points={pts} fill="#16A34A" opacity={0.9} />
            <text
              x={cx}
              y={baseY - 2}
              textAnchor="middle"
              dominantBaseline="auto"
              fill="#16A34A"
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
            <polygon points={pts} fill="#DC2626" opacity={0.9} />
            <text
              x={cx}
              y={baseY + 9}
              textAnchor="middle"
              dominantBaseline="auto"
              fill="#DC2626"
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
        <p style={{ ...TOOLTIP_ITEM_STYLE, color: "#57534E" }}>
          Spread:{" "}
          {(point.spread ?? 0) > 0 ? "+" : ""}
          {(point.spread ?? 0).toFixed(2)}
        </p>
      )}
      {point.above_ema21 !== null && (
        <p style={{ ...TOOLTIP_ITEM_STYLE, color: "#16A34A" }}>
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
    <div className="rounded-xl p-6 border" style={{ backgroundColor: "#E7E2C6", borderColor: "#C9C3A3" }}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-bold mb-1" style={{ color: "#1C1917" }}>RSI(21)</h3>
          <p className="text-xs" style={{ color: "#57534E" }}>
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
              <stop offset="0%" stopColor={COLOR_RSI} stopOpacity={0.15} />
              <stop offset="100%" stopColor={COLOR_RSI} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#C4BE9E" opacity={0.6} />
          <XAxis
            type="number"
            dataKey="index"
            domain={[-0.5, data.length - 0.5]}
            stroke="#78716C"
            tick={{ fill: "#57534E", fontSize: 10 }}
            tickFormatter={(value: number) => dateBreakFormatter(data, value)}
          />
          <YAxis
            stroke="#78716C"
            tick={{ fill: "#57534E", fontSize: 11 }}
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

          {/* WMA45 of RSI — slow MA */}
          <Line
            type="monotone"
            dataKey={config.wma45DataKey}
            stroke={COLOR_WMA45}
            strokeWidth={2}
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
            strokeWidth={2}
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
