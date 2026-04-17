import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { getTradeChart } from "../../api/quant";
import { transformChartData, computeMaeMfe } from "./chart-utils";
import type { ChartDataPoint, MaeMfe } from "./chart-utils";
import { TradeDeepDiveHeader } from "./TradeDeepDiveHeader";
import { PriceCandlestickChart } from "./PriceCandlestickChart";
import { RsiChart } from "./RsiChart";
import { TradeAnnotationPanel } from "./TradeAnnotationPanel";
import { DEFAULT_INDICATOR_CONFIG } from "./indicator-config";

export interface DeepDiveTrade {
  id: number;
  entryTime: string;
  exitTime?: string;
  symbol: string;
  side: "LONG" | "SHORT";
  entryPrice: number;
  exitPrice: number;
  pnl: number;
  pnlPct: number;
  exitReason: string;
}

export interface TradeDeepDiveProps {
  trade: DeepDiveTrade;
  onClose: () => void;
  trades?: DeepDiveTrade[];
  onNavigate?: (trade: DeepDiveTrade) => void;
}

export function TradeDeepDive({
  trade,
  onClose,
  trades,
  onNavigate,
}: TradeDeepDiveProps) {
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [maeMfe, setMaeMfe] = useState<MaeMfe | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Zoom/pan state — null means "show everything"
  const [zoom, setZoom] = useState<{ start: number; end: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const chartsRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startZoom: { start: number; end: number } } | null>(null);

  // Reset zoom when trade changes
  useEffect(() => { setZoom(null); }, [trade.id]);

  // Keyboard navigation
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (!trades || !onNavigate) return;
      const idx = trades.findIndex((t) => t.id === trade.id);
      if (e.key === "ArrowLeft" && idx > 0) {
        onNavigate(trades[idx - 1]);
      } else if (e.key === "ArrowRight" && idx < trades.length - 1) {
        onNavigate(trades[idx + 1]);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [trade.id, trades, onClose, onNavigate]);

  // Fetch chart data
  useEffect(() => {
    let mounted = true;
    async function fetchChart() {
      setIsLoading(true);
      setError(null);
      try {
        const raw = await getTradeChart(trade.id.toString());
        if (!mounted) return;
        const data = transformChartData(raw, trade.entryTime);
        const mae = computeMaeMfe(data, trade.side, trade.entryPrice);
        setChartData(data);
        setMaeMfe(mae);
      } catch (err) {
        if (!mounted) return;
        console.error(err);
        setError("Failed to fetch trade chart data.");
      } finally {
        if (mounted) setIsLoading(false);
      }
    }
    fetchChart();
    return () => { mounted = false; };
  }, [trade.id, trade.entryTime, trade.side, trade.entryPrice]);

  // Slice and reindex data for the current zoom window.
  // Reindexing ensures candle centering (domain={[-0.5, N-0.5]}) stays correct
  // at any zoom level without additional chart changes.
  const visibleData = useMemo((): ChartDataPoint[] => {
    if (!zoom || !chartData.length) return chartData;
    return chartData
      .slice(zoom.start, zoom.end + 1)
      .map((d, i) => ({ ...d, index: i }));
  }, [chartData, zoom]);

  // Shift+wheel zooms the chart; plain wheel falls through so the modal
  // can scroll normally even when the cursor is over the chart area.
  const handleWheel = useCallback((e: WheelEvent) => {
    if (!e.shiftKey) return;
    const total = chartData.length;
    if (!total) return;
    e.preventDefault();

    const start = zoom?.start ?? 0;
    const end = zoom?.end ?? total - 1;
    const windowSize = end - start + 1;

    // Wheel up → zoom in (smaller window); wheel down → zoom out
    const factor = e.deltaY > 0 ? 1.2 : 1 / 1.2;
    const newWindowSize = Math.round(windowSize * factor);
    if (newWindowSize < 10) return;
    if (newWindowSize >= total) { setZoom(null); return; }

    // Zoom anchored to cursor position within the chart container
    const rect = chartsRef.current?.getBoundingClientRect();
    const fraction = rect
      ? Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      : 0.5;

    const anchorIdx = start + Math.round(fraction * (windowSize - 1));
    const newStart = Math.max(0, Math.round(anchorIdx - fraction * newWindowSize));
    const newEnd = Math.min(total - 1, newStart + newWindowSize - 1);
    setZoom({ start: newStart, end: newEnd });
  }, [chartData.length, zoom]);

  useEffect(() => {
    const el = chartsRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  // Drag-to-pan
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const start = zoom?.start ?? 0;
    const end = zoom?.end ?? chartData.length - 1;
    dragRef.current = { startX: e.clientX, startZoom: { start, end } };
    setIsDragging(true);
  }, [zoom, chartData.length]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || !chartsRef.current) return;
    const containerWidth = chartsRef.current.offsetWidth;
    const { startX, startZoom } = drag;
    const windowSize = startZoom.end - startZoom.start;

    const shift = Math.round((-( e.clientX - startX) / containerWidth) * windowSize);
    const newStart = Math.max(0, startZoom.start + shift);
    const newEnd = Math.min(chartData.length - 1, startZoom.end + shift);
    if (newEnd - newStart === windowSize) {
      setZoom(newStart === 0 && newEnd === chartData.length - 1
        ? null
        : { start: newStart, end: newEnd });
    }
  }, [chartData.length]);

  const stopDrag = useCallback(() => {
    dragRef.current = null;
    setIsDragging(false);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-6 sm:p-8 bg-slate-950/90 backdrop-blur-md"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[1400px] max-h-[92vh] bg-slate-900/95 backdrop-blur-xl rounded-2xl border border-violet-500/30 shadow-[0_0_60px_rgba(139,92,246,0.3)] overflow-hidden flex flex-col"
      >
        <TradeDeepDiveHeader
          trade={trade}
          maeMfe={maeMfe}
          trades={trades}
          onClose={onClose}
          onNavigate={onNavigate}
        />

        {/* Charts + annotation */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-6 sm:px-8 sm:py-7 space-y-5 relative">
          {isLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm rounded-xl">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
                <span className="text-slate-300 font-medium">
                  Loading chart data...
                </span>
              </div>
            </div>
          )}
          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm rounded-xl">
              <div className="bg-rose-500/10 border border-rose-500/20 px-4 py-3 rounded-lg text-rose-400">
                {error}
              </div>
            </div>
          )}

          {!isLoading && !error && chartData.length > 0 && (
            <>
              {/* Charts — wheel to zoom, drag to pan */}
              <div
                ref={chartsRef}
                className="space-y-4 select-none"
                style={{ cursor: isDragging ? "grabbing" : "crosshair" }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={stopDrag}
                onMouseLeave={stopDrag}
              >
                <PriceCandlestickChart
                  data={visibleData}
                  entryPrice={trade.entryPrice}
                  exitPrice={trade.exitPrice}
                  isWin={trade.pnl > 0}
                  indicatorConfig={DEFAULT_INDICATOR_CONFIG}
                />
                <RsiChart data={visibleData} indicatorConfig={DEFAULT_INDICATOR_CONFIG} />
              </div>

              {/* Zoom / pan hint */}
              <div className="flex items-center justify-center gap-3 text-xs text-slate-500">
                {zoom ? (
                  <>
                    <span>
                      Showing {visibleData.length} of {chartData.length} candles
                    </span>
                    <button
                      onClick={() => setZoom(null)}
                      className="px-2 py-0.5 rounded border border-white/10 text-slate-400 hover:text-white hover:border-white/30 transition-colors"
                    >
                      Reset zoom
                    </button>
                  </>
                ) : (
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded border border-white/10 text-slate-400 font-mono text-[10px]">Shift</kbd>
                    {" + scroll to zoom · drag to pan"}
                  </span>
                )}
              </div>
            </>
          )}

          <TradeAnnotationPanel tradeId={trade.id} />
        </div>
      </motion.div>
    </motion.div>
  );
}
