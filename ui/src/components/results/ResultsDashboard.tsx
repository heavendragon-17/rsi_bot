import React from "react";
import { HeaderBar } from "./HeaderBar";
import { NetProfitHero } from "./NetProfitHero";
import { MetricGroupCard } from "./MetricGroupCard";
import { EquityUnderwaterChart } from "./EquityUnderwaterChart";
import { ExitReasonsBar } from "./ExitReasonsBar";
import { TradesTable } from "./TradesTable";
import { useResultsStore } from "../../stores/resultsStore";
import { TrendingUp, ShieldAlert, Activity } from "lucide-react";

const usePerformanceMetrics = () => {
  const s = useResultsStore();
  return [
    { label: "Profit Factor", value: s.profitFactor.toFixed(2), highlight: s.profitFactor >= 1.5 ? "success" as const : s.profitFactor < 1 ? "danger" as const : "neutral" as const },
    { label: "Win Rate", value: `${s.winRate.toFixed(1)}%`, subValue: `(${s.winCount}/${s.winCount + s.lossCount})`, highlight: s.winRate > 50 ? "success" as const : "neutral" as const },
    { label: "Expectancy", value: `$${s.expectancy.toFixed(2)}`, subValue: "/ trade", highlight: s.expectancy > 0 ? "success" as const : "danger" as const },
    { label: "Avg Win", value: `$${s.avgWin.toFixed(2)}`, highlight: "success" as const },
    { label: "Avg Loss", value: `-$${Math.abs(s.avgLoss).toFixed(2)}`, highlight: "danger" as const },
    { label: "Best Trade", value: `$${s.bestTrade.toFixed(2)}`, highlight: "success" as const },
    { label: "Worst Trade", value: `-$${Math.abs(s.worstTrade).toFixed(2)}`, highlight: "danger" as const },
  ];
};

const useRiskMetrics = () => {
  const s = useResultsStore();
  return [
    { label: "Max Drawdown", value: `${s.maxDrawdownPct.toFixed(2)}%`, subValue: `($${s.maxDrawdownValue.toLocaleString()})`, highlight: "danger" as const },
    { label: "Sharpe Ratio", value: s.sharpeRatio.toFixed(2), highlight: s.sharpeRatio >= 1 ? "success" as const : s.sharpeRatio < 0 ? "danger" as const : "neutral" as const },
    { label: "Sortino Ratio", value: s.sortinoRatio.toFixed(2) },
    { label: "Calmar Ratio", value: s.calmarRatio.toFixed(2) },
    { label: "Volatility", value: `${s.volatility.toFixed(2)}%` },
    { label: "Consec. Wins", value: String(s.maxConsecWins) },
  ];
};

const useActivityMetrics = () => {
  const s = useResultsStore();
  const total = s.winCount + s.lossCount;
  return [
    { label: "Total Trades", value: String(total), subValue: `${s.winCount}W / ${s.lossCount}L` },
    { label: "Gross Win", value: `$${s.grossWin.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, highlight: "success" as const },
    { label: "Gross Loss", value: `$${s.grossLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, highlight: "danger" as const },
  ];
};

export const ResultsDashboard: React.FC = () => {
  const performanceMetrics = usePerformanceMetrics();
  const riskMetrics = useRiskMetrics();
  const activityMetrics = useActivityMetrics();

  return (
    <div className="flex flex-col h-full bg-bg-surface overflow-y-auto overflow-x-hidden custom-scrollbar">
      <HeaderBar />

      <div className="p-4 lg:p-6 max-w-[1800px] w-full mx-auto space-y-5 pb-20">
        {/* Row 1: Net Profit Hero */}
        <NetProfitHero />

        {/* Row 2: Metric Groups — 3 columns */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <MetricGroupCard
            title="Performance"
            icon={<TrendingUp size={14} />}
            metrics={performanceMetrics}
          />
          <MetricGroupCard
            title="Risk"
            icon={<ShieldAlert size={14} />}
            metrics={riskMetrics}
          />
          <MetricGroupCard
            title="Activity"
            icon={<Activity size={14} />}
            metrics={activityMetrics}
          />
        </div>

        {/* Row 3: Equity + Underwater charts */}
        <EquityUnderwaterChart />

        {/* Row 4: Exit Reasons — compact stacked bar */}
        <ExitReasonsBar />

        {/* Row 5: Trades Table */}
        <div>
          <h3 className="text-xs font-semibold text-text-secondary mb-3 uppercase tracking-wider">
            Trade Journal
          </h3>
          <TradesTable />
        </div>
      </div>
    </div>
  );
};
