import { create } from "zustand";
import { toast } from "sonner";
import {
  startBacktest,
  streamProgress,
  cancelBacktest as apiCancelBacktest,
  getRunDetail,
  getTimeseries,
} from "../api/backtest";
import { mapApiToResults, useResultsStore } from "./resultsStore";
import type { BacktestRequest, RunDetail, TimeseriesResponse } from "../types/api-types";

export interface SingleRunState {
  isRunning: boolean;
  runProgress: number;
  currentRunId: number | null;
  result: RunDetail | null;
  timeseries: TimeseriesResponse | null;
  run: (config: BacktestRequest) => Promise<void>;
  cancel: () => Promise<void>;
}

export const useSingleRunStore = create<SingleRunState>()((set, get) => ({
  isRunning: false,
  runProgress: 0,
  currentRunId: null,
  result: null,
  timeseries: null,

  run: async (config) => {
    set({ isRunning: true, runProgress: 0 });
    try {
      const { run_id } = await startBacktest(config);
      if (!run_id) throw new Error("Missing run_id");
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
              set({ result: detail, timeseries });
              // Sync back to original global store for backward compatibility
              useResultsStore.getState().setResults(mapApiToResults(detail, timeseries));
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
      toast.error(err instanceof Error ? err.message : "Single backtest failed");
    } finally {
      set({ isRunning: false, runProgress: 0, currentRunId: null });
    }
  },

  cancel: async () => {
    const { currentRunId } = get();
    if (currentRunId) {
      try {
        await apiCancelBacktest(currentRunId, "single");
      } catch {
        // Ignore
      }
    }
    set({ isRunning: false, runProgress: 0, currentRunId: null });
  },
}));
