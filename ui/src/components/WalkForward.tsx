// @ts-nocheck
import React, { useEffect } from "react";
import { useWalkForwardStore } from "../stores/walkForwardStore";
import { useBacktestStore } from "../stores/backtestStore";
import {
  WindowConfig,
  ParamOptimizeConfig,
  TimelineVisualization,
  ResultsSummary,
  WalkForwardProgress,
  EquityCurveComparison,
} from "./walk-forward";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Separator } from "./ui/separator";
import { Play, Square, Download, RotateCcw, TrendingUp } from "lucide-react";
import { cn } from "../lib/utils";
import { toast } from "sonner";

export const WalkForward: React.FC = () => {
  const {
    isRunning,
    totalWindows,
    estimatedTimeMinutes,
    windows,
    summary,
    calculateWindows,
    runWalkForward,
    cancelRun,
    exportResults,
    reset,
  } = useWalkForwardStore();

  const { startDate, endDate } = useBacktestStore();

  // Calculate windows on mount and when config changes
  useEffect(() => {
    calculateWindows();
  }, [calculateWindows]);

  const handleRun = async () => {
    if (!startDate || !endDate) {
      toast.error("Please set a date range in the sidebar first");
      return;
    }

    if (totalWindows === 0) {
      toast.error("No windows generated. Adjust configuration.");
      return;
    }

    await runWalkForward();
    toast.success("Walk-forward optimization complete!");
  };

  const handleExport = () => {
    exportResults();
    toast.success("Results exported to CSV");
  };

  const handleReset = () => {
    reset();
    toast.info("Results cleared");
  };

  const hasResults = windows.length > 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent-main/10 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-accent-main" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-text-primary">Walk-Forward Optimization</h1>
              <p className="text-sm text-text-secondary">
                Validate strategy robustness with rolling in-sample/out-of-sample windows
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {hasResults && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExport}
                  className="gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export Results
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReset}
                  className="gap-2"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reset
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Configuration Section */}
        <Card className="p-6 bg-bg-surface border-border-main">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <WindowConfig />
            <div className="space-y-4">
              <ParamOptimizeConfig />

              <Separator />

              {/* Run Button */}
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs text-text-secondary">
                  <span>Estimated Time:</span>
                  <span className="font-medium text-text-primary">
                    ~{estimatedTimeMinutes} min
                  </span>
                </div>

                {isRunning ? (
                  <Button
                    onClick={cancelRun}
                    variant="destructive"
                    className="w-full gap-2"
                  >
                    <Square className="w-4 h-4" />
                    Cancel
                  </Button>
                ) : (
                  <Button
                    onClick={handleRun}
                    className="w-full gap-2 bg-accent-main hover:bg-accent-main/90 text-white"
                    disabled={totalWindows === 0}
                  >
                    <Play className="w-4 h-4" />
                    Run Walk-Forward
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Progress Bar */}
        <WalkForwardProgress />

        {/* Results Section */}
        {hasResults && (
          <>
            <Card className="p-6 bg-bg-surface border-border-main">
              <TimelineVisualization />
            </Card>

            <Card className="p-6 bg-bg-surface border-border-main">
              <ResultsSummary />
            </Card>

            <Card className="p-6 bg-bg-surface border-border-main">
              <EquityCurveComparison />
            </Card>
          </>
        )}

        {/* Empty State */}
        {!hasResults && !isRunning && (
          <Card className="p-12 bg-bg-elevated border-dashed border-border-main text-center">
            <div className="max-w-md mx-auto space-y-4">
              <div className="w-16 h-16 rounded-full bg-accent-main/10 mx-auto flex items-center justify-center">
                <TrendingUp className="w-8 h-8 text-accent-main" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary mb-2">
                  Ready to Test Robustness
                </h3>
                <p className="text-sm text-text-secondary mb-4">
                  Configure your walk-forward windows and parameter range above, then click
                  "Run Walk-Forward" to validate that your strategy isn't overfit to historical data.
                </p>
                <div className="inline-block p-4 bg-bg-surface rounded-lg border border-border-main text-left">
                  <div className="text-xs font-semibold text-text-primary mb-2">
                    💡 What is Walk-Forward?
                  </div>
                  <ul className="text-xs text-text-secondary space-y-1">
                    <li>• Optimize on <strong>In-Sample</strong> data (training)</li>
                    <li>• Validate on <strong>Out-of-Sample</strong> data (testing)</li>
                    <li>• Roll forward and repeat</li>
                    <li>• A robust strategy performs well on <strong>unseen</strong> data</li>
                  </ul>
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};
