import { create } from "zustand";

export interface GridSearchResult {
  xValue: number;
  yValue: number;
  netPnL: number;
  netPnLPct: number;
  sharpe: number;
  profitFactor: number;
  winRate: number;
  maxDrawdownPct: number;
  tradeCount: number;
  calmar?: number;
  sortino?: number;
}

export interface BestResult {
  x: number;
  y: number;
  xValue: number;
  yValue: number;
  metricValue: number;
  fullResults: GridSearchResult;
}

export type GridMetric = "net_pnl" | "sharpe" | "profit_factor" | "win_rate" | "max_dd" | "calmar" | "sortino";

export interface GridSearchState {
  // Configuration
  xAxisParam: string;
  xAxisMin: number;
  xAxisMax: number;
  xAxisStep: number;

  yAxisParam: string;
  yAxisMin: number;
  yAxisMax: number;
  yAxisStep: number;

  metric: GridMetric;
  symbol: string;

  // Computed
  totalCombinations: number;
  estimatedTimeMinutes: number;

  // Execution
  isRunning: boolean;
  progress: number; // 0-100
  currentCombination: { x: number; y: number } | null;
  elapsedSeconds: number;

  // Results
  results: GridSearchResult[][] | null; // 2D array [y][x]
  bestResult: BestResult | null;

  // View
  viewMode: "2d" | "3d";
  hoveredCell: { x: number; y: number } | null;

  // Actions
  setXAxisParam: (param: string) => void;
  setXAxisRange: (min: number, max: number, step: number) => void;
  setYAxisParam: (param: string) => void;
  setYAxisRange: (min: number, max: number, step: number) => void;
  setMetric: (metric: GridMetric) => void;
  setSymbol: (symbol: string) => void;
  setViewMode: (mode: "2d" | "3d") => void;
  setHoveredCell: (cell: { x: number; y: number } | null) => void;
  
  calculateCombinations: () => void;
  runGridSearch: () => Promise<void>;
  cancelSearch: () => void;
  applyBestSettings: () => void;
  exportResults: () => void;
  reset: () => void;
}

// Available parameters from strategy
export const AVAILABLE_PARAMETERS = [
  { value: "rsi_period", label: "RSI Period", type: "int", defaultMin: 10, defaultMax: 20, defaultStep: 2 },
  { value: "ema_fast", label: "EMA Fast", type: "int", defaultMin: 5, defaultMax: 15, defaultStep: 2 },
  { value: "ema_slow", label: "EMA Slow", type: "int", defaultMin: 15, defaultMax: 30, defaultStep: 5 },
  { value: "tp1_rr", label: "Take Profit 1 (R:R)", type: "float", defaultMin: 1.0, defaultMax: 3.0, defaultStep: 0.5 },
  { value: "tp2_rr", label: "Take Profit 2 (R:R)", type: "float", defaultMin: 2.0, defaultMax: 5.0, defaultStep: 0.5 },
  { value: "sl_buffer_pct", label: "Stop Loss Buffer %", type: "float", defaultMin: 0.5, defaultMax: 2.0, defaultStep: 0.25 },
  { value: "overbought", label: "Overbought", type: "int", defaultMin: 65, defaultMax: 80, defaultStep: 5 },
  { value: "oversold", label: "Oversold", type: "int", defaultMin: 20, defaultMax: 35, defaultStep: 5 },
];

// Generate mock results for a single combination
const generateMockResult = (xValue: number, yValue: number, metric: GridMetric): GridSearchResult => {
  // Generate somewhat realistic looking results with some variance
  const seed = xValue * 1000 + yValue;
  const random = (min: number, max: number) => {
    const x = Math.sin(seed) * 10000;
    return min + (x - Math.floor(x)) * (max - min);
  };

  // Create a "sweet spot" around middle values
  const xNormalized = xValue / 100; // Normalize to 0-1 range roughly
  const yNormalized = yValue / 100;
  const distanceFromCenter = Math.sqrt(Math.pow(xNormalized - 0.5, 2) + Math.pow(yNormalized - 0.5, 2));
  const sweetSpotMultiplier = Math.max(0, 1 - distanceFromCenter * 2);

  const baseProfit = (random(0.5, 1.5) + sweetSpotMultiplier) * 1000;
  const netPnL = baseProfit - 500; // Can be negative
  const netPnLPct = (netPnL / 10000) * 100;

  return {
    xValue,
    yValue,
    netPnL: Math.round(netPnL * 100) / 100,
    netPnLPct: Math.round(netPnLPct * 100) / 100,
    sharpe: Math.round((random(0.5, 2.5) + sweetSpotMultiplier * 0.5) * 100) / 100,
    profitFactor: Math.round((random(0.8, 2.2) + sweetSpotMultiplier * 0.3) * 100) / 100,
    winRate: Math.round((random(40, 75) + sweetSpotMultiplier * 10) * 100) / 100,
    maxDrawdownPct: Math.round((random(2, 15) - sweetSpotMultiplier * 3) * 100) / 100,
    tradeCount: Math.floor(random(10, 50)),
  };
};

export const useGridSearchStore = create<GridSearchState>((set, get) => ({
  // Initial Configuration
  xAxisParam: "rsi_period",
  xAxisMin: 10,
  xAxisMax: 20,
  xAxisStep: 2,

  yAxisParam: "tp1_rr",
  yAxisMin: 1.0,
  yAxisMax: 5.0,
  yAxisStep: 1.0,

  metric: "net_pnl",
  symbol: "BTC/USDT",

  totalCombinations: 30,
  estimatedTimeMinutes: 5,

  isRunning: false,
  progress: 0,
  currentCombination: null,
  elapsedSeconds: 0,

  results: null,
  bestResult: null,

  viewMode: "2d",
  hoveredCell: null,

  // Actions
  setXAxisParam: (param) => {
    const paramConfig = AVAILABLE_PARAMETERS.find(p => p.value === param);
    if (paramConfig) {
      set({
        xAxisParam: param,
        xAxisMin: paramConfig.defaultMin,
        xAxisMax: paramConfig.defaultMax,
        xAxisStep: paramConfig.defaultStep,
      });
      get().calculateCombinations();
    }
  },

  setXAxisRange: (min, max, step) => {
    set({ xAxisMin: min, xAxisMax: max, xAxisStep: step });
    get().calculateCombinations();
  },

  setYAxisParam: (param) => {
    const paramConfig = AVAILABLE_PARAMETERS.find(p => p.value === param);
    if (paramConfig) {
      set({
        yAxisParam: param,
        yAxisMin: paramConfig.defaultMin,
        yAxisMax: paramConfig.defaultMax,
        yAxisStep: paramConfig.defaultStep,
      });
      get().calculateCombinations();
    }
  },

  setYAxisRange: (min, max, step) => {
    set({ yAxisMin: min, yAxisMax: max, yAxisStep: step });
    get().calculateCombinations();
  },

  setMetric: (metric) => set({ metric }),
  setSymbol: (symbol) => set({ symbol }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setHoveredCell: (cell) => set({ hoveredCell: cell }),

  calculateCombinations: () => {
    const { xAxisMin, xAxisMax, xAxisStep, yAxisMin, yAxisMax, yAxisStep } = get();
    
    const xSteps = Math.floor((xAxisMax - xAxisMin) / xAxisStep) + 1;
    const ySteps = Math.floor((yAxisMax - yAxisMin) / yAxisStep) + 1;
    const total = xSteps * ySteps;

    // Estimate ~10 seconds per combination
    const estimatedMinutes = Math.ceil((total * 10) / 60);

    set({
      totalCombinations: total,
      estimatedTimeMinutes: estimatedMinutes,
    });
  },

  runGridSearch: async () => {
    const { 
      xAxisMin, xAxisMax, xAxisStep, 
      yAxisMin, yAxisMax, yAxisStep,
      metric
    } = get();

    set({ isRunning: true, progress: 0, elapsedSeconds: 0, results: null, bestResult: null });

    // Generate X and Y value arrays
    const xValues: number[] = [];
    for (let x = xAxisMin; x <= xAxisMax; x += xAxisStep) {
      xValues.push(Math.round(x * 100) / 100);
    }

    const yValues: number[] = [];
    for (let y = yAxisMin; y <= yAxisMax; y += yAxisStep) {
      yValues.push(Math.round(y * 100) / 100);
    }

    const totalCombinations = xValues.length * yValues.length;
    const results: GridSearchResult[][] = [];
    let bestResult: BestResult | null = null;
    let completed = 0;

    // Track elapsed time
    const startTime = Date.now();
    const timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      set({ elapsedSeconds: elapsed });
    }, 1000);

    try {
      // Simulate running each combination
      for (let yIdx = 0; yIdx < yValues.length; yIdx++) {
        const row: GridSearchResult[] = [];
        
        for (let xIdx = 0; xIdx < xValues.length; xIdx++) {
          // Check if cancelled
          if (!get().isRunning) {
            clearInterval(timerInterval);
            return;
          }

          const xValue = xValues[xIdx];
          const yValue = yValues[yIdx];

          set({ currentCombination: { x: xIdx, y: yIdx } });

          // Simulate API call
          await new Promise(resolve => setTimeout(resolve, 100));

          const result = generateMockResult(xValue, yValue, metric);
          row.push(result);

          // Track best result based on metric
          let metricValue: number;
          switch (metric) {
            case "net_pnl":
              metricValue = result.netPnL;
              break;
            case "sharpe":
              metricValue = result.sharpe;
              break;
            case "profit_factor":
              metricValue = result.profitFactor;
              break;
            case "win_rate":
              metricValue = result.winRate;
              break;
            case "max_dd":
              metricValue = -result.maxDrawdownPct; // Lower is better
              break;
            default:
              metricValue = result.netPnL;
          }

          if (!bestResult || metricValue > bestResult.metricValue) {
            bestResult = {
              x: xIdx,
              y: yIdx,
              xValue,
              yValue,
              metricValue,
              fullResults: result,
            };
          }

          completed++;
          set({ progress: Math.round((completed / totalCombinations) * 100) });
        }

        results.push(row);
      }

      set({ results, bestResult, isRunning: false, currentCombination: null });
    } catch (error) {
      console.error("Grid search error:", error);
      set({ isRunning: false, currentCombination: null });
    } finally {
      clearInterval(timerInterval);
    }
  },

  cancelSearch: () => {
    set({ isRunning: false, currentCombination: null });
  },

  applyBestSettings: () => {
    const { bestResult, xAxisParam, yAxisParam } = get();
    if (!bestResult) return;

    // Import the backtest store and apply settings
    const { useBacktestStore } = require("./backtestStore");
    const setParam = useBacktestStore.getState().setParam;
    
    setParam(xAxisParam, bestResult.xValue);
    setParam(yAxisParam, bestResult.yValue);

    console.log("Applied best settings:", {
      [xAxisParam]: bestResult.xValue,
      [yAxisParam]: bestResult.yValue,
    });
  },

  exportResults: () => {
    const { results, xAxisParam, yAxisParam, xAxisMin, xAxisStep, yAxisMin, yAxisStep } = get();
    if (!results) return;

    // Generate CSV
    let csv = `${xAxisParam},${yAxisParam},Net PnL,Net PnL %,Sharpe,Profit Factor,Win Rate %,Max DD %,Trades\n`;
    
    results.forEach((row, yIdx) => {
      row.forEach((result, xIdx) => {
        csv += `${result.xValue},${result.yValue},${result.netPnL},${result.netPnLPct},${result.sharpe},${result.profitFactor},${result.winRate},${result.maxDrawdownPct},${result.tradeCount}\n`;
      });
    });

    // Download CSV
    const blob = new Blob([csv], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `grid_search_${Date.now()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  },

  reset: () => {
    set({
      results: null,
      bestResult: null,
      isRunning: false,
      progress: 0,
      currentCombination: null,
      elapsedSeconds: 0,
      hoveredCell: null,
    });
  },
}));