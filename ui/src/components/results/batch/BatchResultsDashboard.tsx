// @ts-nocheck
import React from "react";
import * as LightweightCharts from "lightweight-charts";
import { BatchHeaderBar } from "./BatchHeaderBar";
import { PortfolioHeroStats } from "./PortfolioHeroStats";
import { PortfolioEquityChart } from "./PortfolioEquityChart";
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
        <div className="flex items-center gap-2 px-6 py-3 border-b border-border-main bg-bg-surface sticky top-0 z-30">
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
    <div className="flex flex-col h-full bg-bg-surface">
      <BatchHeaderBar />

      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
        <div className="p-4 lg:p-5 max-w-[1600px] w-full mx-auto space-y-6 pb-20">
        {/* 1. Hero Stats */}
        <PortfolioHeroStats />

        {/* 2. Portfolio Equity + Benchmark (Dominant Chart) */}
        <div className="w-full">
          <PortfolioEquityChart />
        </div>

        {/* 3. Portfolio Drawdown (full width) */}
        <div className="h-[300px] border border-border-main rounded-xl bg-bg-surface p-4 flex flex-col">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Portfolio Drawdown
          </h3>
          <div className="flex-1 relative">
            <BatchUnderwaterChartStub />
          </div>
        </div>

        {/* 4. Symbol Table */}
        <div className="min-h-[500px]">
          <SymbolPerformanceTable />
        </div>
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
        benchmarkProfitPct: data.benchmarkProfitPct ?? 0,
        profitFactor: data.profitFactor ?? 0,
        grossWin: data.grossWin ?? 0,
        grossLoss: data.grossLoss ?? 0,
        maxDrawdownPct: data.maxDrawdownPct,
        maxDrawdownValue: data.maxDrawdownValue ?? 0,
        sharpeRatio: data.sharpe,
        sortinoRatio: data.sortinoRatio ?? 0,
        calmarRatio: data.calmarRatio ?? 0,
        volatility: data.volatility ?? 0,
        expectancy: data.expectancy ?? 0,
        maxConsecWins: data.maxConsecWins ?? 0,
        winRate: data.winRate ?? 0,
        winCount: data.winCount ?? 0,
        lossCount: data.lossCount ?? 0,
        avgWin: data.avgWin ?? 0,
        avgLoss: data.avgLoss ?? 0,
        bestTrade: data.bestTrade ?? 0,
        worstTrade: data.worstTrade ?? 0,
        equityCurve: data.equityCurve ?? [],
        benchmarkCurve: [],
        underwaterCurve: data.underwaterCurve ?? [],
        trades: data.trades ?? [],
        exitReasons: data.exitReasons ?? {},
        filteredTrades: data.trades ?? [],
        activeFilter: null,
      });
    }
  }, [data, setResults]);
  return null;
};

// Simple Chart Stub for Batch Underwater to save complexity in this turn
const BatchUnderwaterChartStub = () => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<LightweightCharts.IChartApi | null>(null);
  const { portfolioEquityCurve } = useBatchResultsStore();

  React.useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    const initChart = () => {
      if (chartRef.current) return;
      if (container.clientWidth === 0) return;

      const { createChart, ColorType, AreaSeries } = LightweightCharts;
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#71717a",
        },
        grid: {
          vertLines: { visible: false },
          horzLines: { color: "rgba(255,255,255,0.05)" },
        },
        width: container.clientWidth || 600,
        height: container.clientHeight || 220,
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

      // Compute drawdown from equity curve
      let peak = -Infinity;
      const drawdownData = portfolioEquityCurve.map((p) => {
        if (p.value > peak) peak = p.value;
        const dd = ((p.value - peak) / peak) * 100;
        return { time: p.time, value: dd };
      });

      series.setData(drawdownData);
      chart.timeScale().fitContent();
      chartRef.current = chart;
    };

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
  }, [portfolioEquityCurve]);

  return <div ref={containerRef} className="absolute inset-0" />;
};
