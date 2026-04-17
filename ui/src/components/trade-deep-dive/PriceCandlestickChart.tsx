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
  ReferenceArea,
  Customized,
} from "recharts";
import type { ChartDataPoint } from "./chart-utils";
import { dateBreakFormatter, formatPrice } from "./chart-utils";
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
  entryPrice?: number;
  exitPrice?: number;
}

function CandlestickLayer({
  xAxisMap,
  yAxisMap,
  offset,
  chartData,
  entryPrice,
  exitPrice,
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

      {/* Short price reference segments — only span the trade window so the
          horizontal lines no longer stretch across the full chart. */}
      {entryIdx !== -1 && exitIdx !== -1 && entryPrice !== undefined && (() => {
        const x1 = xScale(entryIdx);
        const x2 = xScale(exitIdx);
        const yEntry = yScale(entryPrice);
        return (
          <g key="entry-price-segment">
            <line
              x1={x1}
              x2={x2}
              y1={yEntry}
              y2={yEntry}
              stroke="#8B5CF6"
              strokeWidth={1}
              strokeDasharray="4 4"
              opacity={0.55}
            />
            <text
              x={x2 + 4}
              y={yEntry + 3}
              fill="#8B5CF6"
              fontSize={9}
              fontFamily="monospace"
              opacity={0.85}
            >
              {formatPrice(entryPrice)}
            </text>
          </g>
        );
      })()}

      {entryIdx !== -1 && exitIdx !== -1 && exitPrice !== undefined && (() => {
        const x1 = xScale(entryIdx);
        const x2 = xScale(exitIdx);
        const yExit = yScale(exitPrice);
        return (
          <g key="exit-price-segment">
            <line
              x1={x1}
              x2={x2}
              y1={yExit}
              y2={yExit}
              stroke="#06B6D4"
              strokeWidth={1}
              strokeDasharray="4 4"
              opacity={0.55}
            />
            <text
              x={x2 + 4}
              y={yExit + 3}
              fill="#06B6D4"
              fontSize={9}
              fontFamily="monospace"
              opacity={0.85}
            >
              {formatPrice(exitPrice)}
            </text>
          </g>
        );
      })()}

      {/* Entry triangle above the entry candle high */}
      {entryIdx !== -1 && (() => {
        const cx = xScale(entryIdx);
        const yHigh = yScale(chartData[entryIdx].high);
        const size = 7;
        const spacing = 5; // px gap between triangle tip and candle high
        const tipY = yHigh - spacing;
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

      {/* Exit triangle below the exit candle low */}
      {exitIdx !== -1 && (() => {
        const cx = xScale(exitIdx);
        const yLow = yScale(chartData[exitIdx].low);
        const size = 7;
        const spacing = 5; // px gap between triangle tip and candle low
        const tipY = yLow + spacing;
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

  // Dynamic Y-axis width: enough room for the longest formatted price label
  const yAxisWidth = Math.max(70, formatPrice(domainMax).length * 7 + 8);

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
            domain={[domainMin, domainMax]}
            tickFormatter={(v: number) => formatPrice(v)}
            width={yAxisWidth}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            labelFormatter={(label: number) => data[label]?.dateLabel ?? ""}
            formatter={(value: number, name: string) => [
              formatPrice(value),
              name,
            ]}
          />

          {/* Candlesticks, triangle flags, and short entry/exit price
              segments — all rendered inside Customized so they share the
              real xAxis/yAxis scales. */}
          <Customized
            component={CandlestickLayer}
            chartData={data}
            entryPrice={entryPrice}
            exitPrice={exitPrice}
          />

          {/* Shaded trade region */}
          {entryIdx !== -1 && exitIdx !== -1 && (
            <ReferenceArea
              x1={entryIdx}
              x2={exitIdx}
              fill={shadeColor}
              fillOpacity={0.06}
            />
          )}

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
