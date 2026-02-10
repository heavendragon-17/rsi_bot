import React from "react";
import { Wind, Download } from "lucide-react";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { SensitivityConfig } from "./SensitivityConfig";
import { TornadoChart } from "./TornadoChart";
import { SensitivityTable } from "./SensitivityTable";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { Card } from "../ui/card";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";

export const SensitivityAnalysis: React.FC = () => {
  const { isRunning, progress, currentParam, results, exportResults } = useSensitivityStore();

  return (
    <div className="h-full flex flex-col gap-4 p-6 overflow-auto custom-scrollbar">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent-main/10 flex items-center justify-center">
            <Wind className="w-5 h-5 text-accent-main" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-text-primary">Sensitivity Analysis</h1>
            <p className="text-sm text-text-secondary">
              Identify which parameters have the most impact on strategy performance
            </p>
          </div>
        </div>

        {results.length > 0 && !isRunning && (
          <Button
            onClick={exportResults}
            variant="outline"
            className="gap-2"
          >
            <Download className="w-4 h-4" />
            Export Report
          </Button>
        )}
      </div>

      {/* Configuration Panel */}
      <SensitivityConfig />

      {/* Progress Bar */}
      {isRunning && (
        <Card className="p-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-text-secondary">
                Analyzing: <span className="text-text-primary font-medium">{currentParam}</span>
              </span>
              <span className="text-text-primary font-medium">{progress}%</span>
            </div>
            <Progress value={progress} className="h-2" />
          </div>
        </Card>
      )}

      {/* Results - Tornado Chart */}
      {results.length > 0 && (
        <>
          <TornadoChart />
          <SensitivityTable />
          <RecommendationsPanel />
        </>
      )}

      {/* Empty State */}
      {!isRunning && results.length === 0 && (
        <Card className="p-12 flex flex-col items-center justify-center text-center">
          <div className="w-16 h-16 rounded-full bg-bg-elevated flex items-center justify-center mb-4">
            <Wind className="w-8 h-8 text-text-muted" />
          </div>
          <h3 className="text-lg font-semibold text-text-primary mb-2">No Analysis Results Yet</h3>
          <p className="text-sm text-text-secondary max-w-md">
            Configure your variation settings and click "Run Sensitivity Analysis" to see how each
            parameter affects your strategy performance.
          </p>
        </Card>
      )}
    </div>
  );
};
