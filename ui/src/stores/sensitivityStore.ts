import { create } from "zustand";

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

// Helper: Generate mock backtest result for a parameter set
const generateMockResult = (
  paramName: string,
  paramValue: number,
  metric: SensitivityMetric,
  baseValue: number
): number => {
  // Create semi-realistic sensitivity patterns
  const seed = paramValue * 100;
  const random = (min: number, max: number) => {
    const x = Math.sin(seed) * 10000;
    return min + (x - Math.floor(x)) * (max - min);
  };

  // Different parameters have different sensitivity profiles
  let sensitivityFactor = 1.0;
  
  if (paramName === "rsi_period") {
    // High sensitivity - large impact on results
    sensitivityFactor = 1.5;
  } else if (paramName === "ema_fast" || paramName === "ema_slow") {
    // Medium sensitivity
    sensitivityFactor = 1.2;
  } else if (paramName === "tp1_rr" || paramName === "tp2_rr") {
    // Medium sensitivity
    sensitivityFactor = 1.15;
  } else if (paramName === "sl_buffer_pct") {
    // Medium-high sensitivity
    sensitivityFactor = 1.3;
  } else if (paramName === "overbought" || paramName === "oversold") {
    // Low sensitivity - stable parameters
    sensitivityFactor = 0.6;
  }

  // Calculate deviation from base value
  const deviation = (paramValue - baseValue) / baseValue;
  
  // Apply non-linear effect
  const impact = deviation * sensitivityFactor * random(0.8, 1.2);

  // Base values for different metrics
  let baseMetricValue = 0;
  if (metric === "net_pnl") {
    baseMetricValue = 1330;
  } else if (metric === "sharpe") {
    baseMetricValue = 1.8;
  } else if (metric === "profit_factor") {
    baseMetricValue = 1.6;
  } else if (metric === "win_rate") {
    baseMetricValue = 65;
  }

  // Calculate result with impact
  const result = baseMetricValue * (1 + impact);
  
  return Math.round(result * 100) / 100;
};

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

  results: [],
  insights: [],
  baseMetricValue: 0,

  // Actions
  setVariationPercent: (percent) => set({ variationPercent: percent }),
  
  setCustomVariation: (value) => set({ customVariation: value }),
  
  setMetric: (metric) => set({ metric }),

  runSensitivityAnalysis: async () => {
    const { variationPercent, metric } = get();
    set({ isRunning: true, progress: 0, results: [], insights: [], currentParam: "" });

    try {
      // Get current strategy parameters from backtest store
      const { useBacktestStore } = require("./backtestStore");
      const { params } = useBacktestStore.getState();

      // Import parameter definitions
      const { AVAILABLE_PARAMETERS } = require("./gridSearchStore");

      // Get base metric value
      const baseMetricValue = generateMockResult("base", 0, metric, 0);
      set({ baseMetricValue });

      const results: SensitivityResult[] = [];
      const paramCount = AVAILABLE_PARAMETERS.length;

      // Test each parameter
      for (let i = 0; i < AVAILABLE_PARAMETERS.length; i++) {
        const paramDef = AVAILABLE_PARAMETERS[i];
        const paramName = paramDef.value;
        const baseValue = params[paramName] || paramDef.defaultMin;

        set({ currentParam: paramDef.label, progress: Math.round((i / paramCount) * 100) });

        // Calculate test values
        const variation = variationPercent / 100;
        const lowValue = paramDef.type === "int" 
          ? Math.round(baseValue * (1 - variation))
          : Math.round(baseValue * (1 - variation) * 100) / 100;
        const highValue = paramDef.type === "int"
          ? Math.round(baseValue * (1 + variation))
          : Math.round(baseValue * (1 + variation) * 100) / 100;

        // Run mock backtests
        const lowMetric = generateMockResult(paramName, lowValue, metric, baseValue);
        const baseMetric = generateMockResult(paramName, baseValue, metric, baseValue);
        const highMetric = generateMockResult(paramName, highValue, metric, baseValue);

        // Calculate impacts
        const lowImpactPct = baseMetric !== 0 ? ((lowMetric - baseMetric) / baseMetric) * 100 : 0;
        const highImpactPct = baseMetric !== 0 ? ((highMetric - baseMetric) / baseMetric) * 100 : 0;
        const totalImpact = Math.abs(lowImpactPct) + Math.abs(highImpactPct);

        const result: SensitivityResult = {
          paramName,
          paramDisplayName: paramDef.label,
          lowValue,
          baseValue,
          highValue,
          lowMetric,
          baseMetric,
          highMetric,
          lowImpactPct: Math.round(lowImpactPct * 100) / 100,
          highImpactPct: Math.round(highImpactPct * 100) / 100,
          totalImpact: Math.round(totalImpact * 100) / 100,
          sensitivity: calculateSensitivity(totalImpact),
        };

        results.push(result);

        // Simulate processing time
        await new Promise((resolve) => setTimeout(resolve, 200));

        // Check if cancelled
        if (!get().isRunning) return;
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
      });
    } catch (error) {
      console.error("Sensitivity analysis error:", error);
      set({ isRunning: false, progress: 0, currentParam: "" });
    }
  },

  cancelRun: () => {
    set({ isRunning: false, progress: 0, currentParam: "" });
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
    });
  },
}));
