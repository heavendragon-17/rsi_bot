import React from "react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";

const MetricCell: React.FC<{
  label: string;
  value: string | number;
  subValue?: string;
  highlight?: "success" | "danger" | "neutral";
}> = ({ label, value, subValue, highlight }) => (
  <div className="flex flex-col gap-1.5 p-4 border-r last:border-r-0 border-border-main/40">
    <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted whitespace-nowrap">
      {label}
    </span>
    <div className="flex items-baseline gap-1">
      <span
        className={cn(
          "text-base font-bold font-mono",
          highlight === "success" && "text-success",
          highlight === "danger" && "text-danger"
        )}
      >
        {value}
      </span>
      {subValue && (
        <span className="text-xs text-text-secondary">{subValue}</span>
      )}
    </div>
  </div>
);

export const MetricsGrid: React.FC = () => {
  const {
    sortinoRatio,
    calmarRatio,
    volatility,
    expectancy,
    maxConsecWins,
    winRate,
    winCount,
    lossCount,
    avgWin,
    avgLoss,
    bestTrade,
    worstTrade,
  } = useResultsStore();

  const totalTrades = winCount + lossCount;

  return (
    <div className="border border-border-main rounded-xl bg-bg-surface overflow-hidden shadow-sm">
      {/* Row 1: Risk / ratio stats */}
      <div className="grid grid-cols-5 border-b border-border-main/40">
        <MetricCell label="Sortino" value={sortinoRatio.toFixed(2)} />
        <MetricCell label="Calmar" value={calmarRatio.toFixed(2)} />
        <MetricCell label="Volatility" value={`${volatility.toFixed(2)}%`} />
        <MetricCell
          label="Expectancy"
          value={`$${expectancy.toFixed(2)}`}
          subValue="/ trade"
          highlight={expectancy > 0 ? "success" : "danger"}
        />
        <MetricCell label="Consec. Wins" value={maxConsecWins} />
      </div>

      {/* Row 2: Trade stats */}
      <div className="grid grid-cols-5">
        <MetricCell
          label="Avg Win"
          value={`$${avgWin.toFixed(2)}`}
          highlight="success"
        />
        <MetricCell
          label="Avg Loss"
          value={`-$${Math.abs(avgLoss).toFixed(2)}`}
          highlight="danger"
        />
        <MetricCell
          label="Best Trade"
          value={`$${bestTrade.toFixed(2)}`}
          highlight="success"
        />
        <MetricCell
          label="Worst Trade"
          value={`-$${Math.abs(worstTrade).toFixed(2)}`}
          highlight="danger"
        />
        <MetricCell
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          subValue={`(${winCount}/${totalTrades})`}
          highlight={winRate > 50 ? "success" : "neutral"}
        />
      </div>
    </div>
  );
};
