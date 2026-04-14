import React, { useState, useEffect } from "react";
import { motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { getTradeChart } from "../../api/quant";
import { transformChartData, computeMaeMfe } from "./chart-utils";
import type { ChartDataPoint, MaeMfe } from "./chart-utils";
import { TradeDeepDiveHeader } from "./TradeDeepDiveHeader";
import { PriceCandlestickChart } from "./PriceCandlestickChart";
import { RsiVolumeChart } from "./RsiVolumeChart";
import { TradeAnnotationPanel } from "./TradeAnnotationPanel";

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
    return () => {
      mounted = false;
    };
  }, [trade.id, trade.entryTime, trade.side, trade.entryPrice]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[1600px] max-h-[90vh] bg-slate-800/95 backdrop-blur-xl rounded-2xl border border-violet-500/30 shadow-[0_0_60px_rgba(139,92,246,0.3)] overflow-hidden flex flex-col"
      >
        <TradeDeepDiveHeader
          trade={trade}
          maeMfe={maeMfe}
          trades={trades}
          onClose={onClose}
          onNavigate={onNavigate}
        />

        {/* Charts + annotation */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 relative">
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
              <PriceCandlestickChart
                data={chartData}
                entryPrice={trade.entryPrice}
                exitPrice={trade.exitPrice}
                isWin={trade.pnl > 0}
              />
              <RsiVolumeChart data={chartData} />
            </>
          )}

          <TradeAnnotationPanel tradeId={trade.id} />
        </div>
      </motion.div>
    </motion.div>
  );
}
