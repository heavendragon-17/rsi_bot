// @ts-nocheck
import React, { useEffect, useRef, useState } from "react";
import * as LightweightCharts from "lightweight-charts";
import { useResultsStore } from "../../stores/resultsStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { getBenchmark } from "../../api/backtest";

const BENCHMARK_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "HYPE/USDT", "BNB/USDT", "XRP/USDT"];

export const EquityUnderwaterChart: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const underwaterContainerRef = useRef<HTMLDivElement>(null);

  const chartRef = useRef<LightweightCharts.IChartApi | null>(null);
  const underwaterChartRef = useRef<LightweightCharts.IChartApi | null>(null);

  const [activeBenchmark, setActiveBenchmark] = useState<string | null>(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);

  const { equityCurve, benchmarkCurve, underwaterCurve, netProfit, setResults } =
    useResultsStore();

  const { timeframe, startDate, endDate, capital } = useBacktestStore();

  const handleBenchmarkSwitch = async (sym: string | null) => {
    if (sym === activeBenchmark) return;
    setActiveBenchmark(sym);
    if (!sym) {
      setResults({ benchmarkCurve: [] });
      return;
    }
    setBenchmarkLoading(true);
    try {
      const result = await getBenchmark(sym, timeframe, startDate, endDate, parseFloat(capital) || 10000);
      // Deduplicate to one point per calendar day (backend may return one row per candle)
      const seen = new Map<string, { time: string; value: number }>();
      for (const p of (result.curve ?? [])) {
        const t = String(p["date"] ?? "").slice(0, 10);
        const v = typeof p["balance"] === "string" ? parseFloat(p["balance"] as string) : Number(p["balance"]);
        seen.set(t, { time: t, value: v });
      }
      const curve = Array.from(seen.values()).sort((a, b) => (a.time < b.time ? -1 : 1));
      setResults({ benchmarkCurve: curve });
    } catch (_) {
      // silently ignore if CSV not available
    } finally {
      setBenchmarkLoading(false);
    }
  };

  const isProfit = netProfit >= 0;
  const strategyColor = isProfit ? "#22c55e" : "#ef4444";
  const benchmarkColor = "#71717a";
  const underwaterColor = "#ef4444";
  const gridColor = "rgba(255, 255, 255, 0.05)";
  const textColor = "#a1a1aa";
  const bgColor = "transparent";

  // Main Chart Initialization
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Safety check for dimensions
    if (chartContainerRef.current.clientWidth === 0) return;

    // Use namespace to ensure correct access
    const { createChart, ColorType, LineStyle, AreaSeries, LineSeries } =
      LightweightCharts;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: { visible: true, borderVisible: false },
      rightPriceScale: { borderVisible: false },
      crosshair: { vertLine: { labelVisible: false } },
    });

    // Check if addSeries exists before calling (v5 API)
    let strategySeries;
    if (typeof chart.addSeries === "function") {
      strategySeries = chart.addSeries(AreaSeries, {
        lineColor: strategyColor,
        topColor: `${strategyColor}33`,
        bottomColor: `${strategyColor}00`,
        lineWidth: 2,
      });
      strategySeries.setData(equityCurve);
    } else {
      console.error("LightweightCharts: addSeries not found on chart instance");
    }

    let benchmarkSeries;
    if (typeof chart.addSeries === "function") {
      benchmarkSeries = chart.addSeries(LineSeries, {
        color: benchmarkColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
      });
      benchmarkSeries.setData(benchmarkCurve);
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [equityCurve, benchmarkCurve, strategyColor]);

  // Underwater Chart Initialization
  useEffect(() => {
    if (!underwaterContainerRef.current) return;
    if (underwaterContainerRef.current.clientWidth === 0) return;

    const { createChart, ColorType, AreaSeries } = LightweightCharts;

    const chart = createChart(underwaterContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      width: underwaterContainerRef.current.clientWidth,
      height: 130,
      timeScale: { visible: false },
      rightPriceScale: { borderVisible: false },
      crosshair: { vertLine: { labelVisible: false } },
    });

    if (typeof chart.addSeries === "function") {
      const series = chart.addSeries(AreaSeries, {
        lineColor: underwaterColor,
        topColor: `${underwaterColor}11`,
        bottomColor: `${underwaterColor}66`,
        lineWidth: 1,
        priceFormat: {
          type: "custom",
          formatter: (p: number) => `${p.toFixed(2)}%`,
        },
      });
      series.setData(underwaterCurve);
    }

    chart.timeScale().fitContent();
    underwaterChartRef.current = chart;

    const handleResize = () => {
      if (underwaterContainerRef.current) {
        chart.applyOptions({
          width: underwaterContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      underwaterChartRef.current = null;
    };
  }, [underwaterCurve]);

  // Sync Logic
  useEffect(() => {
    if (!chartRef.current || !underwaterChartRef.current) return;

    const mainTimeScale = chartRef.current.timeScale();
    const subTimeScale = underwaterChartRef.current.timeScale();

    const syncHandler = (timeRange: any) => {
      if (timeRange) {
        subTimeScale.setVisibleRange(timeRange);
      }
    };

    mainTimeScale.subscribeVisibleTimeRangeChange(syncHandler);

    return () => {
      mainTimeScale.unsubscribeVisibleTimeRangeChange(syncHandler);
    };
  }, [equityCurve]); // Re-run sync setup if charts regenerate

  return (
    <div className="space-y-6">
      {/* Equity Curve */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider">
            Equity Curve
          </h2>
          {/* In-chart benchmark switcher */}
          <div className="flex items-center gap-0.5">
            {benchmarkCurve.length > 0 && (
              <span className="text-[9px] text-zinc-400 mr-1">
                Benchmark: {activeBenchmark ? activeBenchmark.split("/")[0] : "—"}
              </span>
            )}
            <button
              onClick={() => handleBenchmarkSwitch(null)}
              className={`px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors ${activeBenchmark === null ? "bg-bg-elevated text-text-primary" : "text-text-muted hover:text-text-secondary"}`}
            >
              Off
            </button>
            {BENCHMARK_SYMBOLS.map((s) => (
              <button
                key={s}
                onClick={() => handleBenchmarkSwitch(s)}
                disabled={benchmarkLoading}
                className={`px-1.5 py-0.5 text-[9px] rounded font-medium transition-colors ${activeBenchmark === s ? "bg-bg-elevated text-text-primary" : "text-text-muted hover:text-text-secondary"}`}
              >
                {s.split("/")[0]}
              </button>
            ))}
            {benchmarkLoading && <span className="text-[9px] text-text-muted ml-1">…</span>}
          </div>
        </div>
        <div
          id="equity-chart"
          ref={chartContainerRef}
          className="w-full rounded-lg border border-border-main bg-bg-elevated/50 overflow-hidden"
        />
      </div>

      {/* Drawdown (Underwater) */}
      <div>
        <h2 className="text-sm font-bold text-text-primary mb-3 uppercase tracking-wider">
          Underwater Curve (Drawdown)
        </h2>
        <div
          id="drawdown-chart"
          ref={underwaterContainerRef}
          className="w-full rounded-lg border border-border-main bg-bg-elevated/50 overflow-hidden"
        />
      </div>
    </div>
  );
};
