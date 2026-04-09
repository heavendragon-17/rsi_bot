// @ts-nocheck
import React, { useEffect, useRef, useState } from "react";
import * as LightweightCharts from "lightweight-charts";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";

export const PortfolioEquityChart: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<LightweightCharts.IChartApi | null>(null);

  const [showDispersion, setShowDispersion] = useState(true);

  const {
    portfolioEquityCurve,
    benchmarkEquityCurve,
    dispersionRange,
    totalPnL,
    pinnedSymbols,
    symbolResults,
  } = useBatchResultsStore();

  const isProfit = totalPnL >= 0;
  const portfolioColor = "#ffffff";
  const benchmarkColor = "#71717a";
  const dispersionColor = isProfit ? "#22c55e" : "#ef4444";
  const gridColor = "rgba(255, 255, 255, 0.05)";
  const textColor = "#a1a1aa";
  const bgColor = "transparent";

  const pinColors = ["#f59e0b", "#3b82f6", "#ec4899"];

  const hasDispersion = dispersionRange.length > 0;

  useEffect(() => {
    if (!chartContainerRef.current) return;
    if (chartContainerRef.current.clientWidth === 0) return;
    if (portfolioEquityCurve.length === 0) return;

    const { createChart, ColorType, LineStyle, LineSeries, AreaSeries } =
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
      height: 250,
      timeScale: { visible: true, borderVisible: false },
      rightPriceScale: { borderVisible: false },
      crosshair: { vertLine: { labelVisible: false } },
    });

    const startValue = portfolioEquityCurve[0].value;

    const normPortfolio = portfolioEquityCurve.map((d) => ({
      time: d.time,
      value: ((d.value - startValue) / startValue) * 100,
    }));

    const startBench =
      benchmarkEquityCurve.length > 0 ? benchmarkEquityCurve[0].value : 1;
    const normBenchmark = benchmarkEquityCurve.map((d) => ({
      time: d.time,
      value: ((d.value - startBench) / startBench) * 100,
    }));

    // --- Dispersion band: AreaSeries (high, fills downward) + LineSeries (low bound) ---
    if (showDispersion && hasDispersion) {
      // Upper bound: AreaSeries with gradient fill going down — creates the shaded band region
      const highSeries = chart.addSeries(AreaSeries, {
        lineColor: `${dispersionColor}55`,
        topColor: "rgba(0,0,0,0)",
        bottomColor: `${dispersionColor}18`,
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (p: number) => `${p.toFixed(2)}%` },
      });
      highSeries.setData(
        dispersionRange.map((d) => ({ time: d.time, value: d.max }))
      );

      // Lower bound: LineSeries marks the floor of the band
      const lowSeries = chart.addSeries(LineSeries, {
        color: `${dispersionColor}55`,
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat: { type: "custom", formatter: (p: number) => `${p.toFixed(2)}%` },
      });
      lowSeries.setData(
        dispersionRange.map((d) => ({ time: d.time, value: d.min }))
      );
    }

    // Portfolio line (on top of dispersion)
    const portfolioSeries = chart.addSeries(AreaSeries, {
      lineColor: portfolioColor,
      topColor: `${portfolioColor}22`,
      bottomColor: `${portfolioColor}00`,
      lineWidth: 3,
      priceFormat: { type: "custom", formatter: (p: number) => `${p.toFixed(2)}%` },
    });
    portfolioSeries.setData(normPortfolio);

    // Benchmark (dashed)
    if (normBenchmark.length > 0) {
      const benchmarkSeries = chart.addSeries(LineSeries, {
        color: benchmarkColor,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
        priceFormat: { type: "custom", formatter: (p: number) => `${p.toFixed(2)}%` },
      });
      benchmarkSeries.setData(normBenchmark);
    }

    // Pinned symbols
    pinnedSymbols.forEach((sym, idx) => {
      const symData = symbolResults.find((r) => r.symbol === sym);
      if (symData && symData.equityCurve.length > 0) {
        const sStart = symData.equityCurve[0].value;
        const sCurve = symData.equityCurve.map((d) => ({
          time: d.time,
          value: ((d.value - sStart) / sStart) * 100,
        }));
        const pinSeries = chart.addSeries(LineSeries, {
          color: pinColors[idx % pinColors.length],
          lineWidth: 1,
          priceFormat: { type: "custom", formatter: (p: number) => `${p.toFixed(2)}%` },
        });
        pinSeries.setData(sCurve);
      }
    });

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
  }, [
    portfolioEquityCurve,
    benchmarkEquityCurve,
    dispersionRange,
    pinnedSymbols,
    symbolResults,
    showDispersion,
  ]);

  return (
    <div className="flex flex-col border border-border-main rounded-xl bg-bg-surface overflow-hidden mb-6 relative">
      <div className="p-3 border-b border-border-main flex items-center justify-between bg-bg-elevated/20">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Portfolio Performance (Normalized %)
        </span>

        {/* Legend */}
        <div className="flex items-center gap-3">
          {/* Portfolio */}
          <div className="flex items-center gap-1.5 text-[10px] text-text-primary">
            <div className="w-3 h-0.5 bg-white" />
            Portfolio
          </div>

          {/* Benchmark — greyed out until implemented */}
          <div className="flex items-center gap-1.5 text-[10px] text-text-muted opacity-40 cursor-not-allowed" title="Benchmark — coming soon">
            <div className="w-3 h-0.5 border-t border-dashed border-zinc-500" />
            Benchmark
          </div>

          {/* Dispersion toggle */}
          {hasDispersion && (
            <button
              onClick={() => setShowDispersion((v) => !v)}
              className={`flex items-center gap-1.5 text-[10px] transition-opacity ${
                showDispersion ? "opacity-100" : "opacity-35"
              }`}
              style={{ color: dispersionColor }}
              title={showDispersion ? "Hide dispersion band" : "Show dispersion band"}
            >
              {/* Band icon: two parallel lines */}
              <svg width="12" height="8" viewBox="0 0 12 8" fill="none">
                <line x1="0" y1="1" x2="12" y2="1" stroke="currentColor" strokeWidth="1.2" />
                <rect x="0" y="2.5" width="12" height="3" fill="currentColor" fillOpacity="0.2" />
                <line x1="0" y1="7" x2="12" y2="7" stroke="currentColor" strokeWidth="1.2" />
              </svg>
              Dispersion
            </button>
          )}

          {/* Pinned symbols */}
          {pinnedSymbols.map((sym, idx) => (
            <div
              key={sym}
              className="flex items-center gap-1.5 text-[10px]"
              style={{ color: pinColors[idx % pinColors.length] }}
            >
              <div className="w-3 h-0.5 bg-current" />
              {sym}
            </div>
          ))}
        </div>
      </div>

      <div className="relative h-[250px] w-full" ref={chartContainerRef}>
        {portfolioEquityCurve.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-text-muted">
            No equity data — run a backtest to see the portfolio curve.
          </div>
        )}
      </div>
    </div>
  );
};
