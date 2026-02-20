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
    bestResult,
    isRunning,
    calculateCombinations,
    exportResults,
    setSymbol,
  } = useGridSearchStore();
  const { symbol: backtestSymbol } = useBacktestStore();

  useEffect(() => {
    // Calculate combinations on mount
    calculateCombinations();
    // Sync symbol from backtest store
    setSymbol(backtestSymbol);
  }, [calculateCombinations, backtestSymbol, setSymbol]);

  const handleExport = () => {
    if (!results) return;
    exportResults();
  };

  return (
    <div className="h-full overflow-auto">
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

          {results && (
            <Button onClick={handleExport} variant="outline" className="gap-2">
              <Download className="w-4 h-4" />
              Export Results
            </Button>
          )}
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

        {/* Best Result Card (shown when results available) */}
        {bestResult && !isRunning && <BestResultCard />}

        {/* Heatmap */}
        {results && !isRunning && (
          <Card className="p-6 bg-card border-border-main">
            <Heatmap />
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
