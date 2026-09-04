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
    isEntry?: boolean;
    isExit?: boolean;
  };
  yAxis?: {
    scale?: (value: number) => number;
  };
}

const BULL_COLOR = "#16A34A";
const BEAR_COLOR = "#DC2626";
const ENTRY_GLOW = "#16A34A";
const EXIT_GLOW = "#DC2626";

/**
 * Custom Recharts Bar shape that renders a proper OHLC candlestick.
 * Entry and exit candles get a colored glow outline around the body.
 */
export function CandlestickShape(props: CandlestickShapeProps) {
  const { x, width, payload, yAxis } = props;

  if (!payload || !yAxis?.scale || x === undefined || width === undefined) {
    return null;
  }

  const { open, high, low, close, isEntry, isExit } = payload;
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
  const bodyX = x + 1;
  const bodyW = Math.max(width - 2, 1);

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
        x={bodyX}
        y={bodyTop}
        width={bodyW}
        height={bodyHeight}
        fill={color}
        fillOpacity={isUp ? 0.8 : 1}
        stroke={color}
        strokeWidth={0.5}
      />
      {/* Entry glow outline */}
      {isEntry && (
        <rect
          x={x}
          y={bodyTop - 1}
          width={Math.max(width, 1)}
          height={bodyHeight + 2}
          fill="none"
          stroke={ENTRY_GLOW}
          strokeWidth={2}
          strokeOpacity={0.85}
          rx={1}
        />
      )}
      {/* Exit glow outline */}
      {isExit && (
        <rect
          x={x}
          y={bodyTop - 1}
          width={Math.max(width, 1)}
          height={bodyHeight + 2}
          fill="none"
          stroke={EXIT_GLOW}
          strokeWidth={2}
          strokeOpacity={0.85}
          rx={1}
        />
      )}
    </g>
  );
}
