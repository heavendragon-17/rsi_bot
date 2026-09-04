import React, { useState } from "react";
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
// OHLC hover bar — shown above the chart, updates as the user moves the mouse
// ---------------------------------------------------------------------------

function OhlcBar({ candle }: { candle: ChartDataPoint | null }) {
  if (!candle) return <div className="h-4" />;
  const change = candle.close - candle.open;
  const changePct = (change / candle.open) * 100;
  const isUp = change >= 0;
  const changeColor = isUp ? "#15803D" : "#B91C1C";
  const sign = isUp ? "+" : "";

  return (
    <div className="flex items-center gap-3 text-[11px] font-mono leading-none">
      <span style={{ color: "#78716C" }}>
        O <span style={{ color: "#1C1917" }}>{formatPrice(candle.open, false)}</span>
      </span>
      <span style={{ color: "#78716C" }}>
        H <span style={{ color: "#1C1917" }}>{formatPrice(candle.high, false)}</span>
      </span>
      <span style={{ color: "#78716C" }}>
        L <span style={{ color: "#1C1917" }}>{formatPrice(candle.low, false)}</span>
      </span>
      <span style={{ color: "#78716C" }}>
        C <span style={{ color: "#1C1917" }}>{formatPrice(candle.close, false)}</span>
      </span>
      <span style={{ color: changeColor }}>
        {sign}{formatPrice(Math.abs(change), false)}&nbsp;
        ({sign}{changePct.toFixed(2)}%)
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recharts Customized component: candlestick bodies + entry/exit triangles
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
  chartData,
}: CandlestickLayerProps) {
  if (!xAxisMap || !yAxisMap || !chartData?.length) return null;

  const xAxis = Object.values(xAxisMap)[0] as any;
  const yAxis = Object.values(yAxisMap)[0] as any;
  const xScale = xAxis?.scale;
  const yScale = yAxis?.scale;
  if (!xScale || !yScale) return null;

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
        const color = isUp ? "#16A34A" : "#DC2626";

        const bodyTop = Math.min(yOpen, yClose);
        const bodyBottom = Math.max(yOpen, yClose);
        const bodyHeight = Math.max(bodyBottom - bodyTop, 1);
        const bodyX = cx - barWidth / 2;

        return (
          <g key={i}>
            <line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={color} strokeWidth={1} />
            <rect
              x={bodyX} y={bodyTop}
              width={barWidth} height={bodyHeight}
              fill={color} fillOpacity={isUp ? 0.8 : 1}
              stroke={color} strokeWidth={0.5}
            />
            {d.isEntry && (
              <rect
                x={bodyX - 1} y={bodyTop - 1}
                width={barWidth + 2} height={bodyHeight + 2}
                fill="none" stroke="#16A34A" strokeWidth={2} strokeOpacity={0.9} rx={1}
              />
            )}
            {d.isExit && (
              <rect
                x={bodyX - 1} y={bodyTop - 1}
                width={barWidth + 2} height={bodyHeight + 2}
                fill="none" stroke="#DC2626" strokeWidth={2} strokeOpacity={0.9} rx={1}
              />
            )}
          </g>
        );
      })}

      {/* Entry triangle ▼ above entry candle high */}
      {entryIdx !== -1 && (() => {
        const cx = xScale(entryIdx);
        const yHigh = yScale(chartData[entryIdx].high);
        const size = 7;
        const tipY = yHigh - 5;
        const baseY = tipY - size;
        return (
          <g key="entry-flag">
            <polygon
              points={`${cx},${tipY} ${cx - size},${baseY} ${cx + size},${baseY}`}
              fill="#16A34A" opacity={0.9}
            />
            <text x={cx} y={baseY - 2} textAnchor="middle" dominantBaseline="auto"
              fill="#16A34A" fontSize={9} fontFamily="monospace">
              Entry
            </text>
          </g>
        );
      })()}

      {/* Exit triangle ▲ below exit candle low */}
      {exitIdx !== -1 && (() => {
        const cx = xScale(exitIdx);
        const yLow = yScale(chartData[exitIdx].low);
        const size = 7;
        const tipY = yLow + 5;
        const baseY = tipY + size;
        return (
          <g key="exit-flag">
            <polygon
              points={`${cx},${tipY} ${cx - size},${baseY} ${cx + size},${baseY}`}
              fill="#DC2626" opacity={0.9}
            />
            <text x={cx} y={baseY + 9} textAnchor="middle" dominantBaseline="auto"
              fill="#DC2626" fontSize={9} fontFamily="monospace">
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
  entryPrice: _entryPrice,
  exitPrice: _exitPrice,
  isWin,
  indicatorConfig,
}: PriceCandlestickChartProps) {
  const config = indicatorConfig ?? DEFAULT_INDICATOR_CONFIG;
  const [hoveredCandle, setHoveredCandle] = useState<ChartDataPoint | null>(null);

  const entryIdx = data.findIndex((d) => d.isEntry);
  const exitIdx = data.findLastIndex((d) => d.isExit);
  const shadeColor = isWin ? "#16A34A" : "#DC2626";

  const domainMin = Math.min(...data.map((d) => d.low)) * 0.9995;
  const domainMax = Math.max(...data.map((d) => d.high)) * 1.0005;
  const yAxisWidth = Math.max(70, formatPrice(domainMax).length * 7 + 8);

  const overlayLabels = config.priceOverlays.map((o) => o.label).join(", ");

  // Default OHLC display: entry candle while not hovering
  const defaultCandle = data[entryIdx] ?? data[data.length - 1] ?? null;
  const displayCandle = hoveredCandle ?? defaultCandle;

  const handleMouseMove = (state: any) => {
    const idx = state?.activeLabel;
    if (idx == null) return;
    const candle = data[Math.round(Number(idx))];
    if (candle) setHoveredCandle(candle);
  };

  return (
    <div className="rounded-xl p-6 border" style={{ backgroundColor: "#E7E2C6", borderColor: "#C9C3A3" }}>
      <div className="mb-3">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
          <h3 className="font-bold" style={{ color: "#1C1917" }}>Price Action</h3>
          <OhlcBar candle={displayCandle} />
        </div>
        <p className="text-xs" style={{ color: "#57534E" }}>
          Candlestick chart — entry/exit markers, {overlayLabels}
        </p>
      </div>
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={data}
          syncId="tradeDeepDive"
          margin={CHART_MARGIN}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredCandle(null)}
        >
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
            domain={[domainMin, domainMax]}
            tickFormatter={(v: number) => formatPrice(v)}
            width={yAxisWidth}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            labelFormatter={(label: number) =>
              data[Math.round(label)]?.dateLabel ?? ""
            }
            formatter={(value: number, name: string) => [formatPrice(value), name]}
          />

          <Customized component={CandlestickLayer} chartData={data} />

          {entryIdx !== -1 && exitIdx !== -1 && (
            <ReferenceArea
              x1={entryIdx} x2={exitIdx}
              fill={shadeColor} fillOpacity={0.06}
            />
          )}

          <Bar
            dataKey="close"
            fill="transparent" stroke="transparent"
            name="Price"
            isAnimationActive={false}
          />

          {config.priceOverlays.map((overlay) => (
            <Line
              key={overlay.dataKey}
              type="monotone"
              dataKey={overlay.dataKey}
              stroke={overlay.color}
              strokeWidth={2}
              dot={false}
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
