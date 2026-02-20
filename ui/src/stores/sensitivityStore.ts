import { create } from "zustand";
import { startSensitivity, streamQuantProgress } from "../api/quant";

export type SensitivityMetric = "net_pnl" | "sharpe" | "profit_factor" | "win_rate";

export interface SensitivityResult {
  paramName: string;
  paramDisplayName: string;

  // Values tested
  lowValue: number;
  baseValue: number;
  highValue: number;

  // Results for each test
  lowMetric: number;
  baseMetric: number;
  highMetric: number;

  // Computed impact
  lowImpactPct: number; // (low - base) / base * 100
  highImpactPct: number; // (high - base) / base * 100
  totalImpact: number; // |lowImpact| + |highImpact|
  sensitivity: "high" | "medium" | "low";
  status?: "success" | "failed";
  error?: string;
}

export interface SensitivityState {
  // Configuration
  variationPercent: number; // 10, 20, 30, or custom
  customVariation: string; // For custom input
  metric: SensitivityMetric;

  // Execution
  isRunning: boolean;
  progress: number;
  currentParam: string;
  _sseCleanup: (() => void) | null;

  // Results
  results: SensitivityResult[];
  insights: string[];
  baseMetricValue: number; // The base value of the selected metric

  // Actions
  setVariationPercent: (percent: number) => void;
  setCustomVariation: (value: string) => void;
  setMetric: (metric: SensitivityMetric) => void;
  
  runSensitivityAnalysis: () => Promise<void>;
  cancelRun: () => void;
  exportResults: () => void;
  reset: () => void;
}



// Calculate sensitivity category
const calculateSensitivity = (totalImpact: number): "high" | "medium" | "low" => {
  if (totalImpact > 20) return "high";
  if (totalImpact > 10) return "medium";
  return "low";
};

// Generate insights based on results
const generateInsights = (results: SensitivityResult[]): string[] => {
  const insights: string[] = [];

  if (results.length === 0) return insights;

  // Find highest sensitivity param
  const highestSensitivity = results[0]; // Already sorted
  if (highestSensitivity.sensitivity === "high") {
    insights.push(
      `🔴 ${highestSensitivity.paramDisplayName} is your most sensitive parameter (${Math.round(highestSensitivity.totalImpact)}% total impact). Small changes cause large swings in performance. Use Grid Search to find the exact optimal value.`
    );
  }

  // Count high sensitivity params
  const highSensParams = results.filter((r) => r.sensitivity === "high");
  if (highSensParams.length > 2) {
    insights.push(
      `⚠️ You have ${highSensParams.length} high-sensitivity parameters. This strategy may be prone to overfitting. Consider Walk-Forward validation.`
    );
  }

  // Find stable params
  const lowSensParams = results.filter((r) => r.sensitivity === "low");
  if (lowSensParams.length > 0) {
    const paramNames = lowSensParams.map((p) => p.paramDisplayName).join(", ");
    insights.push(
      `🟢 ${paramNames} ${lowSensParams.length === 1 ? "is" : "are"} stable parameters. Current values are robust and require less optimization.`
    );
  }

  // Check for asymmetric impact
  results.forEach((result) => {
    const lowAbs = Math.abs(result.lowImpactPct);
    const highAbs = Math.abs(result.highImpactPct);
    const ratio = Math.max(lowAbs, highAbs) / (Math.min(lowAbs, highAbs) + 0.01);
    
    if (ratio > 2 && result.sensitivity !== "low") {
      if (lowAbs > highAbs) {
        insights.push(
          `⚡ ${result.paramDisplayName}: Decreasing this parameter has much stronger impact than increasing it. Be cautious with lower values.`
        );
      } else {
        insights.push(
          `⚡ ${result.paramDisplayName}: Increasing this parameter has much stronger impact than decreasing it. Explore higher values carefully.`
        );
      }
    }
  });

  return insights;
};

export const useSensitivityStore = create<SensitivityState>((set, get) => ({
  // Initial State
  variationPercent: 20,
  customVariation: "",
  metric: "net_pnl",

  isRunning: false,
  progress: 0,
  currentParam: "",
  _sseCleanup: null,

  results: [],
  insights: [],
  baseMetricValue: 0,

  // Actions
  setVariationPercent: (percent) => set({ variationPercent: percent }),
  
  setCustomVariation: (value) => set({ customVariation: value }),
  
  setMetric: (metric) => set({ metric }),

  runSensitivityAnalysis: async () => {
    const { variationPercent, customVariation, metric } = get();
    set({ isRunning: true, progress: 0, results: [], insights: [], currentParam: "" });

    const { useBacktestStore } = await import("./backtestStore");
    const { params, symbol, timeframe, strategy, startDate, endDate } = useBacktestStore.getState();

    const { AVAILABLE_PARAMETERS } = await import("./gridSearchStore");
    const actualVariation = customVariation ? parseFloat(customVariation) : variationPercent;

    // Calculate parameter variations to test
    const variationsToTest: Record<string, number[]> = {};
    AVAILABLE_PARAMETERS.forEach((paramDef: any) => {
        const baseValue = params[paramDef.value] || paramDef.defaultMin;
        const variation = actualVariation / 100;
        const lowValue = paramDef.type === "int" 
          ? Math.round(baseValue * (1 - variation))
          : Math.round(baseValue * (1 - variation) * 100) / 100;
        const highValue = paramDef.type === "int"
          ? Math.round(baseValue * (1 + variation))
          : Math.round(baseValue * (1 + variation) * 100) / 100;
        
        variationsToTest[paramDef.value] = [lowValue, baseValue, highValue];
    });

    try {
      const response = await startSensitivity({
        symbol,
        timeframe,
        strategy,
        start_date: startDate?.toISOString(),
        end_date: endDate?.toISOString(),
        base_params: params,
        variations: variationsToTest,
        metric
      });

      const cleanup = streamQuantProgress(
        response.run_id,
        (pct, currentParam) => {
          set({ progress: pct, currentParam: currentParam || "" });
        },
        (data) => {
          let results: SensitivityResult[] = [];
          if (data && Array.isArray(data.results)) {
            results = data.results.map((r: any) => ({
              paramName: r.param_name,
              paramDisplayName: AVAILABLE_PARAMETERS.find((p: any) => p.value === r.param_name)?.label || r.param_name,
              lowValue: r.low_value,
              baseValue: r.base_value,
              highValue: r.high_value,
              lowMetric: r.low_metric || 0,
              baseMetric: r.base_metric || 0,
              highMetric: r.high_metric || 0,
              lowImpactPct: r.low_impact_pct || 0,
              highImpactPct: r.high_impact_pct || 0,
              totalImpact: r.total_impact || 0,
              sensitivity: r.sensitivity || "low",
              status: r.status || "success",
              error: r.error
            }));
          }

          // Sort by total impact (descending)
          results.sort((a, b) => b.totalImpact - a.totalImpact);

          // Generate insights
          const insights = generateInsights(results);

          set({
            results,
            insights,
            isRunning: false,
            progress: 100,
            currentParam: "",
            _sseCleanup: null,
            baseMetricValue: results.length > 0 ? results[0].baseMetric : 0
          });
        },
        (errorMsg) => {
          console.error("Sensitivity analysis error:", errorMsg);
          set({ isRunning: false, progress: 0, currentParam: "", _sseCleanup: null });
        }
      );

      set({ _sseCleanup: cleanup });

    } catch (error) {
      console.error("Sensitivity analysis error:", error);
      set({ isRunning: false, progress: 0, currentParam: "", _sseCleanup: null });
    }
  },

  cancelRun: () => {
    const { _sseCleanup } = get();
    if (_sseCleanup) _sseCleanup();
    set({ isRunning: false, progress: 0, currentParam: "", _sseCleanup: null });
  },

  exportResults: () => {
    const { results, variationPercent, metric, insights } = get();
    if (results.length === 0) return;

    let csv = `Sensitivity Analysis Report\n`;
    csv += `Variation: ±${variationPercent}%\n`;
    csv += `Metric: ${metric}\n\n`;

    csv += `Parameter,Low Value,Low Result,Base Value,Base Result,High Value,High Result,Low Impact %,High Impact %,Total Impact %,Sensitivity\n`;

    results.forEach((r) => {
      csv += `${r.paramDisplayName},${r.lowValue},${r.lowMetric},${r.baseValue},${r.baseMetric},${r.highValue},${r.highMetric},${r.lowImpactPct},${r.highImpactPct},${r.totalImpact},${r.sensitivity.toUpperCase()}\n`;
    });

    csv += `\nInsights\n`;
    insights.forEach((insight, idx) => {
      csv += `${idx + 1}. ${insight.replace(/[🔴🟡🟢⚠️⚡]/g, "")}\n`;
    });

    const blob = new Blob([csv], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sensitivity_analysis_${Date.now()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  },

  reset: () => {
    set({
      results: [],
      insights: [],
      isRunning: false,
      progress: 0,
      currentParam: "",
      baseMetricValue: 0,
      _sseCleanup: null,
    });
  },
}));
