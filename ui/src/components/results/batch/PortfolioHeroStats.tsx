// @ts-nocheck
import React from "react";
import CountUp from "react-countup";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";
import { cn } from "../../../lib/utils";
import { TrendingUp, AlertTriangle, Layers, Target, Activity } from "lucide-react";

const HeroCard: React.FC<{
    title: string;
    value: React.ReactNode;
    subtitle: React.ReactNode;
    colorClass?: string;
    icon?: React.ReactNode;
}> = ({ title, value, subtitle, colorClass, icon }) => (
    <div className="flex flex-col p-5 bg-bg-elevated/40 border border-border-main rounded-xl shadow-sm relative overflow-hidden group hover:border-accent-main/30 transition-colors">
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

        <div className={cn(
            "absolute -right-4 -bottom-4 w-16 h-16 rounded-full blur-2xl opacity-10 pointer-events-none",
            colorClass?.includes("success") ? "bg-success" :
            colorClass?.includes("danger") ? "bg-danger" :
            "bg-accent-main"
        )} />
    </div>
);

export const PortfolioHeroStats: React.FC = () => {
  const {
      totalPnL,
      totalPnLPct,
      benchmarkPnLPct,
      portfolioSharpe,
      portfolioMaxDrawdownPct,
      portfolioMaxDrawdownValue,
      avgCorrelation,
      bestSymbol
  } = useBatchResultsStore();

  const isProfitPositive = totalPnL >= 0;

  // Sharpe Logic
  let sharpeColor = "text-danger";
  if (portfolioSharpe >= 1.0) sharpeColor = "text-success";
  else if (portfolioSharpe >= 0) sharpeColor = "text-warning";

  // Correlation Logic
  // > 0.7 = Danger, < 0.3 = Success, Else Warning
  let corrColor = "text-warning";
  let corrLabel = "Moderate";
  if (avgCorrelation > 0.7) { corrColor = "text-danger"; corrLabel = "High Risk"; }
  else if (avgCorrelation < 0.3) { corrColor = "text-success"; corrLabel = "Diversified"; }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3 sm:gap-4 mb-4 sm:mb-6">
        {/* Total PnL */}
        <HeroCard
            title="Total PnL"
            value={
                <div className="flex items-baseline gap-2">
                    <span>{isProfitPositive ? "+" : "-"}$<CountUp end={Math.abs(totalPnL)} decimals={0} separator="," duration={1} /></span>
                </div>
            }
            colorClass={isProfitPositive ? "text-success" : "text-danger"}
            subtitle={
                <span className="font-medium">
                   {isProfitPositive ? "+" : ""}{totalPnLPct.toFixed(1)}% (vs Idx: {(benchmarkPnLPct > 0 ? "+" : "") + benchmarkPnLPct.toFixed(1)}%)
                </span>
            }
            icon={<Layers size={16} />}
        />

        {/* Portfolio Sharpe */}
        <HeroCard
            title="Portf. Sharpe"
            value={<CountUp end={portfolioSharpe} decimals={2} duration={1} />}
            colorClass={sharpeColor}
            subtitle={<span>Risk-adj Return</span>}
            icon={<Target size={16} />}
        />

        {/* Max Drawdown */}
        <HeroCard
            title="Max Drawdown"
            value={
                <span>
                    <CountUp end={portfolioMaxDrawdownPct} decimals={2} suffix="%" duration={1} />
                </span>
            }
            colorClass="text-danger"
            subtitle={<span>Peak loss: ${portfolioMaxDrawdownValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}
            icon={<AlertTriangle size={16} />}
        />

        {/* Avg Correlation */}
        <HeroCard
            title="Avg Correlation"
            value={<CountUp end={avgCorrelation} decimals={2} duration={1} />}
            colorClass={corrColor}
            subtitle={<span className={corrColor}>⚠ {corrLabel}</span>}
            icon={<Activity size={16} />}
        />

        {/* Best Symbol */}
        <HeroCard
            title="Best Symbol"
            value={<span className="text-xl">{bestSymbol.symbol}</span>}
            colorClass="text-success"
            subtitle={<span>+{bestSymbol.pnlPct.toFixed(1)}%</span>}
            icon={<TrendingUp size={16} />}
        />
    </div>
  );
};
