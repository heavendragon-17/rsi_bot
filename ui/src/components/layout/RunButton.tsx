import React from "react";
import { Play, X } from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useSingleRunStore } from "../../stores/singleRunStore";
import { useBatchRunStore } from "../../stores/batchRunStore";
import { usePortfolioRunStore } from "../../stores/portfolioRunStore";
import { parse, isValid } from "date-fns";
import { toast } from "sonner";

interface RunButtonProps {
    onClick?: () => void;
}

export const RunButton: React.FC<RunButtonProps> = ({ onClick }) => {
  const store = useBacktestStore();
  const singleStore = useSingleRunStore();
  const batchStore = useBatchRunStore();
  const portfolioStore = usePortfolioRunStore();

  const isRunning = singleStore.isRunning || batchStore.isRunning || portfolioStore.isRunning;
  const runProgress = store.mode === 'single' ? singleStore.runProgress : store.mode === 'batch' ? batchStore.runProgress : portfolioStore.runProgress;

  const runBacktest = async () => {
    try {
      const config = {
        mode: store.mode as 'single' | 'batch' | 'portfolio',
        symbols: store.mode === 'single' ? [store.symbol] : store.portfolioInput.split('\n').filter(s => s.trim() !== ''),
        timeframe: store.timeframe,
        strategy: store.strategy,
        start_date: store.startDate, // Need to make sure format matches yyyy-MM-dd logic in stores
        end_date: store.endDate,
        initial_capital: store.capital,
        capital_mode: store.capitalMode,
        leverage: parseInt(store.leverage),
        risk_per_trade_pct: store.riskPercent,
        fee_tier: "0.001",
        slippage_model: "none",
        slippage_pct: "0.0",
        params: store.params
      };

      // Basic formatting handle
      let sd = config.start_date;
      if (sd && sd.includes("-") && sd.split("-")[0].length === 2) {
          const parts = sd.split("-");
          sd = `${parts[2]}-${parts[1]}-${parts[0]}`;
          config.start_date = sd;
      }
      let ed = config.end_date;
      if (ed && ed.includes("-") && ed.split("-")[0].length === 2) {
          const parts = ed.split("-");
          ed = `${parts[2]}-${parts[1]}-${parts[0]}`;
          config.end_date = ed;
      }

      if (store.mode === 'single') singleStore.run(config);
      if (store.mode === 'batch') batchStore.run(config);
      if (store.mode === 'portfolio') portfolioStore.run(config);
    } catch (e: any) {
        toast.error(e.message);
    }
  };

  const cancelBacktest = async () => {
      if (store.mode === 'single') singleStore.cancel();
      if (store.mode === 'batch') batchStore.cancel();
      if (store.mode === 'portfolio') portfolioStore.cancel();
  };

  const handleClick = (e: React.MouseEvent) => {
      e.preventDefault();
      if (onClick) {
          onClick();
      } else {
          runBacktest();
      }
  };

  if (isRunning) {
    return (
      <div className="relative w-full h-12 rounded-lg bg-bg-elevated border border-border-main overflow-hidden group">
        {/* Progress Bar Background */}
        <div 
            className="absolute top-0 left-0 bottom-0 bg-accent-main/20 transition-all duration-300 ease-out"
            style={{ width: `${runProgress}%` }}
        />
        
        <div className="absolute inset-0 flex items-center justify-between px-4">
             <div className="flex flex-col justify-center">
                <span className="text-xs font-bold text-accent-main">RUNNING...</span>
                <span className="text-[10px] text-text-secondary font-mono">{runProgress}%</span>
             </div>
             
             <button 
                onClick={(e) => {
                    e.stopPropagation();
                    cancelBacktest();
                }}
                className="flex items-center gap-1 px-3 py-1 rounded-md bg-white/10 hover:bg-white/20 text-text-primary text-xs font-medium transition-colors z-10"
             >
                <X size={12} />
                Cancel
             </button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      className="w-full h-12 rounded-lg bg-accent-main hover:bg-accent-hover text-white shadow-lg shadow-accent-main/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group"
    >
      <Play size={18} className="fill-current" />
      <span className="font-semibold">Run Backtest</span>
      <span className="ml-2 px-1.5 py-0.5 rounded bg-black/20 text-[10px] font-mono text-white/70 group-hover:text-white/90">
        ⌘↵
      </span>
    </button>
  );
};
