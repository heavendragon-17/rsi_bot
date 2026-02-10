import React from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { Progress } from "../ui/progress";
import { Loader2 } from "lucide-react";

export const WalkForwardProgress: React.FC = () => {
  const { isRunning, currentWindow, totalWindows, progress } = useWalkForwardStore();

  if (!isRunning) {
    return null;
  }

  return (
    <div className="p-4 rounded-lg bg-accent-main/5 border border-accent-main/30 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 text-accent-main animate-spin" />
          <span className="text-sm font-medium text-text-primary">
            Running Walk-Forward Optimization...
          </span>
        </div>
        <span className="text-sm font-medium text-text-primary">
          {progress}%
        </span>
      </div>

      <Progress value={progress} className="h-2" />

      <div className="flex items-center justify-between text-xs text-text-secondary">
        <span>Window {currentWindow} of {totalWindows}</span>
        <span>Processing...</span>
      </div>
    </div>
  );
};
