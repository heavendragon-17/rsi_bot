// @ts-nocheck
import React, { useEffect, useRef } from "react";
import * as LightweightCharts from "lightweight-charts";
import { useResultsStore } from "../../stores/resultsStore";

export const EquityUnderwaterChart: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const underwaterContainerRef = useRef<HTMLDivElement>(null);

  const chartRef = useRef<LightweightCharts.IChartApi | null>(null);
  const underwaterChartRef = useRef<LightweightCharts.IChartApi | null>(null);

  const { equityCurve, benchmarkCurve, underwaterCurve, netProfit } =
    useResultsStore();

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
          type: "percent",
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
        <h2 className="text-sm font-semibold text-text-primary mb-3 uppercase tracking-wider">
          Equity Curve
        </h2>
        <div
          id="equity-chart"
          ref={chartContainerRef}
          className="w-full rounded-lg border border-border-main bg-bg-elevated/50"
        />
      </div>

      {/* Drawdown (Underwater) */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary mb-3 uppercase tracking-wider">
          Underwater Curve (Drawdown)
        </h2>
        <div
          id="drawdown-chart"
          ref={underwaterContainerRef}
          className="w-full rounded-lg border border-border-main bg-bg-elevated/50"
        />
      </div>
    </div>
  );
};
