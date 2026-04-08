// @ts-nocheck
import React from "react";
import CountUp from "react-countup";
import { motion } from "motion/react";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";

export const NetProfitHero: React.FC = () => {
  const { netProfit, netProfitPct, benchmarkProfitPct, winCount, lossCount } = useResultsStore();

  const isPositive = netProfit >= 0;
  const beatBenchmark = netProfitPct > benchmarkProfitPct;
  const colorClass = isPositive ? "text-success" : "text-danger";
  const totalTrades = winCount + lossCount;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden bg-bg-elevated/40 border border-border-main rounded-xl px-6 py-5 shadow-sm group hover:border-accent-main/30 transition-colors"
    >
      {/* Title */}
      <span className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
        Net Profit
      </span>

      {/* Value Row */}
      <div className={cn("flex items-baseline gap-2.5 mt-1.5", colorClass)}>
        <span className="text-[36px] font-bold tracking-tight leading-none">
          {isPositive ? "+" : "-"}$
          <CountUp end={Math.abs(netProfit)} decimals={2} separator="," duration={1} />
        </span>
        <span className="text-[18px] font-normal">
          (<CountUp
            end={netProfitPct}
            decimals={1}
            prefix={isPositive ? "+" : ""}
            suffix="%"
            duration={1}
          />)
        </span>
      </div>

      {/* Benchmark + trade count */}
      <div className="flex items-center gap-3 mt-1.5">
        <p className={cn("text-[11px] font-medium", beatBenchmark ? "text-success" : "text-danger")}>
          vs B&amp;H: {benchmarkProfitPct > 0 ? "+" : ""}
          {benchmarkProfitPct.toFixed(1)}%
        </p>
        {totalTrades > 0 && (
          <p className="text-[10px] text-text-muted">
            {totalTrades} trades · {winCount}W / {lossCount}L
          </p>
        )}
      </div>

      {/* Background glow */}
      <div
        className={cn(
          "absolute -right-6 -bottom-6 w-32 h-32 rounded-full blur-3xl opacity-15 pointer-events-none",
          isPositive ? "bg-success" : "bg-danger"
        )}
      />
    </motion.div>
  );
};
