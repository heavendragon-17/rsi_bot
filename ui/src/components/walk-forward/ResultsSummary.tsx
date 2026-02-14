import React from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
import { cn } from "../../lib/utils";
import {
  Check,
  AlertTriangle,
  X,
  TrendingUp,
  Target,
  Award,
} from "lucide-react";
import { Card } from "../ui/card";
import { Button } from "../ui/button";

export const ResultsSummary: React.FC = () => {
  const { summary, paramToOptimize, applyBestParam } = useWalkForwardStore();

  if (!summary) {
    return null;
  }

  const paramLabel =
    AVAILABLE_PARAMETERS.find((p) => p.value === paramToOptimize)?.label ||
    paramToOptimize;

  const getVerdictIcon = () => {
    if (summary.verdict === "robust") {
      return <Check className="w-5 h-5 text-success" />;
    } else if (summary.verdict === "marginal") {
      return <AlertTriangle className="w-5 h-5 text-warning" />;
    } else {
      return <X className="w-5 h-5 text-danger" />;
    }
  };

  const getVerdictColor = () => {
    if (summary.verdict === "robust") return "success";
    if (summary.verdict === "marginal") return "warning";
    return "danger";
  };

  const getStabilityColor = () => {
    if (summary.paramStability === "high") return "text-success";
    if (summary.paramStability === "medium") return "text-warning";
    return "text-danger";
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary">
        Walk-Forward Results
      </h3>

      {/* Main metrics cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-4 bg-bg-elevated border-border-main">
          <div className="flex items-start justify-between mb-2">
            <div className="text-xs font-medium text-text-secondary">
              OOS WIN RATE
            </div>
            <TrendingUp className="w-4 h-4 text-accent-main" />
          </div>
          <div className="space-y-1">
            <div className="text-2xl font-bold text-text-primary">
              {summary.oosWinRate.toFixed(1)}%
            </div>
            <div className="text-xs text-text-secondary">
              {summary.oosWinCount} / {summary.totalWindows} windows
            </div>
          </div>
        </Card>

        <Card className="p-4 bg-bg-elevated border-border-main">
          <div className="flex items-start justify-between mb-2">
            <div className="text-xs font-medium text-text-secondary">
              AVG OOS RETURN
            </div>
            <Target className="w-4 h-4 text-accent-main" />
          </div>
          <div className="space-y-1">
            <div
              className={cn(
                "text-2xl font-bold",
                summary.avgOosReturn > 0 ? "text-success" : "text-danger"
              )}
            >
              {summary.avgOosReturn > 0 ? "+" : ""}
              {summary.avgOosReturn.toFixed(2)}%
            </div>
            <div className="text-xs text-text-secondary">per window</div>
          </div>
        </Card>

        <Card
          className={cn(
            "p-4 border-2",
            summary.verdict === "robust"
              ? "bg-success/5 border-success/30"
              : summary.verdict === "marginal"
              ? "bg-warning/5 border-warning/30"
              : "bg-danger/5 border-danger/30"
          )}
        >
          <div className="flex items-start justify-between mb-2">
            <div className="text-xs font-medium text-text-secondary">
              ROBUSTNESS
            </div>
            {getVerdictIcon()}
          </div>
          <div className="space-y-1">
            <div
              className={cn(
                "text-2xl font-bold uppercase",
                `text-${getVerdictColor()}`
              )}
            >
              {summary.verdict}
            </div>
            <div className="text-xs text-text-secondary">
              {summary.verdict === "robust" && "Strategy holds up well"}
              {summary.verdict === "marginal" && "Moderate consistency"}
              {summary.verdict === "overfit" && "May be curve-fitted"}
            </div>
          </div>
        </Card>
      </div>

      {/* Detailed metrics */}
      <Card className="p-4 bg-bg-elevated border-border-main">
        <h4 className="text-xs font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Award className="w-4 h-4 text-accent-main" />
          Detailed Metrics
        </h4>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
          <div>
            <div className="text-text-secondary text-xs mb-1">
              Total OOS Return
            </div>
            <div
              className={cn(
                "font-semibold",
                summary.totalOosReturn > 0 ? "text-success" : "text-danger"
              )}
            >
              {summary.totalOosReturn > 0 ? "+" : ""}
              {summary.totalOosReturn.toFixed(2)}%
            </div>
          </div>

          <div>
            <div className="text-text-secondary text-xs mb-1">Best Window</div>
            <div className="font-semibold text-text-primary">
              W{summary.bestWindow.index} (
              {summary.bestWindow.returnPct > 0 ? "+" : ""}
              {summary.bestWindow.returnPct.toFixed(1)}%)
            </div>
          </div>

          <div>
            <div className="text-text-secondary text-xs mb-1">Worst Window</div>
            <div className="font-semibold text-text-primary">
              W{summary.worstWindow.index} (
              {summary.worstWindow.returnPct > 0 ? "+" : ""}
              {summary.worstWindow.returnPct.toFixed(1)}%)
            </div>
          </div>

          <div>
            <div className="text-text-secondary text-xs mb-1">
              Parameter Stability
            </div>
            <div
              className={cn(
                "font-semibold uppercase text-xs",
                getStabilityColor()
              )}
            >
              {summary.paramStability}
            </div>
          </div>
        </div>
      </Card>

      {/* Most common parameter */}
      <Card className="p-4 bg-accent-main/5 border border-accent-main/30">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-text-secondary mb-1">
              Most Common Best Parameter
            </div>
            <div className="text-lg font-bold text-text-primary">
              {paramLabel} = {summary.mostCommonParam.value}
            </div>
            <div className="text-xs text-text-secondary mt-1">
              Appeared in {summary.mostCommonParam.count} /{" "}
              {summary.totalWindows} windows (
              {(
                (summary.mostCommonParam.count / summary.totalWindows) *
                100
              ).toFixed(0)}
              %)
            </div>
          </div>
          <Button
            onClick={applyBestParam}
            className="bg-accent-main hover:bg-accent-main/90 text-white"
          >
            Apply to Strategy
          </Button>
        </div>
      </Card>
    </div>
  );
};
