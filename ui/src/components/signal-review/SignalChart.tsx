import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
} from "lightweight-charts";
import type { SignalChartResponse } from "../../types/generated";
import { REVIEW_CHART_CHUNK_CANDLES } from "../../lib/signal-review";

interface SignalChartProps {
  chart: SignalChartResponse;
  triggerClosePrice: number;
  onLoadMore: () => Promise<void>;
}

interface ChartCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  rsi21?: number | null;
  rsi_ema9?: number | null;
  rsi_wma45?: number | null;
  ema21?: number | null;
  is_trigger?: boolean;
}

interface LogicalRange {
  from: number;
  to: number;
}

const DEFAULT_VISIBLE_CONTEXT = 120;
const DEFAULT_VISIBLE_FUTURE = 240;

const CHART_OPTIONS = {
  layout: {
    background: { type: ColorType.Solid, color: "#0f172a" },
    textColor: "#94a3b8",
  },
  grid: {
    vertLines: { color: "rgba(51, 65, 85, 0.35)" },
    horzLines: { color: "rgba(51, 65, 85, 0.35)" },
  },
  rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.25)" },
  timeScale: { borderColor: "rgba(148, 163, 184, 0.25)", timeVisible: true },
  crosshair: { mode: 0 },
};

function toUnixSeconds(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

function formatCandleSpan(candles: number, timeframe: string): string {
  const minutes = candles * (timeframe === "5m" ? 5 : 15);
  const days = Math.floor(minutes / (24 * 60));
  const hours = Math.floor((minutes % (24 * 60)) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  return `${hours}h`;
}

export function SignalChart({ chart, triggerClosePrice, onLoadMore }: SignalChartProps) {
  const priceContainer = useRef<HTMLDivElement>(null);
  const rsiContainer = useRef<HTMLDivElement>(null);
  const loadingMore = useRef(false);
  const lastVisibleRange = useRef<LogicalRange | null>(null);
  const lastSignalId = useRef<number | null>(null);
  const previousFutureAllowed = useRef(false);

  useEffect(() => {
    if (!priceContainer.current || !rsiContainer.current || chart.candles.length === 0) {
      return undefined;
    }

    const rows = chart.candles as unknown as ChartCandle[];
    const signalChanged = lastSignalId.current !== chart.signal_id;
    const futureJustUnlocked = !previousFutureAllowed.current && chart.future_allowed;
    if (signalChanged || futureJustUnlocked) lastVisibleRange.current = null;
    lastSignalId.current = chart.signal_id;
    previousFutureAllowed.current = chart.future_allowed;
    const priceChart = createChart(priceContainer.current, {
      ...CHART_OPTIONS,
      width: priceContainer.current.clientWidth,
      height: 430,
    });
    const rsiChart = createChart(rsiContainer.current, {
      ...CHART_OPTIONS,
      width: rsiContainer.current.clientWidth,
      height: 220,
      rightPriceScale: { ...CHART_OPTIONS.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0.1 } },
    });

    const candles = priceChart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    const ema21 = priceChart.addSeries(LineSeries, {
      color: "#fbbf24",
      lineWidth: 2,
      title: "EMA21",
    });
    const rsi = rsiChart.addSeries(LineSeries, {
      color: "#fbbf24",
      lineWidth: 2,
      title: "RSI21",
      autoscaleInfoProvider: (original) => {
        const info = original();
        if (!info) return null;
        return { ...info, priceRange: { minValue: 0, maxValue: 100 } };
      },
    });
    const rsiEma = rsiChart.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 1,
      title: "EMA9",
    });
    const rsiWma = rsiChart.addSeries(LineSeries, {
      color: "#f472b6",
      lineWidth: 1,
      lineStyle: 2,
      title: "WMA45",
    });

    const validRows = rows.map((row) => ({ ...row, time: toUnixSeconds(row.time) as any }));
    candles.setData(validRows.map((row) => ({
      time: row.time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    })) as any);
    ema21.setData(validRows.filter((row) => row.ema21 != null).map((row) => ({ time: row.time, value: row.ema21! })) as any);
    rsi.setData(validRows.filter((row) => row.rsi21 != null).map((row) => ({ time: row.time, value: row.rsi21! })) as any);
    rsiEma.setData(validRows.filter((row) => row.rsi_ema9 != null).map((row) => ({ time: row.time, value: row.rsi_ema9! })) as any);
    rsiWma.setData(validRows.filter((row) => row.rsi_wma45 != null).map((row) => ({ time: row.time, value: row.rsi_wma45! })) as any);

    const triggerRow = validRows.find((row) => row.is_trigger);
    if (triggerRow) {
      createSeriesMarkers(candles, [{
        time: triggerRow.time,
        position: "belowBar",
        color: "#a78bfa",
        shape: "arrowUp",
        text: "Signal",
      }] as any);
      candles.createPriceLine({
        price: triggerClosePrice,
        color: "#a78bfa",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "Trigger",
      });
    }

    let syncing = false;
    let userHasInteracted = false;
    const syncRange = (source: any, target: any) => {
      const handler = (range: any) => {
        if (!range || syncing) return;
        syncing = true;
        target.timeScale().setVisibleLogicalRange(range);
        syncing = false;
        if (userHasInteracted) {
          lastVisibleRange.current = { from: range.from, to: range.to };
        }
        if (userHasInteracted && chart.has_after && range.to > rows.length - 20 && !loadingMore.current) {
          loadingMore.current = true;
          void onLoadMore().finally(() => { loadingMore.current = false; });
        }
      };
      source.timeScale().subscribeVisibleLogicalRangeChange(handler);
      return () => source.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
    };
    const removePriceSync = syncRange(priceChart, rsiChart);
    const removeRsiSync = syncRange(rsiChart, priceChart);

    const markUserInteraction = () => {
      userHasInteracted = true;
    };
    priceContainer.current?.addEventListener("wheel", markUserInteraction, { passive: true });
    priceContainer.current?.addEventListener("pointerdown", markUserInteraction);
    rsiContainer.current?.addEventListener("wheel", markUserInteraction, { passive: true });
    rsiContainer.current?.addEventListener("pointerdown", markUserInteraction);

    const triggerIndex = rows.findIndex((row) => row.is_trigger);
    const initialRange = lastVisibleRange.current
      ?? (
        chart.future_allowed && triggerIndex >= 0
          ? {
              from: Math.max(0, triggerIndex - DEFAULT_VISIBLE_CONTEXT),
              to: Math.min(rows.length - 1, triggerIndex + DEFAULT_VISIBLE_FUTURE),
            }
          : null
      );
    if (initialRange) {
      priceChart.timeScale().setVisibleLogicalRange(initialRange);
    } else {
      priceChart.timeScale().fitContent();
      rsiChart.timeScale().fitContent();
    }

    const resize = () => {
      if (priceContainer.current) priceChart.applyOptions({ width: priceContainer.current.clientWidth });
      if (rsiContainer.current) rsiChart.applyOptions({ width: rsiContainer.current.clientWidth });
    };
    window.addEventListener("resize", resize);

    return () => {
      removePriceSync();
      removeRsiSync();
      priceContainer.current?.removeEventListener("wheel", markUserInteraction);
      priceContainer.current?.removeEventListener("pointerdown", markUserInteraction);
      rsiContainer.current?.removeEventListener("wheel", markUserInteraction);
      rsiContainer.current?.removeEventListener("pointerdown", markUserInteraction);
      window.removeEventListener("resize", resize);
      priceChart.remove();
      rsiChart.remove();
    };
  }, [chart, onLoadMore, triggerClosePrice]);

  const warning = chart.warning;
  const rows = chart.candles as unknown as ChartCandle[];
  const triggerIndex = rows.findIndex((row) => row.is_trigger);
  const futureCandleCount = triggerIndex >= 0 ? rows.length - triggerIndex - 1 : 0;
  const futureSpan = formatCandleSpan(futureCandleCount, chart.timeframe);
  return (
    <section className="rounded-xl border border-border-main bg-bg-primary/60 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-semibold text-text-primary">Market replay</h3>
          <p className="text-xs text-text-muted">Crosshair, wheel zoom, drag/pan, and forward candle loading</p>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono text-text-secondary">
          <span className="text-amber-300">EMA21</span>
          <span className="text-amber-300">RSI21</span>
          <span className="text-sky-300">EMA9</span>
          <span className="text-pink-300">WMA45</span>
        </div>
      </div>
      {warning && (
        <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
          {warning}
        </div>
      )}
      {chart.future_allowed && futureCandleCount > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-400/25 bg-emerald-400/5 px-3 py-2 text-xs">
          <span className="font-medium text-emerald-200">Future outcome window unlocked</span>
          <span className="text-text-secondary">{futureCandleCount.toLocaleString()} candles loaded · about {futureSpan} · pan right from the signal</span>
        </div>
      )}
      {chart.candles.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-sm text-text-muted">
          No chart candles available for this CSV range.
        </div>
      ) : (
        <>
          <div ref={priceContainer} className="w-full" />
          <div ref={rsiContainer} className="w-full" />
        </>
      )}
      {chart.has_after && (
        <button
          type="button"
          onClick={() => void onLoadMore()}
          className="rounded-md border border-border-main px-3 py-2 text-xs text-text-secondary hover:text-text-primary hover:border-accent-main transition-colors"
        >
          Extend by {REVIEW_CHART_CHUNK_CANDLES.toLocaleString()} candles
        </button>
      )}
    </section>
  );
}
