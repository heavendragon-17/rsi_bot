import { create } from "zustand";
import { persist } from "zustand/middleware";

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
  batchSymbols: string[];
}

const getDefaultDates = () => {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  return { start, end };
};

export const DEFAULT_CONFIG = {
  mode: "single" as const,
  symbol: "BTC/USDT",
  batchSymbols: [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT",
    "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT", "UNI/USDT", "LINK/USDT"
  ],
  strategy: "rsi_no_retest",
  timeframe: "1h",
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
  lookbackValue: 30,
  lookbackUnit: "days" as const,
  dateMode: "relative" as const,
  timezone: "UTC",
};

export interface BacktestState {
  // Navigation State
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;

  // Recent Configs
  recentConfigs: BacktestConfig[];
  loadConfig: (config: BacktestConfig) => void;

  // Configuration State
  mode: "single" | "batch" | "pine" | "history" | "grid-search" | "grid-search-results" | "walk-forward" | "sensitivity" | "settings";
  symbol: string;
  batchSymbols: string[];
  strategy: string;
  timeframe: string;
  startDate: Date | null;
  endDate: Date | null;
  lookbackValue: number;
  lookbackUnit: "bars" | "hours" | "days" | "weeks" | "months";
  datePreset: string | null;
  dateMode: "relative" | "absolute";
  timezone: string;

  // Strategy Parameters
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
  capital: string;
  leverage: string;
  riskPercent: string;

  // Execution State
  isRunning: boolean;

  // Actions
  setMode: (mode: BacktestState["mode"]) => void;
  setSymbol: (symbol: string) => void;
  setBatchSymbols: (symbols: string[]) => void;
  setStrategy: (strategy: string) => void;
  setTimeframe: (tf: string) => void;
  setParam: (key: string, value: number) => void;
  setCapital: (val: string) => void;
  setLeverage: (val: string) => void;
  setRiskPercent: (val: string) => void;
  setDateRange: (start: Date | null, end: Date | null) => void;
  setLookbackValue: (val: number) => void;
  setLookbackUnit: (unit: BacktestState["lookbackUnit"]) => void;
  setDatePreset: (preset: string | null) => void;
  setDateMode: (mode: BacktestState["dateMode"]) => void;
  setTimezone: (tz: string) => void;

  runBacktest: () => Promise<void>;
  resetParams: () => void;
  resetToDefaults: () => void;
  getEstimatedBars: () => number;
  getDaysDuration: () => number;
}

export const useBacktestStore = create<BacktestState>()(
  persist(
    (set, get) => ({
      isSidebarOpen: true,
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),

      recentConfigs: [],
      loadConfig: (config) => set({
        symbol: config.symbol,
        batchSymbols: config.batchSymbols || DEFAULT_CONFIG.batchSymbols,
        strategy: config.strategy,
        timeframe: config.timeframe,
        capital: config.capital,
        leverage: config.leverage,
        riskPercent: config.riskPercent,
        params: { ...get().params, ...config.params },
        startDate: config.startDate,
        endDate: config.endDate
      }),

      mode: DEFAULT_CONFIG.mode,
      symbol: DEFAULT_CONFIG.symbol,
      batchSymbols: DEFAULT_CONFIG.batchSymbols,
      strategy: DEFAULT_CONFIG.strategy,
      timeframe: DEFAULT_CONFIG.timeframe,
      startDate: getDefaultDates().start,
      endDate: getDefaultDates().end,
      lookbackValue: DEFAULT_CONFIG.lookbackValue,
      lookbackUnit: DEFAULT_CONFIG.lookbackUnit,
      datePreset: null,
      dateMode: DEFAULT_CONFIG.dateMode,
      timezone: DEFAULT_CONFIG.timezone,

      params: { ...DEFAULT_CONFIG.params },
      capital: DEFAULT_CONFIG.capital,
      leverage: DEFAULT_CONFIG.leverage,
      riskPercent: DEFAULT_CONFIG.riskPercent,

      isRunning: false,

      setMode: (mode) => set({ mode }),
      setSymbol: (symbol) => set({ symbol }),
      setBatchSymbols: (symbols) => set({ batchSymbols: symbols }),
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
      setDateMode: (mode) => set({ dateMode: mode }),
      setTimezone: (tz) => set({ timezone: tz }),

      runBacktest: async () => {
        set({ isRunning: true });
        await new Promise((resolve) => setTimeout(resolve, 800));
        set({ isRunning: false });
      },

      resetParams: () => set({
        params: { ...DEFAULT_CONFIG.params },
        capital: DEFAULT_CONFIG.capital,
        leverage: DEFAULT_CONFIG.leverage,
        riskPercent: DEFAULT_CONFIG.riskPercent
      }),

      resetToDefaults: () => {
        const { start, end } = getDefaultDates();
        set({
          mode: DEFAULT_CONFIG.mode,
          symbol: DEFAULT_CONFIG.symbol,
          batchSymbols: DEFAULT_CONFIG.batchSymbols,
          strategy: DEFAULT_CONFIG.strategy,
          timeframe: DEFAULT_CONFIG.timeframe,
          params: { ...DEFAULT_CONFIG.params },
          capital: DEFAULT_CONFIG.capital,
          leverage: DEFAULT_CONFIG.leverage,
          riskPercent: DEFAULT_CONFIG.riskPercent,
          startDate: start,
          endDate: end,
          lookbackValue: DEFAULT_CONFIG.lookbackValue,
          lookbackUnit: DEFAULT_CONFIG.lookbackUnit,
          dateMode: DEFAULT_CONFIG.dateMode,
          datePreset: null,
          timezone: DEFAULT_CONFIG.timezone,
        });
      },

      getDaysDuration: () => {
        const { startDate, endDate } = get();
        if (!startDate || !endDate) return 0;
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
        batchSymbols: state.batchSymbols,
        strategy: state.strategy,
        timeframe: state.timeframe,
        params: state.params,
        capital: state.capital,
        leverage: state.leverage,
        riskPercent: state.riskPercent,
        startDate: state.startDate,
        endDate: state.endDate,
        dateMode: state.dateMode,
        timezone: state.timezone,
        recentConfigs: state.recentConfigs
      }),
    }
  )
);