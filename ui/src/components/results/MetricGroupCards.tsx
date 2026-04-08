import React from "react";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";

const MetricRow: React.FC<{
  label: string;
  value: string;
  subValue?: string;
  color?: "success" | "danger" | "neutral";
}> = ({ label, value, subValue, color }) => (
  <div className="flex items-center justify-between px-3.5 py-2 text-[13px] border-b border-border-main/30 last:border-b-0">
    <span className="text-text-secondary font-medium">{label}</span>
    <div className="flex flex-col items-end gap-0.5">
      <span
        className={cn(
          "font-bold font-mono",
          color === "success" && "text-success",
          color === "danger" && "text-danger",
          color === "neutral" && "text-text-primary"
        )}
      >
        {value}
      </span>
      {subValue && (
        <span className="text-[10px] text-text-muted font-normal leading-none">{subValue}</span>
      )}
    </div>
  </div>
);

interface CardGroup {
  icon: string;
  title: string;
  metrics: { label: string; value: string; subValue?: string; color?: "success" | "danger" | "neutral" }[];
}

export const MetricGroupCards: React.FC = () => {
  const {
    profitFactor,
    winRate,
    winCount,
    lossCount,
    expectancy,
    avgWin,
    avgLoss,
    bestTrade,
    worstTrade,
    maxDrawdownPct,
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    volatility,
    maxConsecWins,
    grossWin,
    grossLoss,
  } = useResultsStore();

  const totalTrades = winCount + lossCount;
  const wlLabel = `${winCount}W / ${lossCount}L`;

  const groups: CardGroup[] = [
    {
      icon: "\u{1F4C8}",
      title: "PERFORMANCE",
      metrics: [
        { label: "Profit Factor", value: profitFactor.toFixed(2), color: profitFactor >= 1.5 ? "success" : profitFactor >= 1.0 ? "neutral" : "danger" },
        { label: "Win Rate", value: `${winRate.toFixed(1)}%`, subValue: wlLabel, color: winRate > 50 ? "success" : "neutral" },
        { label: "Expectancy", value: `$${expectancy.toFixed(2)}`, color: expectancy > 0 ? "success" : "danger" },
        { label: "Avg Win", value: `$${avgWin.toFixed(2)}`, color: "success" },
        { label: "Avg Loss", value: `-$${Math.abs(avgLoss).toFixed(2)}`, color: "danger" },
        { label: "Best Trade", value: `$${bestTrade.toFixed(2)}`, color: "success" },
        { label: "Worst Trade", value: `-$${Math.abs(worstTrade).toFixed(2)}`, color: "danger" },
      ],
    },
    {
      icon: "\u{1F6E1}",
      title: "RISK",
      metrics: [
        { label: "Max Drawdown", value: `${maxDrawdownPct.toFixed(2)}%`, color: "danger" },
        { label: "Sharpe", value: sharpeRatio.toFixed(2), color: sharpeRatio >= 1.0 ? "success" : "neutral" },
        { label: "Sortino", value: sortinoRatio.toFixed(2), color: "neutral" },
        { label: "Calmar", value: calmarRatio.toFixed(2), color: "neutral" },
        { label: "Volatility", value: `${volatility.toFixed(2)}%`, color: "neutral" },
        { label: "Consec. Wins", value: String(maxConsecWins), color: "neutral" },
      ],
    },
    {
      icon: "\u{26A1}",
      title: "ACTIVITY",
      metrics: [
        { label: "Total Trades", value: `${totalTrades}`, subValue: wlLabel, color: "neutral" },
        { label: "Gross Win", value: `$${grossWin.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`, color: "success" },
        { label: "Gross Loss", value: `$${grossLoss.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`, color: "danger" },
      ],
    },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {groups.map((group, i) => (
        <motion.div
          key={group.title}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 + i * 0.05 }}
          className="bg-bg-elevated/40 border border-border-main rounded-xl overflow-hidden shadow-sm"
        >
          {/* Card header */}
          <div className="bg-bg-elevated/40 px-3.5 py-2.5 flex items-center gap-2 text-text-secondary border-b border-border-main/50">
            <span className="text-sm">{group.icon}</span>
            <span className="text-[11px] font-bold uppercase tracking-wider">
              {group.title}
            </span>
          </div>

          {/* Metric rows */}
          {group.metrics.map((m) => (
            <MetricRow
              key={m.label}
              label={m.label}
              value={m.value}
              subValue={m.subValue}
              color={m.color}
            />
          ))}
        </motion.div>
      ))}
    </div>
  );
};
