import React from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { AlertTriangle } from "lucide-react";

export const WindowConfig: React.FC = () => {
  const {
    isWindowDays,
    oosWindowDays,
    stepSizeDays,
    totalWindows,
    setIsWindowDays,
    setOosWindowDays,
    setStepSizeDays,
  } = useWalkForwardStore();

  const { getDaysDuration } = useBacktestStore();
  const totalDataDays = getDaysDuration();

  const isRecommendedRatio = isWindowDays >= oosWindowDays * 3;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-text-primary mb-3">Window Configuration</h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label htmlFor="is-window" className="text-xs text-text-secondary">
              In-Sample (IS) Window
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id="is-window"
                type="number"
                value={isWindowDays}
                onChange={(e) => setIsWindowDays(Number(e.target.value))}
                className="h-9 text-sm"
                min={10}
                max={365}
              />
              <span className="text-xs text-text-secondary whitespace-nowrap">days</span>
            </div>
            <p className="text-xs text-text-tertiary">Training period</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="oos-window" className="text-xs text-text-secondary">
              Out-of-Sample (OOS) Window
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id="oos-window"
                type="number"
                value={oosWindowDays}
                onChange={(e) => setOosWindowDays(Number(e.target.value))}
                className="h-9 text-sm"
                min={5}
                max={180}
              />
              <span className="text-xs text-text-secondary whitespace-nowrap">days</span>
            </div>
            <p className="text-xs text-text-tertiary">Validation period</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="step-size" className="text-xs text-text-secondary">
              Step Size (Walk Forward)
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id="step-size"
                type="number"
                value={stepSizeDays}
                onChange={(e) => setStepSizeDays(Number(e.target.value))}
                className="h-9 text-sm"
                min={1}
                max={180}
              />
              <span className="text-xs text-text-secondary whitespace-nowrap">days</span>
            </div>
            <p className="text-xs text-text-tertiary">How far to advance</p>
          </div>
        </div>
      </div>

      <div className="h-px bg-border-main" />

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-text-secondary">Total Data Range:</span>
          <span className="ml-2 text-text-primary font-medium">
            {totalDataDays > 0 ? `${totalDataDays} days` : "Not set"}
          </span>
        </div>
        <div>
          <span className="text-text-secondary">Windows Generated:</span>
          <span className="ml-2 text-text-primary font-medium">{totalWindows}</span>
        </div>
      </div>

      {!isRecommendedRatio && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-warning/10 border border-warning/30">
          <AlertTriangle className="w-4 h-4 text-warning mt-0.5 flex-shrink-0" />
          <div className="text-xs text-warning">
            <strong>Recommendation:</strong> IS window should be ≥ 3× OOS window for stable optimization.
            Current ratio: {(isWindowDays / oosWindowDays).toFixed(1)}×
          </div>
        </div>
      )}
    </div>
  );
};
