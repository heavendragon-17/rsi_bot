import React from "react";
import { BatchHeaderBar } from "./BatchHeaderBar";
import { PortfolioHeroStats } from "./PortfolioHeroStats";
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
