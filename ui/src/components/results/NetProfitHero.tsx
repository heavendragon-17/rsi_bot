import React from "react";
import CountUp from "react-countup";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { TrendingUp } from "lucide-react";

export const NetProfitHero: React.FC = () => {
  const { netProfit, netProfitPct, benchmarkProfitPct } = useResultsStore();

  const isPositive = netProfit >= 0;
  const beatBenchmark = netProfitPct > benchmarkProfitPct;

  return (
    <div className="relative overflow-hidden rounded-xl border border-border-main bg-bg-elevated/40 p-6 shadow-sm group hover:border-accent-main/30 transition-colors">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Net Profit
        </span>
        <div className="text-text-muted/50 group-hover:text-text-secondary transition-colors">
          <TrendingUp size={18} />
        </div>
      </div>

      <div
        className={cn(
          "text-5xl font-bold font-mono tracking-tight leading-none mt-3",
          isPositive ? "text-success" : "text-danger"
        )}
      >
        <span>
          {isPositive ? "+" : "-"}$
          <CountUp end={Math.abs(netProfit)} decimals={2} separator="," duration={1} />
        </span>
        <span className="text-2xl font-normal opacity-75 ml-3">
          (
          <CountUp
            end={netProfitPct}
            decimals={1}
            prefix={isPositive ? "+" : ""}
            suffix="%"
            duration={1}
          />
          )
        </span>
      </div>

      <div className="mt-3 text-xs text-text-secondary flex items-center gap-1.5">
        <span className={cn("font-medium", beatBenchmark ? "text-success" : "text-danger")}>
          vs B&amp;H: {benchmarkProfitPct > 0 ? "+" : ""}
          {benchmarkProfitPct.toFixed(1)}%
        </span>
      </div>

      {/* Background glow */}
      <div
        className={cn(
          "absolute -right-8 -bottom-8 w-28 h-28 rounded-full blur-3xl opacity-10 pointer-events-none",
          isPositive ? "bg-success" : "bg-danger"
        )}
      />
    </div>
  );
};
