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
import { mapApiToResults, useResultsStore } from "./resultsStore";
import { parse, format } from "date-fns";
import { fetchStrategies } from "../api/strategies";
import type { StrategyInfo } from "../types/generated";

export interface BacktestState {
  // Navigation State
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;

  // Configuration State
  mode: "single" | "batch" | "portfolio" | "history" | "grid-search" | "walk-forward" | "sensitivity";
  symbol: string;
  portfolioInput: string;
  strategy: string;
  availableStrategies: StrategyInfo[];
  timeframe: string;
  startDate: string;
  endDate: string;
  dateMode: "absolute" | "relative";
  timezone: string;
  lookbackValue: number;
  lookbackUnit: "bars" | "hours" | "days" | "weeks" | "months" | "years";
  datePreset: string | null;

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
  setTimezone: (tz: string) => void;
  setLookbackValue: (val: number) => void;
  setLookbackUnit: (unit: "bars" | "hours" | "days" | "weeks" | "months" | "years") => void;
  setDatePreset: (preset: string | null) => void;
  syncRelativeDates: () => void;
  loadConfig: (config: any) => void;
  loadStrategies: () => Promise<void>;

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
      availableStrategies: [],
      timeframe: "1h",
      startDate: "01-01-2024",
      endDate: "31-12-2024",
      dateMode: "relative",
      timezone: "UTC",
      lookbackValue: 300,
      lookbackUnit: "bars",
      datePreset: null,

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
      setTimeframe: (timeframe) => {
        set({ timeframe });
        get().syncRelativeDates();
      },
      setParam: (key, value) =>
        set((s) => ({ params: { ...s.params, [key]: Number(value) } })),
      setCapital: (capital) => set({ capital }),
      setLeverage: (leverage) => set({ leverage }),
      setRiskPercent: (riskPercent) => set({ riskPercent }),
      setDateRange: (start, end) => set({ startDate: start, endDate: end, dateMode: "absolute", datePreset: null }),
      setStartDate: (startDate) => {
        console.log("Store updating startDate to:", startDate);
        set({ startDate, dateMode: "absolute", datePreset: null });
      },
      setEndDate: (endDate) => set({ endDate, dateMode: "absolute", datePreset: null }),
      setTimezone: (timezone) => set({ timezone }),
      setDateMode: (dateMode) => {
        set({ dateMode });
        get().syncRelativeDates();
      },
      setLookbackValue: (lookbackValue) => {
        set({ lookbackValue, datePreset: null });
        get().syncRelativeDates();
      },
      setLookbackUnit: (lookbackUnit) => {
        set({ lookbackUnit, datePreset: null });
        get().syncRelativeDates();
      },
      setDatePreset: (preset) => {
        if (!preset) {
          set({ datePreset: null });
          return;
        }
        let val = 1;
        let unit: "bars" | "hours" | "days" | "weeks" | "months" | "years" = "days";
        switch (preset) {
          case "1D": val = 1; unit = "days"; break;
          case "1W": val = 1; unit = "weeks"; break;
          case "1M": val = 1; unit = "months"; break;
          case "3M": val = 3; unit = "months"; break;
          case "1Y": val = 1; unit = "years"; break;
          case "YTD": {
            const startOfYear = new Date(new Date().getFullYear(), 0, 1);
            const diffTime = Math.abs(new Date().getTime() - startOfYear.getTime());
            val = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            unit = "days";
            break;
          }
          case "All": {
            val = 20; // 20 years approximation for all data
            unit = "years";
            break;
          }
        }
        set({ datePreset: preset, lookbackValue: val, lookbackUnit: unit, dateMode: "relative" });
        get().syncRelativeDates();
      },
      syncRelativeDates: () => {
         const { dateMode, lookbackValue, lookbackUnit, timeframe } = get();
         if (dateMode !== "relative") return;

         const end = new Date();
         let start = new Date();

         if (lookbackUnit === "bars") {
           const barsPerDay: Record<string, number> = {
             "15m": 96, "1h": 24, "4h": 6, "1d": 1,
           };
           const bpd = barsPerDay[timeframe] || 24;
           const days = Math.ceil(lookbackValue / bpd);
           start.setDate(start.getDate() - days);
         } else if (lookbackUnit === "hours") {
           start.setHours(start.getHours() - lookbackValue);
         } else if (lookbackUnit === "days") {
           start.setDate(start.getDate() - lookbackValue);
         } else if (lookbackUnit === "weeks") {
           start.setDate(start.getDate() - lookbackValue * 7);
         } else if (lookbackUnit === "months") {
           start.setMonth(start.getMonth() - lookbackValue);
         } else if (lookbackUnit === "years") {
           start.setFullYear(start.getFullYear() - lookbackValue);
         }

         const format = (d: Date) => {
           const day = String(d.getDate()).padStart(2, '0');
           const month = String(d.getMonth() + 1).padStart(2, '0');
           const year = d.getFullYear();
           return `${day}-${month}-${year}`;
         };

         set({ startDate: format(start), endDate: format(end) });
      },
      loadConfig: (config) => {
        set((state) => ({ ...state, ...config }));
        get().syncRelativeDates();
      },

      // ── Real API + SSE ────────────────────────────────────────────────────

      runBacktest: async () => {
        const state = get();
        set({ isRunning: true, runProgress: 0 });

        try {
          const startDate = parse(state.startDate, "dd-MM-yyyy", new Date());
          const endDate = parse(state.endDate, "dd-MM-yyyy", new Date());

          if (state.mode === "batch") {
            const symbols = state.portfolioInput.split("\n").map(s => s.trim()).filter(s => s.length > 0);
            if (symbols.length === 0) throw new Error("No symbols provided for batch run.");

            // Start all backtests
            const runIds: { id: number, symbol: string }[] = [];
            const perConfigCap = parseFloat(state.capital) / symbols.length;

            for (const sym of symbols) {
              const { run_id } = await startBacktest({
                symbol: sym,
                timeframe: state.timeframe,
                strategy: state.strategy,
                start_date: format(startDate, "yyyy-MM-dd"),
                end_date: format(endDate, "yyyy-MM-dd"),
                initial_capital: perConfigCap.toString(),
                leverage: parseInt(state.leverage) || 1,
                risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
                params: state.params,
              });
              runIds.push({ id: run_id, symbol: sym });
            }

            set({ currentRunId: runIds[0].id });

            const progressMap = new Map<number, number>();
            const promises = runIds.map(({ id, symbol }) => new Promise<any>((resolve, reject) => {
              const cleanup = streamProgress(id,
                (pct) => {
                  progressMap.set(id, pct);
                  let total = 0;
                  progressMap.forEach(v => total += v);
                  set({ runProgress: total / symbols.length });
                },
                async () => {
                  cleanup();
                  try {
                    const [detail, timeseries] = await Promise.all([getRunDetail(id), getTimeseries(id)]);
                    resolve({ symbol, detail, timeseries, initialCapital: perConfigCap });
                  } catch (e) { reject(e); }
                },
                (err) => { cleanup(); reject(new Error(err)); }
              );
            }));

            const allResults = await Promise.all(promises);

            // Import util
            const { aggregateBatchResults } = await import("../lib/batch-utils");
            const aggregated = aggregateBatchResults(allResults);

            const { useBatchResultsStore } = await import("./batchResultsStore");
            useBatchResultsStore.getState().setBatchResults(aggregated);

            set({ isRunning: false, runProgress: 0, currentRunId: null });
            return;
          }

          if (state.mode === "portfolio") {
            const symbols = state.portfolioInput.split("\n").map(s => s.trim()).filter(s => s.length > 0);
            if (symbols.length === 0) throw new Error("No symbols provided for portfolio run.");

            const { run_id } = await startBacktest({
              symbols: symbols,
              timeframe: state.timeframe,
              strategy: state.strategy,
              start_date: format(startDate, "yyyy-MM-dd"),
              end_date: format(endDate, "yyyy-MM-dd"),
              initial_capital: state.capital,
              leverage: parseInt(state.leverage) || 1,
              risk_per_trade_pct: (parseFloat(state.riskPercent) / 100).toFixed(4),
              params: state.params,
            });

            set({ currentRunId: run_id });

            await new Promise<void>((resolve, reject) => {
              const cleanup = streamProgress(
                run_id,
                (pct) => set({ runProgress: pct }),
                async () => {
                  cleanup();
                  try {
                    const [detail, timeseries] = await Promise.all([
                      getRunDetail(run_id),
                      getTimeseries(run_id),
                    ]);
                    useResultsStore.getState().setResults(
                      mapApiToResults(detail, timeseries)
                    );
                    resolve();
                  } catch (fetchErr) {
                    reject(fetchErr);
                  }
                },
                (msg) => {
                  cleanup();
                  reject(new Error(msg));
                }
              );
            });

            set({ isRunning: false, runProgress: 100, currentRunId: null });
            return;
          }

          // Single run mode
          const { run_id } = await startBacktest({
            symbol: state.symbol,
            timeframe: state.timeframe,
            strategy: state.strategy,
            start_date: format(startDate, "yyyy-MM-dd"),
            end_date: format(endDate, "yyyy-MM-dd"),
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
                // Instantly clean up to prevent EventSource from firing onerror when server closes
                cleanup();

                // 4. On complete: fetch results and push to resultsStore
                try {
                  const [detail, timeseries] = await Promise.all([
                    getRunDetail(run_id),
                    getTimeseries(run_id),
                  ]);
                  useResultsStore.getState().setResults(
                    mapApiToResults(detail, timeseries),
                  );
                  resolve();
                } catch (fetchErr) {
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

      loadStrategies: async () => {
        try {
          const strategies = await fetchStrategies();
          set({ availableStrategies: strategies });
        } catch (err) {
          console.error("Failed to load strategies:", err);
        }
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
        timezone: state.timezone,
        lookbackValue: state.lookbackValue,
        lookbackUnit: state.lookbackUnit,
        datePreset: state.datePreset,
        recentConfigs: state.recentConfigs,
      }),
    },
  ),
);
