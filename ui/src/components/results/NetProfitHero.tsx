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
      <span className="text-xs font-bold uppercase tracking-widest text-text-secondary">
        Net Profit
      </span>

      {/* Value Row */}
      <div className={cn("flex items-baseline gap-3 mt-2", colorClass)}>
        <span className="text-4xl font-extrabold tracking-tight leading-none">
          {isPositive ? "+" : "-"}$
          <CountUp end={Math.abs(netProfit)} decimals={2} separator="," duration={1} />
        </span>
        <span className="text-lg font-semibold">
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
      <div className="flex items-center gap-3 mt-2">
        <p className={cn("text-xs font-semibold", beatBenchmark ? "text-success" : "text-danger")}>
          vs B&amp;H: {benchmarkProfitPct > 0 ? "+" : ""}
          {benchmarkProfitPct.toFixed(1)}%
        </p>
        {totalTrades > 0 && (
          <p className="text-[11px] text-text-secondary">
            {totalTrades} trades · {winCount}W / {lossCount}L
          </p>
        )}
      </div>

      {/* Background glow */}
      <div
        className={cn(
          "absolute -right-8 -bottom-8 w-24 h-24 rounded-full blur-2xl opacity-10 pointer-events-none",
          isPositive ? "bg-success" : "bg-danger"
        )}
      />
    </motion.div>
  );
};
