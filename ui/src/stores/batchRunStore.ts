import { create } from "zustand";
import { toast } from "sonner";
import {
  startBacktest,
  streamProgress,
  cancelBacktest as apiCancelBacktest,
  getBatchRunDetail,
  getBatchTimeseries,
} from "../api/backtest";
import type { BacktestRequest, BatchRunDetail, BatchTimeseriesResponse } from "../types/api-types";

export interface BatchRunState {
  isRunning: boolean;
  runProgress: number;
  completedSymbols: number;
  totalSymbols: number;
  symbolStatuses: Record<string, "pending" | "running" | "completed" | "failed">;
  currentBatchRunId: number | null;
  result: BatchRunDetail | null;
  timeseries: BatchTimeseriesResponse | null;
  run: (config: BacktestRequest) => Promise<void>;
  cancel: () => Promise<void>;
}

export const useBatchRunStore = create<BatchRunState>()((set, get) => ({
  isRunning: false,
  runProgress: 0,
  completedSymbols: 0,
  totalSymbols: 0,
  symbolStatuses: {},
  currentBatchRunId: null,
  result: null,
  timeseries: null,

  run: async (config) => {
    set({
      isRunning: true,
      runProgress: 0,
      completedSymbols: 0,
      totalSymbols: config.symbols.length,
      symbolStatuses: {}
    });
    try {
      const { batch_run_id } = await startBacktest(config);
      if (!batch_run_id) throw new Error("Missing batch_run_id");
      set({ currentBatchRunId: batch_run_id });

      await new Promise<void>((resolve, reject) => {
        const cleanup = streamProgress(
          batch_run_id,
          (pct, payload) => {
            set({ runProgress: pct });
            if (payload && payload.symbol && payload.symbol_status) {
                 set((state) => ({
                      symbolStatuses: { ...state.symbolStatuses, [payload.symbol]: payload.symbol_status },
                      completedSymbols: payload.completed || state.completedSymbols
                 }));
            }
          },
          async () => {
            cleanup();
            try {
              const [detail, timeseries] = await Promise.all([
                getBatchRunDetail(batch_run_id),
                getBatchTimeseries(batch_run_id),
              ]);
              set({ result: detail, timeseries });
              resolve();
            } catch (err) {
              reject(err);
            }
          },
          (msg) => {
            cleanup();
            reject(new Error(msg));
          }
        );
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Batch backtest failed");
    } finally {
      set({ isRunning: false, runProgress: 0, currentBatchRunId: null });
    }
  },

  cancel: async () => {
    const { currentBatchRunId } = get();
    if (currentBatchRunId) {
      try {
        await apiCancelBacktest(currentBatchRunId, "batch");
      } catch {
        // Ignore
      }
    }
    set({ isRunning: false, runProgress: 0, currentBatchRunId: null });
  },
}));
