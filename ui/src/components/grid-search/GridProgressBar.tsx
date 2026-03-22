import React from "react";
import { X } from "lucide-react";
import { useGridSearchStore } from "../../stores/gridSearchStore";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";

export const GridProgressBar: React.FC = () => {
  const {
    progress,
    currentCombination,
    elapsedSeconds,
    totalCombinations,
    estimatedTimeMinutes,
    xAxisMin,
    xAxisStep,
    yAxisMin,
    yAxisStep,
    cancelSearch
  } = useGridSearchStore();

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const currentXValue = currentCombination
    ? xAxisMin + (currentCombination.x * xAxisStep)
    : 0;
  const currentYValue = currentCombination
    ? yAxisMin + (currentCombination.y * yAxisStep)
    : 0;

  const completedCombinations = Math.floor((progress / 100) * totalCombinations);
  const estimatedRemaining = Math.max(0, (estimatedTimeMinutes * 60) - elapsedSeconds);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-text-primary">Running Grid Search</h3>
        <Button
          onClick={cancelSearch}
          variant="outline"
          size="sm"
          className="gap-2 text-danger border-danger/30 hover:bg-danger/10"
        >
          <X className="w-4 h-4" />
          Cancel
        </Button>
      </div>

      <div className="h-px bg-border-main" />

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-text-secondary">Progress</span>
          <span className="font-semibold text-text-primary">
            {completedCombinations}/{totalCombinations} ({progress}%)
          </span>
        </div>
        <Progress value={progress} className="h-3" />
      </div>

      {/* Current Status */}
      {currentCombination && (
        <div className="rounded-lg bg-bg-elevated border border-border-main p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Current Combination:</span>
            <span className="text-sm font-mono font-semibold text-text-primary">
              X={currentXValue.toFixed(2)}, Y={currentYValue.toFixed(2)}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-border-main">
            <div>
              <p className="text-xs text-text-secondary mb-1">Elapsed</p>
              <p className="text-lg font-semibold text-text-primary">{formatTime(elapsedSeconds)}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary mb-1">Remaining</p>
              <p className="text-lg font-semibold text-text-primary">
                ~{formatTime(estimatedRemaining)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Message */}
      <p className="text-sm text-text-secondary text-center">
        Please wait while we test all parameter combinations...
      </p>
    </div>
  );
};
