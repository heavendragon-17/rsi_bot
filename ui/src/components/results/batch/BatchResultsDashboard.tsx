import React from "react";
import * as LightweightCharts from "lightweight-charts";
import { BatchHeaderBar } from "./BatchHeaderBar";
import { PortfolioHeroStats } from "./PortfolioHeroStats";
import { PortfolioEquityChart } from "./PortfolioEquityChart";
import { SymbolPerformanceTable } from "./SymbolPerformanceTable";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";
import { ResultsDashboard } from "../ResultsDashboard";
import { ChevronLeft } from "lucide-react";
import { useResultsStore } from "../../../stores/resultsStore";

export const BatchResultsDashboard: React.FC = () => {
  const { selectedSymbol, selectSymbol, symbolResults } =
    useBatchResultsStore();

  // Drill-down: render single-pair dashboard for selected symbol
  if (selectedSymbol) {
    const symData = symbolResults.find((s) => s.symbol === selectedSymbol);

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

        <div className="flex-1 overflow-hidden">
          <SingleResultHydrator data={symData} />
          <ResultsDashboard />
        </div>
      </div>
    );
  }

  // Portfolio overview: hero stats + symbol table
  return (
    <div className="flex flex-col h-full bg-bg-surface overflow-y-auto overflow-x-hidden custom-scrollbar">
      <BatchHeaderBar />

      <div className="p-6 max-w-[1800px] w-full mx-auto space-y-6 pb-20">
        <PortfolioHeroStats />

        {/* Portfolio Equity + Benchmark */}
        <div className="w-full">
          <PortfolioEquityChart />
        </div>

        {/* Portfolio Drawdown */}
        <div className="border border-border-main rounded-xl bg-bg-surface p-4 flex flex-col">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Portfolio Drawdown
          </h3>
          <div className="h-[200px] relative">
            <BatchUnderwaterChartStub />
          </div>
        </div>

        <div className="min-h-[500px]">
          <SymbolPerformanceTable />
        </div>
      </div>
    </div>
  );
};

/** Hydrates the single-pair resultsStore from batch symbol data. */
const SingleResultHydrator: React.FC<{ data: any }> = ({ data }) => {
  const { setResults } = useResultsStore();

  React.useEffect(() => {
    if (!data) return;

    setResults({
      netProfit: data.netPnL,
      netProfitPct: data.netPnLPct,
      benchmarkProfitPct: data.benchmarkProfitPct ?? 0,
      profitFactor: data.profitFactor ?? 0,
      maxDrawdownPct: data.maxDrawdownPct,
      maxDrawdownValue: data.maxDrawdownValue ?? 0,
      sharpeRatio: data.sharpe,
      sortinoRatio: data.sortinoRatio ?? 0,
      calmarRatio: data.calmarRatio ?? 0,
      volatility: data.volatility ?? 0,
      expectancy: data.expectancy ?? 0,
      maxConsecWins: data.maxConsecWins ?? 0,
      winRate: data.winRate,
      winCount: data.trades?.filter((t: any) => t.pnl >= 0).length ?? 0,
      lossCount: data.trades?.filter((t: any) => t.pnl < 0).length ?? 0,
      avgWin: data.avgWin ?? 0,
      avgLoss: data.avgLoss ?? 0,
      bestTrade: data.bestTrade ?? 0,
      worstTrade: data.worstTrade ?? 0,
      grossWin: data.grossWin ?? 0,
      grossLoss: data.grossLoss ?? 0,
      equityCurve: data.equityCurve ?? [],
      benchmarkCurve: [],
      underwaterCurve: data.underwaterCurve ?? [],
      exitReasons: data.exitReasons ?? {},
      trades: data.trades ?? [],
    });
  }, [data, setResults]);

  return null;
};

/** Simplified drawdown chart derived from portfolio equity curve. */
const BatchUnderwaterChartStub: React.FC = () => {
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
