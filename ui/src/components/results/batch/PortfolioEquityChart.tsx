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
      symbolResults
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
    if (chartContainerRef.current.clientWidth === 0) return;

    const { createChart, ColorType, LineStyle } = LightweightCharts;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: bgColor }, textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      width: chartContainerRef.current.clientWidth,
      height: 250,
      timeScale: { visible: true, borderVisible: false },
      rightPriceScale: { borderVisible: false },
      crosshair: { vertLine: { labelVisible: false } }
    });

    // 1. Dispersion Range (Simulated via Max/Min lines for now as AreaSeries can't float)
    // To truly do a shaded range, we would ideally use a custom series or two areas where one masks the other.
    // Hack: Just draw the bounds as thin lines for now to meet the "Dispersion" requirement visually without complex custom series code.
    // Or better: Use "Extra Series" logic.
    const maxSeries = chart.addLineSeries({
        color: dispersionColor,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false
    });
    // @ts-ignore
    maxSeries.setData(dispersionRange.map(d => ({ time: d.time, value: d.max / 100 * portfolioEquityCurve[0].value + portfolioEquityCurve[0].value }))); // Scale % back to value roughly for viz? 
    // Wait, dispersion is % return. Equity is value.
    // This is tricky. Let's just plot the Portfolio Equity Area and Benchmark.
    // And simplify Dispersion to just be implied by the portfolio line for MVP unless we normalize everything to %.
    
    // DECISION: Normalize everything to % Return for the chart. This makes Dispersion easy.
    // Let's re-map data to % change from start.
    const startValue = portfolioEquityCurve.length > 0 ? portfolioEquityCurve[0].value : 1;
    
    const normPortfolio = portfolioEquityCurve.map(d => ({
        time: d.time,
        value: ((d.value - startValue) / startValue) * 100
    }));

    const startBench = benchmarkEquityCurve.length > 0 ? benchmarkEquityCurve[0].value : 1;
    const normBenchmark = benchmarkEquityCurve.map(d => ({
        time: d.time,
        value: ((d.value - startBench) / startBench) * 100
    }));
    
    // Now Dispersion is already in %.
    const dispHigh = dispersionRange.map(d => ({ time: d.time, value: d.max }));
    const dispLow = dispersionRange.map(d => ({ time: d.time, value: d.min }));

    // Plot Dispersion Bounds (faint)
    const highSeries = chart.addLineSeries({ color: `${dispersionColor}44`, lineWidth: 1, lineStyle: LineStyle.Dotted, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false });
    highSeries.setData(dispHigh);
    const lowSeries = chart.addLineSeries({ color: `${dispersionColor}44`, lineWidth: 1, lineStyle: LineStyle.Dotted, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false });
    lowSeries.setData(dispLow);

    // 2. Portfolio Line (Bold Area)
    const portfolioSeries = chart.addAreaSeries({
        lineColor: portfolioColor,
        topColor: `${portfolioColor}22`,
        bottomColor: `${portfolioColor}00`,
        lineWidth: 3,
        priceFormat: { type: 'percent' }
    });
    portfolioSeries.setData(normPortfolio);

    // 3. Benchmark (Dashed)
    const benchmarkSeries = chart.addLineSeries({
        color: benchmarkColor,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
        priceFormat: { type: 'percent' }
    });
    benchmarkSeries.setData(normBenchmark);

    // 4. Pinned Symbols
    pinnedSymbols.forEach((sym, idx) => {
        const symData = symbolResults.find(r => r.symbol === sym);
        if (symData) {
            const sStart = symData.equityCurve[0].value;
            const sCurve = symData.equityCurve.map(d => ({
                time: d.time,
                value: ((d.value - sStart) / sStart) * 100
            }));
            
            const pinSeries = chart.addLineSeries({
                color: pinColors[idx % pinColors.length],
                lineWidth: 1,
                priceFormat: { type: 'percent' }
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
  }, [portfolioEquityCurve, benchmarkEquityCurve, dispersionRange, pinnedSymbols, symbolResults]);

  return (
    <div className="flex flex-col border border-border-main rounded-xl bg-bg-surface overflow-hidden mb-6 relative">
        <div className="p-3 border-b border-border-main flex items-center justify-between bg-bg-elevated/20">
             <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Portfolio Performance (Normalized %)</span>
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
                     <div key={sym} className="flex items-center gap-1.5 text-[10px]" style={{ color: pinColors[idx % pinColors.length] }}>
                         <div className="w-3 h-0.5 bg-current" />
                         {sym}
                     </div>
                 ))}
             </div>
        </div>
        <div className="relative h-[250px] w-full" ref={chartContainerRef} />
    </div>
  );
};
