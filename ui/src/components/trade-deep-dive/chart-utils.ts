import type { ChartCandle } from "../../api/quant";

export interface ChartDataPoint {
  index: number;
  time: string;        // ISO string
  dateLabel: string;   // "Apr 12 · 14:30"
  calendarDate: string; // "2025-04-12" for break detection
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  rsi: number | null;
  ema9: number | null;
  wma45: number | null;
  ema21: number | null;
  ema200: number | null;
  spread: number | null;
  above_ema21: boolean | null;
  active_sl: number | undefined;
  isEntry: boolean;
  isExit: boolean;
}

export interface MaeMfe {
  mae: number; // max adverse excursion as a decimal fraction (e.g. -0.012 = -1.2%)
  mfe: number; // max favorable excursion as a decimal fraction (e.g. 0.038 = 3.8%)
}

/**
 * Transform raw API candles into chart-ready data points.
 * Also ensures at least one candle is marked as exit.
 */
export function transformChartData(
  candles: ChartCandle[],
  entryTime: string,
): ChartDataPoint[] {
  const entryMs = new Date(entryTime).getTime();

  const data: ChartDataPoint[] = candles.map((c, i) => {
    const dateObj = new Date(c.time);
    const dateLabel = dateObj.toLocaleString("en-US", {
      timeZone: "Asia/Bangkok", // UTC+7
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
    // calendarDate used for day-break detection — keep in UTC+7 too
    const calendarDate = dateObj.toLocaleDateString("en-CA", {
      timeZone: "Asia/Bangkok",
    }); // "YYYY-MM-DD"
    const isEntry = c.is_entry ?? Math.abs(dateObj.getTime() - entryMs) < 1000;

    return {
      index: i,
      time: c.time,
      dateLabel,
      calendarDate,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume ?? 0,
      rsi: c.rsi ?? null,
      ema9: c.ema9 ?? null,
      wma45: c.wma45 ?? null,
      ema21: c.ema21 ?? null,
      ema200: c.ema200 ?? null,
      spread: c.spread ?? null,
      above_ema21: c.above_ema21 ?? null,
      active_sl: c.active_sl,
      isEntry,
      isExit: c.is_exit ?? false,
    };
  });

  // Ensure at least one candle is marked as exit
  if (data.length > 0 && !data.some((d) => d.isExit)) {
    data[data.length - 1].isExit = true;
  }

  return data;
}

/**
 * Compute MAE and MFE from chart data between entry and exit candles.
 * LONG:  MAE = (entry - minLow) / entry,  MFE = (maxHigh - entry) / entry
 * SHORT: MAE = (maxHigh - entry) / entry, MFE = (entry - minLow) / entry
 */
export function computeMaeMfe(
  data: ChartDataPoint[],
  side: "LONG" | "SHORT",
  entryPrice: number,
): MaeMfe {
  const entryIdx = data.findIndex((d) => d.isEntry);
  const exitIdx = data.findLastIndex((d) => d.isExit);

  if (entryIdx === -1 || exitIdx === -1 || entryIdx >= exitIdx) {
    return { mae: 0, mfe: 0 };
  }

  const window = data.slice(entryIdx, exitIdx + 1);
  const minLow = Math.min(...window.map((d) => d.low));
  const maxHigh = Math.max(...window.map((d) => d.high));

  if (side === "LONG") {
    return {
      mae: (minLow - entryPrice) / entryPrice,
      mfe: (maxHigh - entryPrice) / entryPrice,
    };
  } else {
    return {
      mae: (entryPrice - maxHigh) / entryPrice,
      mfe: (entryPrice - minLow) / entryPrice,
    };
  }
}

/**
 * Format duration between two ISO timestamps as "2h 35m".
 */
export function formatDuration(entryTime: string, exitTime?: string): string {
  if (!exitTime) return "—";
  const diffMs = new Date(exitTime).getTime() - new Date(entryTime).getTime();
  if (diffMs <= 0) return "—";
  const totalMin = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours === 0) return `${mins}m`;
  if (mins === 0) return `${hours}h`;
  return `${hours}h ${mins}m`;
}

/**
 * Format a price with adaptive precision so small token prices (e.g. 0.0000123)
 * are displayed accurately rather than rounded to $0.00.
 *
 * Strategy: always show 4 significant digits after the first non-zero digit.
 *   ≥ 1000  → 2 decimals  ($52 341.25)
 *   ≥ 1     → 4 decimals  ($1.2345)
 *   < 1     → enough decimals to show 4 sig-figs past the leading zeros
 *             ($0.0000001234)
 */
export function formatPrice(price: number, withDollar = true): string {
  if (!Number.isFinite(price) || price === 0) return withDollar ? "$0" : "0";
  const abs = Math.abs(price);
  let str: string;
  if (abs >= 1000) {
    str = price.toFixed(2);
  } else if (abs >= 1) {
    str = price.toFixed(4);
  } else {
    // position of first significant digit + 4 more sig-figs
    const decimals = Math.min(Math.ceil(-Math.log10(abs)) + 4, 12);
    str = price.toFixed(decimals);
  }
  return withDollar ? `$${str}` : str;
}

/**
 * X-axis tick formatter: shows date label only when calendar date changes.
 */
export function dateBreakFormatter(
  data: ChartDataPoint[],
  index: number,
): string {
  // With type="number" XAxis, Recharts can emit fractional tick values
  // (e.g. 49.5) or ticks just outside the domain. Round and guard.
  const i = Math.round(index);
  if (i < 0 || i >= data.length) return "";
  const curr = data[i];
  if (!curr) return "";
  if (i === 0) return curr.dateLabel;
  const prev = data[i - 1];
  if (!prev) return curr.dateLabel;
  if (curr.calendarDate !== prev.calendarDate) return curr.dateLabel;
  return "";
}
