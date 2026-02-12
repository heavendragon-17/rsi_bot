import React, { useEffect } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { useGridSearchStore } from "../stores/gridSearchStore";
import { useBacktestStore } from "../stores/backtestStore";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { BestResultCard } from "./grid-search/BestResultCard";
import { Heatmap } from "./grid-search/Heatmap";

export const GridSearchResults: React.FC = () => {
  const { results, bestResult } = useGridSearchStore();
  const { setMode } = useBacktestStore();

  // Redirect to config if no results
  useEffect(() => {
    if (!results) {
      setMode("grid-search");
    }
  }, [results, setMode]);

  const handleBack = () => {
    console.log("[GridSearchResults] Back button clicked, navigating to grid-search");
    setMode("grid-search");
  };

  const handleExport = () => {
    // TODO: Implement CSV export
    console.log("Export results as CSV");
  };

  if (!results) {
    return null;
  }

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <div className="max-w-[1600px] mx-auto p-6 space-y-6">
        {/* Header with back button and export */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button onClick={handleBack} variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Config
            </Button>
            <div>
              <h1 className="text-2xl font-bold text-text-primary">Grid Search Results</h1>
              <p className="text-sm text-text-secondary">
                Analyzed {results.length * results[0].length} parameter combinations
              </p>
            </div>
          </div>
          <Button onClick={handleExport} variant="outline" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Export CSV
          </Button>
        </div>

        {/* Best Result Card */}
        {bestResult && <BestResultCard />}

        {/* Full-Width Heatmap */}
        <Card className="p-6 bg-card border-border-main">
          <Heatmap />
        </Card>
      </div>
    </div>
  );
};
