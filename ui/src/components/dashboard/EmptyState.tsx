import React from "react";
import { Play, Clock } from "lucide-react";
import { useBacktestStore, BacktestConfig } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

export const EmptyState: React.FC = () => {
  const { recentConfigs, loadConfig } = useBacktestStore();

  return (
    <div className="w-full h-full flex flex-col items-center justify-center p-8">
      <div className="w-24 h-24 rounded-full bg-accent-main/10 flex items-center justify-center mb-6 ring-4 ring-accent-main/5 animate-pulse-slow">
        <Play size={48} className="text-accent-main ml-2 fill-current" />
      </div>
      
      <h2 className="text-2xl font-bold text-text-primary mb-2">Run your first backtest</h2>
      <p className="text-text-secondary max-w-md text-center mb-8">
        Configure your strategy in the sidebar and press Run to analyze performance across historical data.
      </p>

      {recentConfigs.length > 0 && (
        <div className="w-full max-w-md">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <Clock size={12} />
                Recent Configs
            </h3>
            <div className="flex flex-col gap-2">
                {recentConfigs.map((config) => (
                    <button
                        key={config.id}
                        onClick={() => loadConfig(config)}
                        className="flex items-center justify-between p-3 rounded-lg bg-bg-elevated/50 hover:bg-bg-elevated border border-transparent hover:border-accent-main/30 transition-all group text-left"
                    >
                        <div>
                            <div className="text-sm font-medium text-text-primary">
                                {config.symbol} • {config.timeframe} • {config.strategy}
                            </div>
                            <div className="text-xs text-text-secondary mt-0.5">
                                ${parseInt(config.capital).toLocaleString()} • {config.leverage}x
                            </div>
                        </div>
                        <div className="text-xs text-text-muted group-hover:text-accent-main transition-colors">
                            Load
                        </div>
                    </button>
                ))}
            </div>
        </div>
      )}
    </div>
  );
};
