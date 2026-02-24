import React from "react";
import { Play, X } from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";

interface RunButtonProps {
    onClick?: () => void;
}

export const RunButton: React.FC<RunButtonProps> = ({ onClick }) => {
  const { isRunning, runProgress, runBacktest, cancelBacktest } = useBacktestStore();

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
