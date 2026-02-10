import React, { useEffect, useState } from "react";
import { useDataPrepStore } from "../../stores/dataPrepStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { useResultsStore } from "../../stores/resultsStore";
import { useBatchResultsStore } from "../../stores/batchResultsStore";
import { cn } from "../../lib/utils";
import { motion } from "motion/react";
import { TechnicalZenLoader } from "./TechnicalZenLoader";
import { SymbolStatusTable } from "./SymbolStatusTable";
import { AnimatedProgressBar } from "./AnimatedProgressBar";
import { ContextFactDisplay } from "./ContextFactDisplay";
import { X, Play, RefreshCw, AlertTriangle, ArrowRight, CheckCircle } from "lucide-react";
import { getRandomFact } from "../../lib/data-utils";

export const DataPrepModal: React.FC = () => {
  const { 
      isOpen, 
      state, 
      closeModal, 
      symbols, 
      overallProgress, 
      currentDownload, 
      estimatedTimeRemaining,
      currentFact,
      setFact,
      setPrepState,
      setProgress,
      updateSymbolStatus,
      reset
  } = useDataPrepStore();

  const { runBacktest, capital, mode } = useBacktestStore();
  const { generateMockResults, setResults } = useResultsStore();
  const { generateMockBatchResults, clearBatchResults } = useBatchResultsStore();
  
  const [autoCloseTimer, setAutoCloseTimer] = useState<number | null>(null);

  // Fact Rotation Logic
  useEffect(() => {
    if (!isOpen || state === "complete" || state === "ready") return;
    
    setFact(getRandomFact(currentDownload || undefined));

    const interval = setInterval(() => {
        setFact(getRandomFact(currentDownload || undefined));
    }, 5000);

    return () => clearInterval(interval);
  }, [isOpen, state, currentDownload, setFact]);


  // Simulation of Downloading
  useEffect(() => {
    if (state === "downloading" && isOpen) {
        let progress = 0;
        const total = 100;
        
        // Find next missing/outdated symbol
        const pendingSymbols = symbols.filter(s => s.status === "missing" || s.status === "outdated");
        
        if (pendingSymbols.length === 0) {
            setPrepState("complete");
            return;
        }

        const activeSymbol = pendingSymbols[0];
        updateSymbolStatus(activeSymbol.symbol, { status: "downloading" });
        useDataPrepStore.setState({ currentDownload: activeSymbol.symbol });

        const interval = setInterval(() => {
            progress += 5; // Faster for demo
            
            if (progress > 100) {
                clearInterval(interval);
                updateSymbolStatus(activeSymbol.symbol, { status: "fresh" });
                
                // Check if more
                const remaining = symbols.filter(s => (s.status === "missing" || s.status === "outdated") && s.symbol !== activeSymbol.symbol);
                if (remaining.length === 0) {
                     setPrepState("complete");
                     setProgress(100, 0);
                } else {
                     setProgress(overallProgress + (100 / symbols.length)); 
                }
            } else {
                setProgress(Math.min(99, progress), 5); // Dummy ETA
            }
        }, 50);

        return () => clearInterval(interval);
    }
  }, [state, isOpen, symbols, setPrepState, setProgress, updateSymbolStatus, overallProgress]);


  // Auto-Start on Ready/Complete
  useEffect(() => {
      if ((state === "ready" || state === "complete") && isOpen) {
          const timer = window.setTimeout(() => {
              handleStartBacktest();
          }, 1500); 
          setAutoCloseTimer(timer);
          return () => clearTimeout(timer);
      }
  }, [state, isOpen]);

  const handleStartBacktest = async () => {
      if (autoCloseTimer) clearTimeout(autoCloseTimer);
      closeModal();
      
      await runBacktest();
      
      if (mode === "single") {
          clearBatchResults();
          generateMockResults(parseFloat(capital));
      } else {
          setResults({ hasResults: false });
          const batchSymbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT", "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT", "UNI/USDT", "LINK/USDT"];
          generateMockBatchResults(parseFloat(capital), batchSymbols);
      }
      
      setTimeout(reset, 500);
  };

  const handleCancel = () => {
      if (autoCloseTimer) clearTimeout(autoCloseTimer);
      closeModal();
      reset();
  };

  const handleAction = (symbol: string, action: "skip" | "partial" | "retry") => {
      if (action === "skip" || action === "partial") {
          updateSymbolStatus(symbol, { status: "fresh" });
      }
      if (action === "retry") {
          updateSymbolStatus(symbol, { status: "missing" });
          setPrepState("downloading");
      }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={handleCancel}
      />

      {/* Modal Content */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-lg bg-bg-surface backdrop-blur-xl border border-border-main shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[90vh]"
      >
        {/* Header Section */}
        <div className="p-6 pb-2">
            <div className="flex items-center gap-4 mb-4">
                 <div className="shrink-0">
                     {state === "checking" || state === "downloading" ? (
                         <TechnicalZenLoader className="w-16 h-16" />
                     ) : state === "error" ? (
                         <div className="w-16 h-16 rounded-full bg-danger/10 flex items-center justify-center">
                             <AlertTriangle className="text-danger w-8 h-8" />
                         </div>
                     ) : (
                         <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center">
                             <CheckCircle className="text-success w-8 h-8" />
                         </div>
                     )}
                 </div>
                 
                 <div>
                     <h2 className="text-lg font-semibold text-text-primary">
                        {state === "checking" && "Validating Data Integrity"}
                        {state === "downloading" && "Initializing Data Pipeline"}
                        {state === "ready" && "Data Ready"}
                        {state === "complete" && "Download Complete"}
                        {state === "error" && "Download Failed"}
                     </h2>
                     <p className="text-sm text-text-secondary mt-1">
                        {state === "checking" && "Checking local cache for requested symbols..."}
                        {state === "downloading" && "Syncing historical data for backtest."}
                        {state === "ready" && "All historical data is up-to-date."}
                        {state === "complete" && "All data synced successfully."}
                        {state === "error" && "Connection interrupted. Please retry."}
                     </p>
                 </div>
            </div>

            {/* Symbol Table */}
            <SymbolStatusTable symbols={symbols} onAction={handleAction} />
        </div>

        {/* Dynamic Content Area */}
        <div className="px-6 py-2 space-y-4">
            
            {/* Progress Bar (Only when downloading) */}
            {state === "downloading" && (
                <div className="space-y-2">
                    <div className="flex justify-between text-xs font-medium text-text-secondary">
                        <div className="flex items-center gap-2">
                            {currentDownload && (
                                <>
                                    <span className="text-text-primary">Syncing {currentDownload}</span>
                                    <span className="text-text-muted">•</span>
                                </>
                            )}
                            <span>{overallProgress.toFixed(0)}%</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <span>⏱️ ~{estimatedTimeRemaining}s remaining</span>
                        </div>
                    </div>
                    <AnimatedProgressBar progress={overallProgress} />
                </div>
            )}

            {/* Context Fact */}
            <ContextFactDisplay fact={currentFact} />
        </div>

        {/* Footer Actions */}
        <div className="p-6 pt-4 flex items-center justify-between border-t border-border-main/50 bg-bg-surface/50">
            <button 
                onClick={handleCancel}
                className="px-4 py-2 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
                Cancel
            </button>

            <div className="flex gap-2">
                {state === "error" ? (
                     <button 
                        onClick={() => {
                            setPrepState("downloading");
                        }}
                        className="px-4 py-2 rounded-lg bg-accent-main text-white text-sm font-medium hover:bg-accent-hover transition-colors shadow-lg shadow-accent-main/20 flex items-center gap-2"
                     >
                        <RefreshCw size={16} />
                        Retry
                     </button>
                ) : (
                    <button 
                        onClick={handleStartBacktest}
                        className={cn(
                            "px-4 py-2 rounded-lg bg-accent-main text-white text-sm font-medium hover:bg-accent-hover transition-colors shadow-lg shadow-accent-main/20 flex items-center gap-2",
                            (state === "checking" || state === "downloading") && "opacity-80"
                        )}
                    >
                        {state === "ready" || state === "complete" ? (
                            <>
                                Start Backtest 
                                <ArrowRight size={16} />
                            </>
                        ) : (
                            <>
                                Start Anyway
                                <Play size={16} className="fill-current" />
                            </>
                        )}
                    </button>
                )}
            </div>
        </div>
      </motion.div>
    </div>
  );
};
