import { create } from "zustand";
import { persist } from "zustand/middleware";
import { toast } from "sonner";
import {
  startBacktest,
  streamProgress,
  cancelBacktest as apiCancelBacktest,
  getRunDetail,
  getTimeseries,
} from "../api/backtest";
import { checkDataStatus } from "../api/data";
import { mapApiToResults, useResultsStore } from "./resultsStore";
import { parse } from "date-fns";

export interface BacktestState {
  // Navigation State
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;

  // Configuration State
  mode: "single" | "batch" | "pine" | "history" | "grid-search" | "walk-forward" | "sensitivity";
  symbol: string;
  portfolioInput: string;
  strategy: string;
  timeframe: string;
  startDate: string;
  endDate: string;
  dateMode: "absolute" | "relative";
  lookbackValue: number;
  lookbackUnit: "bars" | "hours" | "days" | "weeks" | "months";

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
  runProgress: number;        // 0-100
  currentRunId: number | null;
  recentConfigs: any[];

  // Actions
  setMode: (mode: BacktestState["mode"]) => void;
  setSymbol: (symbol: string) => void;
  setPortfolioInput: (input: string) => void;
  setStrategy: (strategy: string) => void;
  setTimeframe: (tf: string) => void;
  setParam: (key: string, value: number) => void;
  setCapital: (val: string) => void;
  setLeverage: (val: string) => void;
  setRiskPercent: (val: string) => void;
  setDateRange: (start: string, end: string) => void;
  setStartDate: (date: string) => void;
  setEndDate: (date: string) => void;
  setDateMode: (mode: "absolute" | "relative") => void;
  setLookbackValue: (val: number) => void;
  setLookbackUnit: (unit: "bars" | "hours" | "days" | "weeks" | "months") => void;
  loadConfig: (config: any) => void;

  runBacktest: () => Promise<void>;
  cancelBacktest: () => Promise<void>;
  resetParams: () => void;
  getEstimatedBars: () => number;
  getDaysDuration: () => number;
}

const DEFAULT_PARAMS = {
  rsi_period: 14,
  ema_fast: 9,
  ema_slow: 21,
  tp1_rr: 1.5,
  tp2_rr: 3.0,
  sl_buffer_pct: 1.0,
  overbought: 70,
  oversold: 30,
};

export const useBacktestStore = create<BacktestState>()(
  persist(
    (set, get) => ({
      isSidebarOpen: true,
      toggleSidebar: () => set((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
      setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),

      mode: "single",
      symbol: "BTC/USDT",
      portfolioInput: "BTC/USDT\nETH/USDT\nSOL/USDT\nBNB/USDT\nADA/USDT\nXRP/USDT\nDOGE/USDT\nDOT/USDT\nMATIC/USDT\nLTC/USDT\nUNI/USDT\nLINK/USDT",
      strategy: "rsi_no_retest",
      timeframe: "1h",
      startDate: "01-01-2024",
      endDate: "31-12-2024",
      dateMode: "relative",
      lookbackValue: 300,
      lookbackUnit: "bars",

      params: { ...DEFAULT_PARAMS },

      capital: "10000",
      leverage: "1",
      riskPercent: "1",

      isRunning: false,
      runProgress: 0,
      currentRunId: null,
      recentConfigs: [],

      setMode: (mode) => set({ mode }),
      setSymbol: (symbol) => set({ symbol }),
      setPortfolioInput: (portfolioInput) => set({ portfolioInput }),
      setStrategy: (strategy) => set({ strategy }),
      setTimeframe: (timeframe) => set({ timeframe }),
      setParam: (key, value) =>
        set((s) => ({ params: { ...s.params, [key]: value } })),
      setCapital: (capital) => set({ capital }),
      setLeverage: (leverage) => set({ leverage }),
      setRiskPercent: (riskPercent) => set({ riskPercent }),
      setDateRange: (start, end) => set({ startDate: start, endDate: end }),
      setStartDate: (startDate) => {
        console.log("Store updating startDate to:", startDate);
        set({ startDate });
      },
      setEndDate: (endDate) => set({ endDate }),
      setDateMode: (dateMode) => set({ dateMode }),
      setLookbackValue: (lookbackValue) => set({ lookbackValue }),
      setLookbackUnit: (lookbackUnit) => set({ lookbackUnit }),
      loadConfig: (config) => set((state) => ({ ...state, ...config })),

      // ── Real API + SSE ────────────────────────────────────────────────────

      runBacktest: async () => {
        const state = get();
        set({ isRunning: true, runProgress: 0 });

        try {
          // 1. Fail fast: check data file exists
          const dataStatus = await checkDataStatus(state.symbol, state.timeframe);
          if (!dataStatus.available) {
            throw new Error(
              `No data for ${state.symbol} ${state.timeframe}. Download data first.`,
            );
          }

          // 2. Start backtest via API
          const startDate = parse(state.startDate, "dd-MM-yyyy", new Date());
          const endDate = parse(state.endDate, "dd-MM-yyyy", new Date());

          const { run_id } = await startBacktest({
            symbol: state.symbol,
            timeframe: state.timeframe,
            strategy: state.strategy,
            start_date: startDate.toISOString().split("T")[0],
            end_date: endDate.toISOString().split("T")[0],
            initial_capital: state.capital,
            leverage: parseInt(state.leverage) || 1,
            risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
            params: state.params,
          });

          set({ currentRunId: run_id });

          // 3. SSE — store owns the EventSource connection
          await new Promise<void>((resolve, reject) => {
            const cleanup = streamProgress(
              run_id,
              (pct) => set({ runProgress: pct }),
              async () => {
                // 4. On complete: fetch results and push to resultsStore
                try {
                  const [detail, timeseries] = await Promise.all([
                    getRunDetail(run_id),
                    getTimeseries(run_id),
                  ]);
                  useResultsStore.getState().setResults(
                    mapApiToResults(detail, timeseries),
                  );
                  cleanup();
                  resolve();
                } catch (fetchErr) {
                  cleanup();
                  reject(fetchErr);
                }
              },
              (msg) => {
                cleanup();
                reject(new Error(msg));
              },
            );
          });
        } catch (err) {
          toast.error(err instanceof Error ? err.message : "Backtest failed");
        } finally {
          set({ isRunning: false, runProgress: 0, currentRunId: null });
        }
      },

      cancelBacktest: async () => {
        const { currentRunId } = get();
        if (currentRunId) {
          try {
            await apiCancelBacktest(currentRunId);
          } catch {
            // Ignore — state reset is the priority
          }
        }
        set({ isRunning: false, runProgress: 0, currentRunId: null });
      },

      resetParams: () =>
        set({
          params: { ...DEFAULT_PARAMS },
          capital: "10000",
          leverage: "1",
          riskPercent: "1",
        }),

      getDaysDuration: () => {
        const { startDate, endDate } = get();
        if (!startDate || !endDate) return 0;
        const start = parse(startDate, "dd-MM-yyyy", new Date());
        const end = parse(endDate, "dd-MM-yyyy", new Date());
        return Math.max(0, Math.floor((end.getTime() - start.getTime()) / 86_400_000));
      },

      getEstimatedBars: () => {
        const { timeframe } = get();
        const days = get().getDaysDuration();
        if (days === 0) return 0;
        const barsPerDay: Record<string, number> = {
          "15m": 96,
          "1h": 24,
          "4h": 6,
          "1d": 1,
        };
        return days * (barsPerDay[timeframe] ?? 24);
      },
    }),
    {
      name: "backtest-config-v2",
      // Only persist configuration — not runtime state
      partialize: (state) => ({
        mode: state.mode,
        symbol: state.symbol,
        portfolioInput: state.portfolioInput,
        strategy: state.strategy,
        timeframe: state.timeframe,
        params: state.params,
        capital: state.capital,
        leverage: state.leverage,
        riskPercent: state.riskPercent,
        startDate: state.startDate,
        endDate: state.endDate,
        dateMode: state.dateMode,
        lookbackValue: state.lookbackValue,
        lookbackUnit: state.lookbackUnit,
        recentConfigs: state.recentConfigs,
      }),
    },
  ),
);
