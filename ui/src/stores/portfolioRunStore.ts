import { create } from "zustand";
import { toast } from "sonner";
import {
  startBacktest,
  streamProgress,
  cancelBacktest as apiCancelBacktest,
  getPortfolioRunDetail,
  getPortfolioTimeseries,
} from "../api/backtest";
import type { BacktestRequest, PortfolioRunDetail, PortfolioTimeseriesResponse } from "../types/api-types";

export interface PortfolioRunState {
  isRunning: boolean;
  runProgress: number;
  currentPortfolioRunId: number | null;
  result: PortfolioRunDetail | null;
  timeseries: PortfolioTimeseriesResponse | null;
  run: (config: BacktestRequest) => Promise<void>;
  cancel: () => Promise<void>;
}

export const usePortfolioRunStore = create<PortfolioRunState>()((set, get) => ({
  isRunning: false,
  runProgress: 0,
  currentPortfolioRunId: null,
  result: null,
  timeseries: null,

  run: async (config) => {
    set({ isRunning: true, runProgress: 0 });
    try {
      const { portfolio_run_id } = await startBacktest(config);
      if (!portfolio_run_id) throw new Error("Missing portfolio_run_id");
      set({ currentPortfolioRunId: portfolio_run_id });

      await new Promise<void>((resolve, reject) => {
        const cleanup = streamProgress(
          portfolio_run_id,
          (pct) => set({ runProgress: pct }),
          async () => {
            cleanup();
            try {
              const [detail, timeseries] = await Promise.all([
                getPortfolioRunDetail(portfolio_run_id),
                getPortfolioTimeseries(portfolio_run_id),
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
      toast.error(err instanceof Error ? err.message : "Portfolio backtest failed");
    } finally {
      set({ isRunning: false, runProgress: 0, currentPortfolioRunId: null });
    }
  },

  cancel: async () => {
    const { currentPortfolioRunId } = get();
    if (currentPortfolioRunId) {
      try {
        await apiCancelBacktest(currentPortfolioRunId, "portfolio");
      } catch {
        // Ignore
      }
    }
    set({ isRunning: false, runProgress: 0, currentPortfolioRunId: null });
  },
}));
