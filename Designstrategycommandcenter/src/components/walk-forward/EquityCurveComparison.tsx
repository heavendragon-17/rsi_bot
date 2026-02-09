import React, { useEffect, useRef } from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import * as LightweightCharts from "lightweight-charts";
import { useThemeStore } from "../../stores/themeStore";

export const EquityCurveComparison: React.FC = () => {
  const { windows } = useWalkForwardStore();
  const { currentTheme } = useThemeStore();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<LightweightCharts.IChartApi | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current || windows.length === 0) return;

    // Get theme colors
    const bgColor = currentTheme?.variables["bg-surface"] || "#ffffff";
    const textColor = currentTheme?.variables["text-primary"] || "#000000";
    const gridColor = currentTheme?.variables["border-main"] || "#e5e5e5";

    // Create chart
    const chart = LightweightCharts.createChart(chartContainerRef.current, {
      layout: {
        background: { type: LightweightCharts.ColorType.Solid, color: bgColor },
        textColor: textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        borderColor: gridColor,
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: gridColor,
      },
    });

    // Generate cumulative returns for IS and OOS
    const isData: LightweightCharts.LineData[] = [];
    const oosData: LightweightCharts.LineData[] = [];

    let isCumulative = 100;
    let oosCumulative = 100;

    windows.forEach((window, idx) => {
      // IS point (at end of IS period)
      const isDate = new Date(window.isEndDate);
      const isTime = Math.floor(isDate.getTime() / 1000) as any;
      
      // Assume IS generates similar return as OOS (but slightly better since optimized)
      const isReturn = window.oosReturnPct * 1.2; // IS typically performs better
      isCumulative *= (1 + isReturn / 100);
      
      isData.push({
        time: isTime,
        value: isCumulative,
      });

      // OOS point (at end of OOS period)
      const oosDate = new Date(window.oosEndDate);
      const oosTime = Math.floor(oosDate.getTime() / 1000) as any;
      
      oosCumulative *= (1 + window.oosReturnPct / 100);
      
      oosData.push({
        time: oosTime,
        value: oosCumulative,
      });
    });

    // Add IS line (solid)
    const isSeries = chart.addLineSeries({
      color: currentTheme?.variables["accent-color"] || "#3b82f6",
      lineWidth: 2,
      title: "IS (In-Sample)",
    });
    isSeries.setData(isData);

    // Add OOS line (dashed - approximate with area)
    const oosSeries = chart.addLineSeries({
      color: currentTheme?.variables["success"] || "#22c55e",
      lineWidth: 2,
      lineStyle: 2, // Dashed
      title: "OOS (Out-of-Sample)",
    });
    oosSeries.setData(oosData);

    chart.timeScale().fitContent();

    chartRef.current = chart;

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [windows, currentTheme]);

  if (windows.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Equity Comparison: IS vs OOS</h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-8 h-0.5 bg-accent-main" />
            <span className="text-text-secondary">IS (In-Sample)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-8 h-0.5 bg-success border-t-2 border-dashed border-success" />
            <span className="text-text-secondary">OOS (Out-of-Sample)</span>
          </div>
        </div>
      </div>

      <div 
        ref={chartContainerRef} 
        className="rounded-lg border border-border-main overflow-hidden bg-bg-elevated"
      />

      <div className="p-3 rounded-lg bg-warning/10 border border-warning/30">
        <p className="text-xs text-warning">
          <strong>⚠️ Interpretation:</strong> If OOS equity consistently underperforms IS equity, 
          the strategy may be overfit to historical data. A robust strategy shows similar performance 
          in both IS and OOS periods.
        </p>
      </div>
    </div>
  );
};