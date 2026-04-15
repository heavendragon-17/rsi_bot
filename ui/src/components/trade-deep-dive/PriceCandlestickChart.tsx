import React from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  Customized,
} from "recharts";
import type { ChartDataPoint } from "./chart-utils";
import { dateBreakFormatter } from "./chart-utils";
import type { IndicatorConfig } from "./indicator-config";
import { DEFAULT_INDICATOR_CONFIG } from "./indicator-config";

interface PriceCandlestickChartProps {
  data: ChartDataPoint[];
  entryPrice: number;
  exitPrice: number;
  isWin: boolean;
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
// Recharts Customized component: candlestick bodies + entry/exit triangle flags
// Using Customized gives us real xAxisMap/yAxisMap scale functions + offset.
// Note: Recharts ReferenceLine does NOT support a `content` render prop in this
// version, so all SVG annotations are rendered here instead.
// ---------------------------------------------------------------------------

interface CandlestickLayerProps {
  xAxisMap?: Record<string, any>;
  yAxisMap?: Record<string, any>;
  offset?: { top: number; left: number; width: number; height: number };
  chartData?: ChartDataPoint[];
}

function CandlestickLayer({
  xAxisMap,
  yAxisMap,
  offset,
  chartData,
}: CandlestickLayerProps) {
  if (!xAxisMap || !yAxisMap || !chartData?.length) return null;

  const xAxis = Object.values(xAxisMap)[0] as any;
  const yAxis = Object.values(yAxisMap)[0] as any;
  const xScale = xAxis?.scale;
  const yScale = yAxis?.scale;
  if (!xScale || !yScale) return null;

  // Bar width from scale gap
  const barGap =
    chartData.length > 1 ? Math.abs(xScale(1) - xScale(0)) : 10;
  const barWidth = Math.max(barGap * 0.8, 3);

  // Chart plot area bounds (absolute SVG coordinates)
  const chartTop = offset?.top ?? CHART_MARGIN.top;
  const chartBottom =
    (offset?.top ?? CHART_MARGIN.top) + (offset?.height ?? 356);

  const entryIdx = chartData.findIndex((d) => d.isEntry);
  const exitIdx = chartData.findLastIndex((d) => d.isExit);

  return (
    <g>
      {/* Candlestick wicks + bodies + glow outlines */}
      {chartData.map((d, i) => {
        const cx = xScale(d.index ?? i);
        const yHigh = yScale(d.high);
        const yLow = yScale(d.low);
        const yOpen = yScale(d.open);
        const yClose = yScale(d.close);

        const isUp = d.close >= d.open;
        const color = isUp ? "#22c55e" : "#ef4444";

        const bodyTop = Math.min(yOpen, yClose);
        const bodyBottom = Math.max(yOpen, yClose);
        const bodyHeight = Math.max(bodyBottom - bodyTop, 1);
        const bodyX = cx - barWidth / 2;

        return (
          <g key={i}>
            {/* Wick */}
            <line
              x1={cx}
              y1={yHigh}
              x2={cx}
              y2={yLow}
              stroke={color}
              strokeWidth={1}
            />
            {/* Body */}
            <rect
              x={bodyX}
              y={bodyTop}
              width={barWidth}
              height={bodyHeight}
              fill={color}
              fillOpacity={isUp ? 0.8 : 1}
              stroke={color}
              strokeWidth={0.5}
            />
            {/* Entry candle glow */}
            {d.isEntry && (
              <rect
                x={bodyX - 1}
                y={bodyTop - 1}
                width={barWidth + 2}
                height={bodyHeight + 2}
                fill="none"
                stroke="#22c55e"
                strokeWidth={2}
                strokeOpacity={0.9}
                rx={1}
              />
            )}
            {/* Exit candle glow */}
            {d.isExit && (
              <rect
                x={bodyX - 1}
                y={bodyTop - 1}
                width={barWidth + 2}
                height={bodyHeight + 2}
                fill="none"
                stroke="#ef4444"
                strokeWidth={2}
                strokeOpacity={0.9}
                rx={1}
              />
            )}
          </g>
        );
      })}

      {/* Entry triangle flag at chart top */}
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

      {/* Exit triangle flag at chart bottom */}
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
// Chart component
// ---------------------------------------------------------------------------

export function PriceCandlestickChart({
  data,
  entryPrice,
  exitPrice,
  isWin,
  indicatorConfig,
}: PriceCandlestickChartProps) {
  const config = indicatorConfig ?? DEFAULT_INDICATOR_CONFIG;

  const entryIdx = data.findIndex((d) => d.isEntry);
  const exitIdx = data.findLastIndex((d) => d.isExit);
  const shadeColor = isWin ? "#22c55e" : "#ef4444";

  const domainMin = Math.min(...data.map((d) => d.low)) * 0.9995;
  const domainMax = Math.max(...data.map((d) => d.high)) * 1.0005;

  const overlayLabels = config.priceOverlays.map((o) => o.label).join(", ");

  return (
    <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
      <div className="mb-4">
        <h3 className="text-white font-bold mb-1">Price Action</h3>
        <p className="text-xs text-slate-400">
          Candlestick chart — entry/exit markers, {overlayLabels}
        </p>
      </div>
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={data} syncId="tradeDeepDive" margin={CHART_MARGIN}>
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
            domain={[domainMin, domainMax]}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            width={70}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            labelFormatter={(label: number) => data[label]?.dateLabel ?? ""}
            formatter={(value: number, name: string) => [
              `$${value?.toFixed(2)}`,
              name,
            ]}
          />

          {/* Candlesticks + triangle flags rendered by Customized (gets real scales) */}
          <Customized component={CandlestickLayer} chartData={data} />

          {/* Shaded trade region */}
          {entryIdx !== -1 && exitIdx !== -1 && (
            <ReferenceArea
              x1={entryIdx}
              x2={exitIdx}
              fill={shadeColor}
              fillOpacity={0.06}
            />
          )}

          {/* Entry price horizontal reference line */}
          <ReferenceLine
            y={entryPrice}
            stroke="#8B5CF6"
            strokeDasharray="5 5"
            strokeWidth={1.5}
            label={{
              value: `$${entryPrice.toFixed(2)}`,
              fill: "#8B5CF6",
              fontSize: 10,
              position: "insideBottomRight",
            }}
          />

          {/* Exit price horizontal reference line */}
          <ReferenceLine
            y={exitPrice}
            stroke="#06B6D4"
            strokeDasharray="5 5"
            strokeWidth={1.5}
            label={{
              value: `$${exitPrice.toFixed(2)}`,
              fill: "#06B6D4",
              fontSize: 10,
              position: "insideTopRight",
            }}
          />

          {/* Transparent bar — keeps Y-axis domain and tooltip data correct */}
          <Bar
            dataKey="close"
            fill="transparent"
            stroke="transparent"
            name="Price"
            isAnimationActive={false}
          />

          {/* EMA / price overlay lines from indicator config */}
          {config.priceOverlays.map((overlay) => (
            <Line
              key={overlay.dataKey}
              type="monotone"
              dataKey={overlay.dataKey}
              stroke={overlay.color}
              strokeWidth={1.5}
              dot={false}
              strokeDasharray="5 3"
              name={overlay.label}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
