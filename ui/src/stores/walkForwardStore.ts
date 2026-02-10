import { create } from "zustand";

export interface WalkForwardWindow {
  index: number;
  isStartDate: string;
  isEndDate: string;
  oosStartDate: string;
  oosEndDate: string;

  // Optimization result
  bestParam: number;
  isMetricValue: number; // e.g., IS Sharpe

  // Validation result
  oosReturn: number;
  oosReturnPct: number;
  isPositive: boolean;
}

export interface WalkForwardSummary {
  oosWinRate: number;
  oosWinCount: number;
  totalWindows: number;
  avgOosReturn: number;
  totalOosReturn: number;
  bestWindow: { index: number; returnPct: number; param: number };
  worstWindow: { index: number; returnPct: number; param: number };
  mostCommonParam: { value: number; count: number };
  paramStability: "high" | "medium" | "low";
  verdict: "robust" | "marginal" | "overfit";
}

export type WalkForwardMetric = "sharpe" | "net_pnl" | "profit_factor" | "sortino";

export interface WalkForwardState {
  // Configuration
  isWindowDays: number;
  oosWindowDays: number;
  stepSizeDays: number;

  paramToOptimize: string;
  paramMin: number;
  paramMax: number;
  paramStep: number;

  optimizeMetric: WalkForwardMetric;

  // Computed
  totalWindows: number;
  estimatedTimeMinutes: number;

  // Execution
  isRunning: boolean;
  currentWindow: number;
  progress: number;

  // Results
  windows: WalkForwardWindow[];
  summary: WalkForwardSummary | null;

  // Actions
  setIsWindowDays: (days: number) => void;
  setOosWindowDays: (days: number) => void;
  setStepSizeDays: (days: number) => void;
  setParamToOptimize: (param: string) => void;
  setParamRange: (min: number, max: number, step: number) => void;
  setOptimizeMetric: (metric: WalkForwardMetric) => void;
  
  calculateWindows: () => void;
  runWalkForward: () => Promise<void>;
  cancelRun: () => void;
  applyBestParam: () => void;
  exportResults: () => void;
  reset: () => void;
}

// Helper to generate date ranges
const generateDateRanges = (
  totalDays: number,
  isWindowDays: number,
  oosWindowDays: number,
  stepSizeDays: number
): Array<{
  isStart: Date;
  isEnd: Date;
  oosStart: Date;
  oosEnd: Date;
}> => {
  const ranges = [];
  const baseDate = new Date("2024-01-01");
  
  let currentStartDay = 0;
  
  while (currentStartDay + isWindowDays + oosWindowDays <= totalDays) {
    const isStart = new Date(baseDate);
    isStart.setDate(isStart.getDate() + currentStartDay);
    
    const isEnd = new Date(isStart);
    isEnd.setDate(isEnd.getDate() + isWindowDays - 1);
    
    const oosStart = new Date(isEnd);
    oosStart.setDate(oosStart.getDate() + 1);
    
    const oosEnd = new Date(oosStart);
    oosEnd.setDate(oosEnd.getDate() + oosWindowDays - 1);
    
    ranges.push({ isStart, isEnd, oosStart, oosEnd });
    
    currentStartDay += stepSizeDays;
  }
  
  return ranges;
};

// Mock result generation
const generateWindowResult = (
  windowIndex: number,
  paramMin: number,
  paramMax: number,
  paramStep: number,
  metric: WalkForwardMetric
): { bestParam: number; isMetricValue: number; oosReturnPct: number } => {
  // Simulate optimization finding best param in IS
  const possibleParams = [];
  for (let p = paramMin; p <= paramMax; p += paramStep) {
    possibleParams.push(Math.round(p * 100) / 100);
  }
  
  // Pick "best" param with some variance
  const seed = windowIndex * 12345;
  const random = (min: number, max: number) => {
    const x = Math.sin(seed + windowIndex) * 10000;
    return min + (x - Math.floor(x)) * (max - min);
  };
  
  const bestParamIdx = Math.floor(random(0, possibleParams.length));
  const bestParam = possibleParams[bestParamIdx];
  
  // IS metric value
  const isMetricValue = random(0.8, 2.2);
  
  // OOS return - with some degradation from IS
  // Most windows should be positive (70-80%) for a robust strategy
  const oosReturnPct = random(-3, 7) * (0.7 + random(0, 0.3));
  
  return {
    bestParam,
    isMetricValue: Math.round(isMetricValue * 100) / 100,
    oosReturnPct: Math.round(oosReturnPct * 100) / 100,
  };
};

// Calculate summary statistics
const calculateSummary = (windows: WalkForwardWindow[]): WalkForwardSummary => {
  const positiveWindows = windows.filter(w => w.isPositive);
  const oosWinCount = positiveWindows.length;
  const totalWindows = windows.length;
  const oosWinRate = totalWindows > 0 ? (oosWinCount / totalWindows) * 100 : 0;
  
  const totalOosReturn = windows.reduce((sum, w) => sum + w.oosReturnPct, 0);
  const avgOosReturn = totalWindows > 0 ? totalOosReturn / totalWindows : 0;
  
  // Find best and worst windows
  let bestWindow = { index: 0, returnPct: windows[0]?.oosReturnPct ?? 0, param: windows[0]?.bestParam ?? 0 };
  let worstWindow = { index: 0, returnPct: windows[0]?.oosReturnPct ?? 0, param: windows[0]?.bestParam ?? 0 };
  
  windows.forEach((w, idx) => {
    if (w.oosReturnPct > bestWindow.returnPct) {
      bestWindow = { index: idx + 1, returnPct: w.oosReturnPct, param: w.bestParam };
    }
    if (w.oosReturnPct < worstWindow.returnPct) {
      worstWindow = { index: idx + 1, returnPct: w.oosReturnPct, param: w.bestParam };
    }
  });
  
  // Find most common param
  const paramCounts = new Map<number, number>();
  windows.forEach(w => {
    const count = paramCounts.get(w.bestParam) || 0;
    paramCounts.set(w.bestParam, count + 1);
  });
  
  let mostCommonParam = { value: 0, count: 0 };
  paramCounts.forEach((count, value) => {
    if (count > mostCommonParam.count) {
      mostCommonParam = { value, count };
    }
  });
  
  // Calculate parameter stability
  const params = windows.map(w => w.bestParam);
  const avgParam = params.reduce((sum, p) => sum + p, 0) / params.length;
  const variance = params.reduce((sum, p) => sum + Math.pow(p - avgParam, 2), 0) / params.length;
  const stdDev = Math.sqrt(variance);
  
  let paramStability: "high" | "medium" | "low" = "high";
  if (stdDev > 2) paramStability = "low";
  else if (stdDev > 1) paramStability = "medium";
  
  // Determine verdict
  let verdict: "robust" | "marginal" | "overfit" = "overfit";
  if (oosWinRate >= 70) verdict = "robust";
  else if (oosWinRate >= 50) verdict = "marginal";
  
  return {
    oosWinRate: Math.round(oosWinRate * 100) / 100,
    oosWinCount,
    totalWindows,
    avgOosReturn: Math.round(avgOosReturn * 100) / 100,
    totalOosReturn: Math.round(totalOosReturn * 100) / 100,
    bestWindow,
    worstWindow,
    mostCommonParam,
    paramStability,
    verdict,
  };
};

export const useWalkForwardStore = create<WalkForwardState>((set, get) => ({
  // Initial Configuration
  isWindowDays: 60,
  oosWindowDays: 20,
  stepSizeDays: 20,

  paramToOptimize: "rsi_period",
  paramMin: 10,
  paramMax: 20,
  paramStep: 2,

  optimizeMetric: "sharpe",

  totalWindows: 0,
  estimatedTimeMinutes: 0,

  isRunning: false,
  currentWindow: 0,
  progress: 0,

  windows: [],
  summary: null,

  // Actions
  setIsWindowDays: (days) => {
    set({ isWindowDays: days });
    get().calculateWindows();
  },

  setOosWindowDays: (days) => {
    set({ oosWindowDays: days });
    get().calculateWindows();
  },

  setStepSizeDays: (days) => {
    set({ stepSizeDays: days });
    get().calculateWindows();
  },

  setParamToOptimize: (param) => {
    // Import available parameters
    const { AVAILABLE_PARAMETERS } = require("./gridSearchStore");
    const paramConfig = AVAILABLE_PARAMETERS.find((p: any) => p.value === param);
    
    if (paramConfig) {
      set({
        paramToOptimize: param,
        paramMin: paramConfig.defaultMin,
        paramMax: paramConfig.defaultMax,
        paramStep: paramConfig.defaultStep,
      });
    }
  },

  setParamRange: (min, max, step) => {
    set({ paramMin: min, paramMax: max, paramStep: step });
  },

  setOptimizeMetric: (metric) => set({ optimizeMetric: metric }),

  calculateWindows: () => {
    const { isWindowDays, oosWindowDays, stepSizeDays } = get();
    const totalDataDays = 365; // Full year
    
    const ranges = generateDateRanges(totalDataDays, isWindowDays, oosWindowDays, stepSizeDays);
    const totalWindows = ranges.length;
    
    // Each window: optimize params (1 min) + validate (10 sec)
    const estimatedMinutes = Math.ceil((totalWindows * 70) / 60);
    
    set({
      totalWindows,
      estimatedTimeMinutes: estimatedMinutes,
    });
  },

  runWalkForward: async () => {
    const {
      isWindowDays,
      oosWindowDays,
      stepSizeDays,
      paramMin,
      paramMax,
      paramStep,
      optimizeMetric,
    } = get();

    set({ isRunning: true, progress: 0, currentWindow: 0, windows: [], summary: null });

    const totalDataDays = 365;
    const ranges = generateDateRanges(totalDataDays, isWindowDays, oosWindowDays, stepSizeDays);
    const totalWindows = ranges.length;
    const windows: WalkForwardWindow[] = [];

    try {
      for (let i = 0; i < ranges.length; i++) {
        // Check if cancelled
        if (!get().isRunning) return;

        set({ currentWindow: i + 1 });

        const range = ranges[i];
        const result = generateWindowResult(i, paramMin, paramMax, paramStep, optimizeMetric);

        const window: WalkForwardWindow = {
          index: i + 1,
          isStartDate: range.isStart.toISOString().split("T")[0],
          isEndDate: range.isEnd.toISOString().split("T")[0],
          oosStartDate: range.oosStart.toISOString().split("T")[0],
          oosEndDate: range.oosEnd.toISOString().split("T")[0],
          bestParam: result.bestParam,
          isMetricValue: result.isMetricValue,
          oosReturn: result.oosReturnPct * 100, // Store as actual currency value (mock)
          oosReturnPct: result.oosReturnPct,
          isPositive: result.oosReturnPct > 0,
        };

        windows.push(window);
        set({ windows: [...windows], progress: Math.round(((i + 1) / totalWindows) * 100) });

        // Simulate processing time
        await new Promise(resolve => setTimeout(resolve, 150));
      }

      const summary = calculateSummary(windows);
      set({ summary, isRunning: false, currentWindow: 0 });
    } catch (error) {
      console.error("Walk-forward error:", error);
      set({ isRunning: false, currentWindow: 0 });
    }
  },

  cancelRun: () => {
    set({ isRunning: false, currentWindow: 0 });
  },

  applyBestParam: () => {
    const { summary, paramToOptimize } = get();
    if (!summary) return;

    const { useBacktestStore } = require("./backtestStore");
    const setParam = useBacktestStore.getState().setParam;

    setParam(paramToOptimize, summary.mostCommonParam.value);

    console.log("Applied most common best param:", {
      [paramToOptimize]: summary.mostCommonParam.value,
    });
  },

  exportResults: () => {
    const { windows, summary, paramToOptimize } = get();
    if (!windows.length) return;

    let csv = `Window,IS Start,IS End,OOS Start,OOS End,Best ${paramToOptimize},IS Metric,OOS Return %,Status\n`;

    windows.forEach((w) => {
      csv += `W${w.index},${w.isStartDate},${w.isEndDate},${w.oosStartDate},${w.oosEndDate},${w.bestParam},${w.isMetricValue},${w.oosReturnPct},${w.isPositive ? "Positive" : "Negative"}\n`;
    });

    if (summary) {
      csv += `\nSummary\n`;
      csv += `OOS Win Rate,${summary.oosWinRate}%\n`;
      csv += `Avg OOS Return,${summary.avgOosReturn}%\n`;
      csv += `Total OOS Return,${summary.totalOosReturn}%\n`;
      csv += `Most Common Param,${summary.mostCommonParam.value}\n`;
      csv += `Verdict,${summary.verdict.toUpperCase()}\n`;
    }

    const blob = new Blob([csv], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `walk_forward_${Date.now()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  },

  reset: () => {
    set({
      windows: [],
      summary: null,
      isRunning: false,
      currentWindow: 0,
      progress: 0,
    });
  },
}));
