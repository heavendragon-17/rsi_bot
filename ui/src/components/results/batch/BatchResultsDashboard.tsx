// @ts-nocheck
import React from "react";
import * as LightweightCharts from "lightweight-charts";
import { BatchHeaderBar } from "./BatchHeaderBar";
import { PortfolioHeroStats } from "./PortfolioHeroStats";
import { PortfolioEquityChart } from "./PortfolioEquityChart";
import { CorrelationMatrix } from "./CorrelationMatrix";
import { SymbolPerformanceTable } from "./SymbolPerformanceTable";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";
import { ResultsDashboard } from "../ResultsDashboard"; // Reuse Single Dashboard
import { ChevronLeft } from "lucide-react";
import { useResultsStore } from "../../../stores/resultsStore";

export const BatchResultsDashboard: React.FC = () => {
  const {
    selectedSymbol,
    selectSymbol,
    symbolResults,
    allocationMode,
    symbols,
  } = useBatchResultsStore();
  const { setResults } = useResultsStore();

  // If Drill-Down is active, switch to Single ResultsDashboard
  if (selectedSymbol) {
    // Hydrate the single results store with the selected symbol's data
    // In a real app, this might fetch data. Here we pull from our mock batch store.
    const symData = symbolResults.find((s) => s.symbol === selectedSymbol);

    // We need to shape this into the ResultsState expected by ResultsDashboard
    if (symData) {
      // This side-effect inside render is generally bad practice but acceptable for this mocked rapid prototype
      // Ideally use a useEffect or event handler.
      // Let's use an Effect to trigger the hydration ONCE when selectedSymbol changes.
    }

    return (
      <div className="flex flex-col h-full bg-bg-surface overflow-hidden">
        {/* Breadcrumb Header */}
        <div className="flex items-center gap-2 p-4 border-b border-border-main bg-bg-surface sticky top-0 z-30">
          <button
            onClick={() => selectSymbol(null)}
            className="flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
          >
            <ChevronLeft size={16} />
            Back to Portfolio
          </button>
          <span className="text-text-muted">/</span>
          <span className="text-sm font-bold text-accent-main">
            {selectedSymbol}
          </span>
        </div>

        {/* Reuse the Single Dashboard */}
        <div className="flex-1 overflow-hidden">
          <SingleResultHydrator data={symData} />
          <ResultsDashboard />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-bg-surface overflow-y-auto overflow-x-hidden custom-scrollbar">
      <BatchHeaderBar />

      <div className="p-6 max-w-[1600px] w-full mx-auto space-y-6 pb-20">
        {/* 1. Hero Stats */}
        <PortfolioHeroStats />

        {/* 2. Portfolio Equity + Benchmark (Dominant Chart) */}
        <div className="w-full">
          <PortfolioEquityChart />
        </div>

        {/* 3. Charts Row (Underwater + Correlation) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[400px]">
          {/* Reusing Underwater Chart logic but we need a Batch specific one or adapt the generic one?
                    The Generic one reads from resultsStore. We are in Batch mode.
                    Actually, we can create a `BatchUnderwaterChart` or just let `PortfolioEquityChart` handle it?
                    The layout asks for separate charts.
                    Let's create a simplified wrapper or duplicate for isolation.
                    Actually, we can just use the PortfolioEquityChart which renders 2 charts? No, that was Single mode.
                    Task 5 Layout:
                    Row 2: Portfolio Equity
                    Row 3: Underwater (50%) + Correlation (50%)
                */}

          {/* Underwater Wrapper */}
          <div className="h-full border border-border-main rounded-xl bg-bg-surface p-4 flex flex-col">
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
              Portfolio Drawdown
            </h3>
            <div className="flex-1 bg-bg-elevated/10 rounded relative flex items-center justify-center text-text-muted text-sm">
              {/*
                            Ideally reusing logic from EquityUnderwaterChart but mapped to batch data.
                            For MVP/Proto, I will put a placeholder or basic re-implementation.
                        */}
              <BatchUnderwaterChartStub />
            </div>
          </div>

          {/* Correlation Matrix */}
          <div className="h-full">
            <CorrelationMatrix />
          </div>
        </div>

        {/* 4. Symbol Table */}
        <div className="min-h-[500px]">
          <SymbolPerformanceTable />
        </div>
      </div>
    </div>
  );
};

// Helper to inject data into the Single Store when drilling down
const SingleResultHydrator: React.FC<{ data: any }> = ({ data }) => {
  const { setResults } = useResultsStore();
  React.useEffect(() => {
    if (data) {
      setResults({
        netProfit: data.netPnL,
        netProfitPct: data.netPnLPct,
        profitFactor: 1.5, // Mock derived
        maxDrawdownPct: data.maxDrawdownPct,
        maxDrawdownValue: 1000, // Mock
        sharpeRatio: data.sharpe,
        equityCurve: data.equityCurve,
        benchmarkCurve: data.equityCurve.map((x: any) => ({
          ...x,
          value: x.value * 0.9,
        })), // Mock bench
        underwaterCurve: data.equityCurve.map((x: any) => ({
          ...x,
          value: -Math.random() * 5,
        })), // Mock underwater
        trades: [], // would be populated
        exitReasons: { TP1: 10, SL: 5 }, // Mock
      });
    }
  }, [data, setResults]);
  return null;
};

// Simple Chart Stub for Batch Underwater to save complexity in this turn
const BatchUnderwaterChartStub = () => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const { portfolioEquityCurve } = useBatchResultsStore();

  React.useEffect(() => {
    if (!containerRef.current) return;
    const { createChart, ColorType, AreaSeries } = LightweightCharts;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#71717a",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "rgba(255,255,255,0.05)" },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      timeScale: { visible: true, borderVisible: false },
      rightPriceScale: { borderVisible: false },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: "#ef4444",
      topColor: "#ef444411",
      bottomColor: "#ef444466",
      lineWidth: 1,
      priceFormat: { type: "percent" },
    });

    // Mock drawdown from equity curve
    let peak = -Infinity;
    const drawdownData = portfolioEquityCurve.map((p) => {
      if (p.value > peak) peak = p.value;
      const dd = ((p.value - peak) / peak) * 100;
      return { time: p.time, value: dd };
    });

    series.setData(drawdownData);
    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current)
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [portfolioEquityCurve]);

  return <div ref={containerRef} className="w-full h-full" />;
};
