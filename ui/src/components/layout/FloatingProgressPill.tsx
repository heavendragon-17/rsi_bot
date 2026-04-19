import React, { useState } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronUp, Download, Activity } from "lucide-react";
import { cn } from "../../lib/utils";

export const FloatingProgressPill: React.FC = () => {
  const {
    isRunning, runProgress, runPhase,
    downloadProgress, backtestProgress,
    cancelBacktest,
  } = useBacktestStore();
  const [expanded, setExpanded] = useState(false);

  if (!isRunning) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        className="fixed bottom-6 right-6 z-50"
      >
        <div className={cn(
          "bg-bg-surface/95 backdrop-blur-xl border border-accent-main/30",
          "shadow-2xl shadow-accent-main/10 rounded-2xl overflow-hidden",
          "transition-all duration-300",
          expanded ? "w-80" : "w-56"
        )}>
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3 cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-accent-main animate-pulse" />
              <span className="text-xs font-medium text-text-primary">
                {runPhase === "download" ? "Downloading..." : "Running..."}
              </span>
              <span className="text-xs font-mono text-accent-main">
                {Math.round(runProgress)}%
              </span>
            </div>
            {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </div>

          {/* Progress Bar */}
          <div className="px-4 pb-2">
            <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-accent-main rounded-full"
                animate={{ width: `${runProgress}%` }}
                transition={{ ease: "easeOut" }}
              />
            </div>
          </div>

          {/* Expanded Details */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4 space-y-3 border-t border-border-main/50 pt-3">
                  <div className="flex items-center gap-2">
                    <Download size={12} className={cn(
                      runPhase === "download" ? "text-accent-main" : "text-success"
                    )} />
                    <span className="text-xs text-text-secondary flex-1">Data Download</span>
                    <span className="text-xs font-mono text-text-primary">
                      {runPhase === "download" ? `${downloadProgress}%` : "Done"}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Activity size={12} className={cn(
                      runPhase === "backtest" ? "text-accent-main" :
                      runPhase === "download" ? "text-text-muted" : "text-success"
                    )} />
                    <span className="text-xs text-text-secondary flex-1">Backtest</span>
                    <span className="text-xs font-mono text-text-primary">
                      {runPhase === "backtest" ? `${backtestProgress}%` :
                       runPhase === "download" ? "Waiting" : "Done"}
                    </span>
                  </div>

                  <button
                    onClick={(e) => { e.stopPropagation(); cancelBacktest(); }}
                    className="w-full py-1.5 text-xs text-danger hover:bg-danger/10 rounded-lg transition-colors"
                  >
                    Cancel Backtest
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
