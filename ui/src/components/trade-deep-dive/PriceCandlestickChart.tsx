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
} from "recharts";
import type { ChartDataPoint } from "./chart-utils";
import { dateBreakFormatter } from "./chart-utils";
import { CandlestickShape } from "./CandlestickShape";

interface PriceCandlestickChartProps {
  data: ChartDataPoint[];
  entryPrice: number;
  exitPrice: number;
  isWin: boolean;
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

export function PriceCandlestickChart({
  data,
  entryPrice,
  exitPrice,
  isWin,
}: PriceCandlestickChartProps) {
  const entryIdx = data.findIndex((d) => d.isEntry);
  const exitIdx = data.findLastIndex((d) => d.isExit);
  const shadeColor = isWin ? "#22c55e" : "#ef4444";

  const domainMin = Math.min(...data.map((d) => d.low)) * 0.9995;
  const domainMax = Math.max(...data.map((d) => d.high)) * 1.0005;

  return (
    <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
      <div className="mb-4">
        <h3 className="text-white font-bold mb-1">Price Action</h3>
        <p className="text-xs text-slate-400">
          Candlestick chart — entry/exit markers, EMA21, trailing SL
        </p>
      </div>
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={data} syncId="tradeDeepDive">
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

          {/* Shaded trade region */}
          {entryIdx !== -1 && exitIdx !== -1 && (
            <ReferenceArea
              x1={entryIdx}
              x2={exitIdx}
              fill={shadeColor}
              fillOpacity={0.06}
            />
          )}

          {/* Entry price horizontal line */}
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

          {/* Exit price horizontal line */}
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

          {/* Entry vertical line */}
          {entryIdx !== -1 && (
            <ReferenceLine
              x={entryIdx}
              stroke="#22c55e"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: "Entry",
                fill: "#22c55e",
                fontSize: 10,
                position: "top",
              }}
            />
          )}

          {/* Exit vertical line */}
          {exitIdx !== -1 && (
            <ReferenceLine
              x={exitIdx}
              stroke="#ef4444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: "Exit",
                fill: "#ef4444",
                fontSize: 10,
                position: "top",
              }}
            />
          )}

          {/* Candlestick bars — custom shape draws OHLC */}
          <Bar
            dataKey="close"
            shape={<CandlestickShape />}
            fill="transparent"
            name="Price"
            isAnimationActive={false}
          />

          {/* EMA21 price overlay */}
          <Line
            type="monotone"
            dataKey="ema21"
            stroke="#F59E0B"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="5 3"
            name="EMA21"
            connectNulls
          />

          {/* Trailing SL */}
          <Line
            type="stepAfter"
            dataKey="active_sl"
            stroke="#94a3b8"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="3 3"
            name="Trailing SL"
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
