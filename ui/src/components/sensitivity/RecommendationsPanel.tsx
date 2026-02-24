import React from "react";
import { Lightbulb, TrendingUp, Flame } from "lucide-react";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { Card } from "../ui/card";
import { Button } from "../ui/button";

export const RecommendationsPanel: React.FC = () => {
  const { insights, results } = useSensitivityStore();
  const { setMode } = useBacktestStore();

  if (results.length === 0) return null;

  const highSensParams = results.filter((r) => r.sensitivity === "high");
  const topParam = results[0];

  return (
    <Card className="p-6">
      <div className="flex items-center gap-2 mb-4">
        <Lightbulb className="w-5 h-5 text-accent-main" />
        <h2 className="text-lg font-semibold text-text-primary">Recommendations</h2>
      </div>

      {/* Insights */}
      <div className="space-y-3 mb-6">
        {insights.map((insight, idx) => (
          <div
            key={idx}
            className="px-4 py-3 bg-bg-elevated rounded-lg border border-border-main"
          >
            <p className="text-sm text-text-primary leading-relaxed">{insight}</p>
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      {highSensParams.length > 0 && (
        <div className="space-y-4">
          <div className="text-sm font-medium text-text-secondary">Next Steps</div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Grid Search Recommendation */}
            <div className="p-4 bg-bg-elevated rounded-lg border border-border-main hover:border-accent-main transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-accent-main/10 flex items-center justify-center flex-shrink-0">
                  <Flame className="w-4 h-4 text-accent-main" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-text-primary mb-1">
                    Run Grid Search
                  </h3>
                  <p className="text-xs text-text-secondary mb-3">
                    Optimize {topParam.paramDisplayName} to find the exact best value. This
                    parameter has high sensitivity ({topParam.totalImpact.toFixed(0)}% impact).
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setMode("grid-search")}
                    className="w-full gap-2"
                  >
                    <Flame className="w-3 h-3" />
                    Open Grid Search
                  </Button>
                </div>
              </div>
            </div>

            {/* Walk-Forward Recommendation */}
            <div className="p-4 bg-bg-elevated rounded-lg border border-border-main hover:border-accent-main transition-colors">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-accent-main/10 flex items-center justify-center flex-shrink-0">
                  <TrendingUp className="w-4 h-4 text-accent-main" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-text-primary mb-1">
                    Validate with Walk-Forward
                  </h3>
                  <p className="text-xs text-text-secondary mb-3">
                    Test {topParam.paramDisplayName} stability across different time periods to
                    ensure robustness and avoid overfitting.
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setMode("walk-forward")}
                    className="w-full gap-2"
                  >
                    <TrendingUp className="w-3 h-3" />
                    Open Walk-Forward
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stability Note */}
      {highSensParams.length === 0 && (
        <div className="px-4 py-3 bg-success/10 border border-success/30 rounded-lg">
          <p className="text-sm text-text-primary">
            <span className="font-semibold">✅ Good News:</span> All parameters show low to medium
            sensitivity. Your strategy appears stable and less prone to overfitting. Current
            parameter values are likely robust.
          </p>
        </div>
      )}
    </Card>
  );
};
