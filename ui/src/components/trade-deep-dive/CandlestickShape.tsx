import React from "react";

interface CandlestickShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: {
    open: number;
    high: number;
    low: number;
    close: number;
  };
  yAxis?: {
    scale?: (value: number) => number;
  };
}

const BULL_COLOR = "#22c55e";
const BEAR_COLOR = "#ef4444";

/**
 * Custom Recharts Bar shape that renders a proper OHLC candlestick.
 * The Bar's dataKey is "close" (used only to feed Recharts' axis domain).
 * We ignore x/y/height from Recharts and compute our own pixel positions
 * using the yAxis scale function.
 */
export function CandlestickShape(props: CandlestickShapeProps) {
  const { x, width, payload, yAxis } = props;

  if (!payload || !yAxis?.scale || x === undefined || width === undefined) {
    return null;
  }

  const { open, high, low, close } = payload;
  const scale = yAxis.scale;

  const isUp = close >= open;
  const color = isUp ? BULL_COLOR : BEAR_COLOR;

  const yHigh = scale(high);
  const yLow = scale(low);
  const yOpen = scale(open);
  const yClose = scale(close);

  const bodyTop = Math.min(yOpen, yClose);
  const bodyBottom = Math.max(yOpen, yClose);
  const bodyHeight = Math.max(bodyBottom - bodyTop, 1);

  const wickX = x + width / 2;

  return (
    <g>
      {/* Wick */}
      <line
        x1={wickX}
        y1={yHigh}
        x2={wickX}
        y2={yLow}
        stroke={color}
        strokeWidth={1}
      />
      {/* Body */}
      <rect
        x={x + 1}
        y={bodyTop}
        width={Math.max(width - 2, 1)}
        height={bodyHeight}
        fill={color}
        fillOpacity={isUp ? 0.8 : 1}
        stroke={color}
        strokeWidth={0.5}
      />
    </g>
  );
}
