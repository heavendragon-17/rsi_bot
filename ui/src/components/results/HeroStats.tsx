// @ts-nocheck
import React from "react";
import CountUp from "react-countup";
import { useResultsStore } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { TrendingUp, AlertTriangle, Scale, Target } from "lucide-react";

const HeroCard: React.FC<{
    title: string;
    value: React.ReactNode;
    subtitle: React.ReactNode;
    colorClass?: string;
    icon?: React.ReactNode;
}> = ({ title, value, subtitle, colorClass, icon }) => (
    <div className="flex flex-col p-4 bg-bg-elevated/40 border border-border-main rounded-xl shadow-sm relative overflow-hidden group hover:border-accent-main/30 transition-colors">
        <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">{title}</span>
            {icon && <div className="text-text-muted/50 group-hover:text-text-secondary transition-colors">{icon}</div>}
        </div>
        <div className={cn("text-2xl font-bold font-mono tracking-tight", colorClass)}>
            {value}
        </div>
        <div className="mt-1 text-xs text-text-secondary flex items-center gap-1.5">
            {subtitle}
        </div>

        {/* Subtle background glow based on sentiment */}
        <div className={cn(
            "absolute -right-4 -bottom-4 w-16 h-16 rounded-full blur-2xl opacity-10 pointer-events-none",
            colorClass?.includes("success") ? "bg-success" :
            colorClass?.includes("danger") ? "bg-danger" :
            "bg-accent-main"
        )} />
    </div>
);

export const HeroStats: React.FC = () => {
  const {
      netProfit,
      netProfitPct,
      benchmarkProfitPct,
      profitFactor,
      grossWin,
      grossLoss,
      maxDrawdownPct,
      maxDrawdownValue,
      sharpeRatio
  } = useResultsStore();

  const isProfitPositive = netProfit >= 0;
  const beatBenchmark = netProfitPct > benchmarkProfitPct;

  // Profit Factor Logic
  let pfColor = "text-danger";
  if (profitFactor >= 1.5) pfColor = "text-success";
  else if (profitFactor >= 1.0) pfColor = "text-warning";

  // Sharpe Logic
  let sharpeColor = "text-danger";
  if (sharpeRatio >= 1.0) sharpeColor = "text-success";
  else if (sharpeRatio >= 0) sharpeColor = "text-warning";

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4 sm:mb-6">
        {/* Net Profit */}
        <HeroCard
            title="Net Profit"
            value={
                <div className="flex items-baseline gap-2">
                    <span>{isProfitPositive ? "+" : "-"}$<CountUp end={Math.abs(netProfit)} decimals={2} separator="," duration={1} /></span>
                    <span className="text-sm font-normal opacity-80">
                        (<CountUp end={netProfitPct} decimals={1} prefix={isProfitPositive ? "+" : ""} suffix="%" duration={1} />)
                    </span>
                </div>
            }
            colorClass={isProfitPositive ? "text-success" : "text-danger"}
            subtitle={
                <span className={cn("font-medium", beatBenchmark ? "text-success" : "text-danger")}>
                    vs B&H: {benchmarkProfitPct > 0 ? "+" : ""}{benchmarkProfitPct.toFixed(1)}%
                </span>
            }
            icon={<TrendingUp size={16} />}
        />

        {/* Profit Factor */}
        <HeroCard
            title="Profit Factor"
            value={<CountUp end={profitFactor} decimals={2} duration={1} />}
            colorClass={pfColor}
            subtitle={
                <span>
                   <span className="text-success">${(grossWin/1000).toFixed(1)}k</span> / <span className="text-danger">${(grossLoss/1000).toFixed(1)}k</span> GW/GL
                </span>
            }
            icon={<Scale size={16} />}
        />

        {/* Max Drawdown */}
        <HeroCard
            title="Max Drawdown"
            value={
                <span>
                    <CountUp end={maxDrawdownPct} decimals={2} suffix="%" duration={1} />
                </span>
            }
            colorClass="text-danger"
            subtitle={<span>Peak loss: ${maxDrawdownValue.toLocaleString()}</span>}
            icon={<AlertTriangle size={16} />}
        />

        {/* Sharpe Ratio */}
        <HeroCard
            title="Sharpe Ratio"
            value={<CountUp end={sharpeRatio} decimals={2} duration={1} />}
            colorClass={sharpeColor}
            subtitle={<span>Risk-adj return</span>}
            icon={<Target size={16} />}
        />
    </div>
  );
};
