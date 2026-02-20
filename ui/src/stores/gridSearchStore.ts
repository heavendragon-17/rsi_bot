import { create } from "zustand";
import { startGridSearch, streamQuantProgress } from "../api/quant";

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
  status?: "success" | "failed";
  error?: string;
  config?: Record<string, any>;
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
  _sseCleanup: (() => void) | null;

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
  _sseCleanup: null,

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
      xAxisParam, xAxisMin, xAxisMax, xAxisStep, 
      yAxisParam, yAxisMin, yAxisMax, yAxisStep,
      symbol, metric
    } = get();

    set({ isRunning: true, progress: 0, elapsedSeconds: 0, results: null, bestResult: null });

    // Track elapsed time
    const startTime = Date.now();
    const timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      set({ elapsedSeconds: elapsed });
    }, 1000);

    const { useBacktestStore } = await import("./backtestStore");
    const baseParams = useBacktestStore.getState().params;
    const timeframe = useBacktestStore.getState().timeframe;
    const strategy = useBacktestStore.getState().strategy;
    const startDate = useBacktestStore.getState().startDate;
    const endDate = useBacktestStore.getState().endDate;

    const xValues: number[] = [];
    for (let x = xAxisMin; x <= xAxisMax; x += xAxisStep) {
      xValues.push(Math.round(x * 100) / 100);
    }
    const yValues: number[] = [];
    for (let y = yAxisMin; y <= yAxisMax; y += yAxisStep) {
      yValues.push(Math.round(y * 100) / 100);
    }

    try {
      const response = await startGridSearch({
        symbol,
        timeframe,
        strategy,
        start_date: startDate?.toISOString(),
        end_date: endDate?.toISOString(),
        params: baseParams,
        grid_params: {
          [xAxisParam]: xValues,
          [yAxisParam]: yValues
        }
      });

      const cleanup = streamQuantProgress(
        response.run_id,
        (pct, currentBest) => {
          set({ progress: pct });
        },
        (data) => {
          const results2D: GridSearchResult[][] = Array.from({ length: yValues.length }, () => 
            Array(xValues.length).fill(null)
          );
          
          let finalBest: BestResult | null = null;

          if (data && Array.isArray(data.results)) {
            data.results.forEach((res: any) => {
              const xIdx = xValues.findIndex(v => Math.abs(v - res.config[xAxisParam]) < 0.0001);
              const yIdx = yValues.findIndex(v => Math.abs(v - res.config[yAxisParam]) < 0.0001);
              
              if (xIdx !== -1 && yIdx !== -1) {
                const node: GridSearchResult = {
                  xValue: res.config[xAxisParam],
                  yValue: res.config[yAxisParam],
                  netPnL: res.net_profit || 0,
                  netPnLPct: res.net_profit_pct || 0,
                  sharpe: res.sharpe_ratio || 0,
                  profitFactor: res.profit_factor || 0,
                  winRate: res.win_rate || 0,
                  maxDrawdownPct: res.max_drawdown_pct || 0,
                  tradeCount: res.total_trades || 0,
                  status: res.status,
                  error: res.error,
                  config: res.config
                };
                results2D[yIdx][xIdx] = node;

                if (node.status !== "failed") {
                  let metricValue = 0;
                  switch (metric) {
                    case "net_pnl": metricValue = node.netPnL; break;
                    case "sharpe": metricValue = node.sharpe; break;
                    case "profit_factor": metricValue = node.profitFactor; break;
                    case "win_rate": metricValue = node.winRate; break;
                    case "max_dd": metricValue = -node.maxDrawdownPct; break;
                    default: metricValue = node.netPnL;
                  }
                  if (!finalBest || metricValue > finalBest.metricValue) {
                    finalBest = {
                      x: xIdx, y: yIdx,
                      xValue: node.xValue, yValue: node.yValue,
                      metricValue, fullResults: node
                    };
                  }
                }
              }
            });
          }
          
          clearInterval(timerInterval);
          set({ results: results2D, bestResult: finalBest, isRunning: false, currentCombination: null, progress: 100, _sseCleanup: null });
        },
        (errorMsg) => {
          console.error("SSE Error:", errorMsg);
          clearInterval(timerInterval);
          set({ isRunning: false, currentCombination: null, _sseCleanup: null });
        }
      );

      set({ _sseCleanup: cleanup });

    } catch (error) {
      console.error("Grid search error:", error);
      clearInterval(timerInterval);
      set({ isRunning: false, currentCombination: null, _sseCleanup: null });
    }
  },

  cancelSearch: () => {
    const { _sseCleanup } = get();
    if (_sseCleanup) _sseCleanup();
    set({ isRunning: false, currentCombination: null, _sseCleanup: null });
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
      _sseCleanup: null,
    });
  },
}));