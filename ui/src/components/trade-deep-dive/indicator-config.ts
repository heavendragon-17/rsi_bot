/**
 * Indicator module configuration system.
 *
 * Each strategy defines an IndicatorConfig that controls which overlays are
 * rendered on the price chart and which oscillator is shown in the second chart.
 * Charts consume this config at render time, so adding a new indicator for a
 * future strategy requires no changes to chart components.
 */

// ---------------------------------------------------------------------------
// Price chart overlays
// ---------------------------------------------------------------------------

export interface EmaOverlayConfig {
  type: "ema";
  dataKey: "ema21" | "ema200";
  color: string;
  label: string;
}

// Discriminated union — add "bollinger" | "vwap" | "sma" members here later.
export type PriceOverlayConfig = EmaOverlayConfig;

// ---------------------------------------------------------------------------
// Oscillator chart
// ---------------------------------------------------------------------------

export interface RsiOscillatorConfig {
  type: "rsi";
  rsiDataKey: "rsi";
  ema9DataKey: "ema9";
  wma45DataKey: "wma45";
  obLevel: number;
  osLevel: number;
}

// Discriminated union — add "macd" | "stoch" members here later.
export type OscillatorConfig = RsiOscillatorConfig;

// ---------------------------------------------------------------------------
// Top-level config
// ---------------------------------------------------------------------------

export interface IndicatorConfig {
  priceOverlays: PriceOverlayConfig[];
  oscillator: OscillatorConfig;
}

// ---------------------------------------------------------------------------
// Default config — RSI strategy
// ---------------------------------------------------------------------------

export const DEFAULT_INDICATOR_CONFIG: IndicatorConfig = {
  priceOverlays: [
    { type: "ema", dataKey: "ema21",  color: "#F59E0B", label: "EMA21"  },
    { type: "ema", dataKey: "ema200", color: "#3B82F6", label: "EMA200" },
  ],
  oscillator: {
    type: "rsi",
    rsiDataKey:  "rsi",
    ema9DataKey:  "ema9",
    wma45DataKey: "wma45",
    obLevel: 70,
    osLevel: 30,
  },
};
