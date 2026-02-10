import { create } from "zustand";
import { persist } from "zustand/middleware";
// Trigger IDE re-analysis after type updates

export interface BacktestConfig {
  id: string;
  symbol: string;
  strategy: string;
  timeframe: string;
  capital: string;
  leverage: string;
  riskPercent: string;
  params: any;
  startDate: Date | null;
  endDate: Date | null;
}

export interface BacktestState {
  // Navigation State
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;

  // Recent Configs
  recentConfigs: BacktestConfig[];
  loadConfig: (config: BacktestConfig) => void;

  // Configuration State
  mode: "single" | "batch" | "pine" | "history" | "grid-search" | "walk-forward" | "sensitivity" | "settings";
  symbol: string;
  strategy: string;
  timeframe: string;
  startDate: Date | null;
  endDate: Date | null;
  lookbackValue: number;
  lookbackUnit: "bars" | "hours" | "days" | "weeks" | "months";
  datePreset: string | null;  // For PresetPills

  // Strategy Parameters (Generic map for now)
  params: {
    rsi_period: number;
    ema_fast: number;
    ema_slow: number;
    tp1_rr: number;
    tp2_rr: number;
    sl_buffer_pct: number;
    overbought: number;
    oversold: number;
    [key: string]: number;
  };

  // Risk Management
  capital: string; // string to handle input field easier
  leverage: string;
  riskPercent: string;

  // Execution State
  isRunning: boolean;

  // Actions
  setMode: (mode: "single" | "batch" | "pine" | "history" | "grid-search" | "walk-forward" | "sensitivity" | "settings") => void;
  setSymbol: (symbol: string) => void;
  setStrategy: (strategy: string) => void;
  setTimeframe: (tf: string) => void;
  setParam: (key: string, value: number) => void;
  setCapital: (val: string) => void;
  setLeverage: (val: string) => void;
  setRiskPercent: (val: string) => void;
  setDateRange: (start: Date | null, end: Date | null) => void;
  setLookbackValue: (val: number) => void;
  setLookbackUnit: (unit: "bars" | "hours" | "days" | "weeks" | "months") => void;
  setDatePreset: (preset: string | null) => void;

  runBacktest: () => Promise<void>;
  resetParams: () => void;
  getEstimatedBars: () => number;
  getDaysDuration: () => number;
}

export const useBacktestStore = create<BacktestState>()(
  persist(
    (set, get) => ({
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),

      recentConfigs: [
        {
          id: "1",
          symbol: "BTC/USDT",
          strategy: "rsi_no_retest",
          timeframe: "4h",
          capital: "10000",
          leverage: "1",
          riskPercent: "1",
          params: { rsi_period: 14, ema_fast: 9, ema_slow: 21 },
          startDate: new Date("2024-01-01"),
          endDate: new Date("2024-03-01")
        },
        {
          id: "2",
          symbol: "ETH/USDT",
          strategy: "ema_crossover",
          timeframe: "1h",
          capital: "5000",
          leverage: "2",
          riskPercent: "2",
          params: { ema_fast: 12, ema_slow: 26 },
          startDate: new Date("2024-02-01"),
          endDate: new Date("2024-03-01")
        }
      ],
      loadConfig: (config) => set({
        symbol: config.symbol,
        strategy: config.strategy,
        timeframe: config.timeframe,
        capital: config.capital,
        leverage: config.leverage,
        riskPercent: config.riskPercent,
        params: { ...get().params, ...config.params },
        startDate: config.startDate,
        endDate: config.endDate
      }),

      mode: "single",
      symbol: "BTC/USDT",
      strategy: "rsi_no_retest",
      timeframe: "1h",
      startDate: new Date("2024-01-01"),
      endDate: new Date("2024-12-31"),
      lookbackValue: 30,
      lookbackUnit: "days",
      datePreset: null,

      params: {
        rsi_period: 14,
        ema_fast: 9,
        ema_slow: 21,
        tp1_rr: 1.5,
        tp2_rr: 3.0,
        sl_buffer_pct: 1.0,
        overbought: 70,
        oversold: 30,
      },

      capital: "10000",
      leverage: "1",
      riskPercent: "1",

      isRunning: false,

      setMode: (mode) => set({ mode }),
      setSymbol: (symbol) => set({ symbol }),
      setStrategy: (strategy) => set({ strategy }),
      setTimeframe: (timeframe) => set({ timeframe }),
      setParam: (key, value) =>
        set((state) => ({ params: { ...state.params, [key]: value } })),

      setCapital: (capital) => set({ capital }),
      setLeverage: (leverage) => set({ leverage }),
      setRiskPercent: (riskPercent) => set({ riskPercent }),
      setDateRange: (start, end) => set({ startDate: start, endDate: end }),
      setLookbackValue: (lookbackValue) => set({ lookbackValue }),
      setLookbackUnit: (unit) => set({ lookbackUnit: unit }),
      setDatePreset: (preset) => set({ datePreset: preset }),

      runBacktest: async () => {
        set({ isRunning: true });
        // Simulate API delay
        await new Promise((resolve) => setTimeout(resolve, 800));
        set({ isRunning: false });
      },

      resetParams: () => set({
        params: {
          rsi_period: 14,
          ema_fast: 9,
          ema_slow: 21,
          tp1_rr: 1.5,
          tp2_rr: 3.0,
          sl_buffer_pct: 1.0,
          overbought: 70,
          oversold: 30,
        },
        capital: "10000",
        leverage: "1",
        riskPercent: "1"
      }),

      getDaysDuration: () => {
        const { startDate, endDate } = get();
        if (!startDate || !endDate) return 0;
        // Handle potential string hydration from JSON
        const start = new Date(startDate);
        const end = new Date(endDate);
        const diff = end.getTime() - start.getTime();
        return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
      },

      getEstimatedBars: () => {
        const { timeframe } = get();
        const days = get().getDaysDuration();
        if (days === 0) return 0;

        let barsPerDay = 1;
        if (timeframe === '15m') barsPerDay = 96;
        if (timeframe === '1h') barsPerDay = 24;
        if (timeframe === '4h') barsPerDay = 6;
        if (timeframe === '1d') barsPerDay = 1;

        return days * barsPerDay;
      }
    }),
    {
      name: "backtest-config",
      partialize: (state) => ({
        mode: state.mode,
        symbol: state.symbol,
        strategy: state.strategy,
        timeframe: state.timeframe,
        params: state.params,
        capital: state.capital,
        leverage: state.leverage,
        riskPercent: state.riskPercent,
        startDate: state.startDate,
        endDate: state.endDate,
        recentConfigs: state.recentConfigs
      }),
    }
  )
);