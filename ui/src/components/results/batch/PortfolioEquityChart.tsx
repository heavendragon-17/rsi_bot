// @ts-nocheck
import React, { useEffect, useRef } from "react";
import * as LightweightCharts from "lightweight-charts";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";

export const PortfolioEquityChart: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<LightweightCharts.IChartApi | null>(null);

  const {
    portfolioEquityCurve,
    benchmarkEquityCurve,
    dispersionRange,
    totalPnL,
    pinnedSymbols,
    symbolResults,
  } = useBatchResultsStore();

  const isProfit = totalPnL >= 0;
  const portfolioColor = "#ffffff"; // White for portfolio main line
  const benchmarkColor = "#71717a"; // Zinc-500
  const dispersionColor = isProfit ? "#22c55e" : "#ef4444"; // Color for range
  const gridColor = "rgba(255, 255, 255, 0.05)";
  const textColor = "#a1a1aa";
  const bgColor = "transparent";

  // Pin colors
  const pinColors = ["#f59e0b", "#3b82f6", "#ec4899"]; // Amber, Blue, Pink

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;

    const initChart = () => {
      // Prevent double-init
      if (chartRef.current) return;
      if (container.clientWidth === 0) return;

      const { createChart, ColorType, LineStyle, LineSeries, AreaSeries } =
        LightweightCharts;

      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: bgColor },
          textColor,
        },
        grid: {
          vertLines: { color: gridColor },
          horzLines: { color: gridColor },
        },
        width: container.clientWidth,
        height: container.clientHeight || 280,
        timeScale: { visible: true, borderVisible: false },
        rightPriceScale: { borderVisible: false },
        crosshair: { vertLine: { labelVisible: false } },
      });

      // Normalize everything to % Return for the chart.
      const startValue =
        portfolioEquityCurve.length > 0 ? portfolioEquityCurve[0].value : 1;

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

      // Dispersion is already in %.
      const dispHigh = dispersionRange.map((d) => ({
        time: d.time,
        value: d.max,
      }));
      const dispLow = dispersionRange.map((d) => ({
        time: d.time,
        value: d.min,
      }));

      // Plot Dispersion Bounds (faint)
      if (dispHigh.length > 0) {
        const highSeries = chart.addSeries(LineSeries, {
          color: `${dispersionColor}44`,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          crosshairMarkerVisible: false,
          lastValueVisible: false,
          priceLineVisible: false,
        });
        highSeries.setData(dispHigh);
        const lowSeries = chart.addSeries(LineSeries, {
          color: `${dispersionColor}44`,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          crosshairMarkerVisible: false,
          lastValueVisible: false,
          priceLineVisible: false,
        });
        lowSeries.setData(dispLow);
      }

      // Portfolio Line (Bold Area)
      const portfolioSeries = chart.addSeries(AreaSeries, {
        lineColor: portfolioColor,
        topColor: `${portfolioColor}22`,
        bottomColor: `${portfolioColor}00`,
        lineWidth: 3,
        priceFormat: { type: "percent" },
      });
      portfolioSeries.setData(normPortfolio);

      // Benchmark (Dashed)
      if (normBenchmark.length > 0) {
        const benchmarkSeries = chart.addSeries(LineSeries, {
          color: benchmarkColor,
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          crosshairMarkerVisible: false,
          priceFormat: { type: "percent" },
        });
        benchmarkSeries.setData(normBenchmark);
      }

      // Pinned Symbols
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
            priceFormat: { type: "percent" },
          });
          pinSeries.setData(sCurve);
        }
      });

      chart.timeScale().fitContent();
      chartRef.current = chart;
    };

    // Use ResizeObserver to wait for non-zero dimensions, then init
    initChart();

    const ro = new ResizeObserver(() => {
      if (!chartRef.current) {
        initChart();
      } else if (container.clientWidth > 0) {
        chartRef.current.applyOptions({
          width: container.clientWidth,
          height: container.clientHeight,
        });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [
    portfolioEquityCurve,
    benchmarkEquityCurve,
    dispersionRange,
    pinnedSymbols,
    symbolResults,
  ]);

  return (
    <div className="flex flex-col border border-border-main rounded-xl bg-bg-surface overflow-hidden mb-6 relative">
      <div className="p-3 border-b border-border-main flex items-center justify-between bg-bg-elevated/20">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Portfolio Performance (Normalized %)
        </span>
        {/* Legend */}
        <div className="flex gap-3">
          <div className="flex items-center gap-1.5 text-[10px] text-text-primary">
            <div className="w-3 h-0.5 bg-white" />
            Portfolio
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-text-muted">
            <div className="w-3 h-0.5 border-t border-dashed border-zinc-500" />
            Benchmark
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-text-muted opacity-60">
            <div className="w-3 h-2 border border-dotted border-current" />
            Dispersion
          </div>
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
      <div className="relative h-[280px] w-full shrink-0" ref={chartContainerRef} />
    </div>
  );
};
