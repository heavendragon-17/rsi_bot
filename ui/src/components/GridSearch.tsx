import React, { useEffect } from "react";
import { Flame, Download } from "lucide-react";
import { useGridSearchStore } from "../stores/gridSearchStore";
import { useBacktestStore } from "../stores/backtestStore";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { ParameterSetup } from "./grid-search/ParameterSetup";
import { GridProgressBar } from "./grid-search/GridProgressBar";
import { Heatmap } from "./grid-search/Heatmap";
import { BestResultCard } from "./grid-search/BestResultCard";

export const GridSearch: React.FC = () => {
  const {
    results,
    isRunning,
    calculateCombinations,
    setSymbol,
    shouldAutoNavigate,
    setShouldAutoNavigate,
  } = useGridSearchStore();
  const { symbol: backtestSymbol, setMode } = useBacktestStore();

  useEffect(() => {
    // Calculate combinations on mount
    calculateCombinations();
    // Sync symbol from backtest store
    setSymbol(backtestSymbol);
  }, [calculateCombinations, backtestSymbol, setSymbol]);

  // Auto-navigate to results page when search completes (only if flag is set)
  useEffect(() => {
    console.log("[GridSearch] Auto-nav check:", { results: !!results, isRunning, shouldAutoNavigate });
    if (results && !isRunning && shouldAutoNavigate) {
      console.log("[GridSearch] Auto-navigating to results");
      setShouldAutoNavigate(false); // Reset flag after navigating
      setMode("grid-search-results");
    }
  }, [results, isRunning, shouldAutoNavigate, setShouldAutoNavigate, setMode]);



  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <div className="max-w-[1400px] mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-accent-main/10">
              <Flame className="w-6 h-6 text-accent-main" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-text-primary">
                Grid Search
              </h1>
              <p className="text-sm text-text-secondary">
                Find optimal parameters with heatmap analysis
              </p>
            </div>
          </div>

        </div>

        {/* Parameter Setup */}
        <Card className="p-6 bg-card border-border-main">
          <ParameterSetup />
        </Card>

        {/* Progress Bar (shown while running) */}
        {isRunning && (
          <Card className="p-6 bg-card border-border-main">
            <GridProgressBar />
          </Card>
        )}



        {/* Empty State */}
        {!results && !isRunning && (
          <Card className="p-12 bg-card border-border-main">
            <div className="text-center space-y-4">
              <div className="mx-auto w-16 h-16 rounded-full bg-accent-main/10 flex items-center justify-center">
                <Flame className="w-8 h-8 text-accent-main" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary mb-2">
                  Configure Parameters & Run Grid Search
                </h3>
                <p className="text-sm text-text-secondary max-w-md mx-auto">
                  Select two parameters to test across a range of values. The
                  heatmap will show which combinations perform best.
                </p>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};
