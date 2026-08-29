import { create } from "zustand";
import {
  getSignalChart,
  getSignalReplaySignal,
  listSignalReplaySignals,
  listSignalReplayRuns,
  startSignalReplay,
  streamSignalReplayProgress,
  updateSignalReview,
  type SignalReplayListFilters,
} from "../api/signalReplay";
import type {
  SignalChartResponse,
  SignalReplayRunSummary,
  SignalReplaySignalDetail,
  SignalReplaySignalSummary,
  SignalReviewUpdate,
} from "../types/generated";

interface SignalReviewState {
  timeframe: "5m" | "15m";
  qualityFilter: string;
  outcomeFilter: string;
  signals: SignalReplaySignalSummary[];
  total: number;
  page: number;
  pages: number;
  selected: SignalReplaySignalDetail | null;
  chart: SignalChartResponse | null;
  runs: SignalReplayRunSummary[];
  activeRunId: number | null;
  runProgress: number;
  runPhase: string;
  isLoading: boolean;
  isLoadingDetail: boolean;
  isRunning: boolean;
  error: string | null;
  setTimeframe: (timeframe: "5m" | "15m") => void;
  setQualityFilter: (quality: string) => void;
  setOutcomeFilter: (outcome: string) => void;
  loadSignals: (page?: number) => Promise<void>;
  loadRuns: () => Promise<void>;
  loadSignal: (signalId: number) => Promise<void>;
  loadAdjacentSignal: (direction: -1 | 1) => Promise<void>;
  loadMoreChart: () => Promise<void>;
  saveReview: (patch: SignalReviewUpdate) => Promise<void>;
  startReplay: (start?: string, end?: string) => Promise<void>;
  clearSelection: () => void;
}

export const useSignalReviewStore = create<SignalReviewState>((set, get) => ({
  timeframe: "5m",
  qualityFilter: "",
  outcomeFilter: "",
  signals: [],
  total: 0,
  page: 1,
  pages: 1,
  selected: null,
  chart: null,
  runs: [],
  activeRunId: null,
  runProgress: 0,
  runPhase: "idle",
  isLoading: false,
  isLoadingDetail: false,
  isRunning: false,
  error: null,

  setTimeframe: (timeframe) => {
    set({ timeframe, selected: null, chart: null });
    void get().loadSignals(1);
  },

  setQualityFilter: (qualityFilter) => {
    set({ qualityFilter });
    void get().loadSignals(1);
  },

  setOutcomeFilter: (outcomeFilter) => {
    set({ outcomeFilter });
    void get().loadSignals(1);
  },

  loadSignals: async (page = get().page) => {
    set({ isLoading: true, error: null });
    try {
      const state = get();
      const filters: SignalReplayListFilters = {
        timeframe: state.timeframe,
        quality: state.qualityFilter || undefined,
        human_outcome: state.outcomeFilter || undefined,
        page,
        limit: 50,
      };
      const response = await listSignalReplaySignals(filters);
      set({
        signals: response.signals,
        total: response.total,
        page: response.page,
        pages: response.pages,
        isLoading: false,
      });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to load signals",
      });
    }
  },

  loadRuns: async () => {
    try {
      set({ runs: await listSignalReplayRuns() });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to load replay runs" });
    }
  },

  loadSignal: async (signalId) => {
    set({ isLoadingDetail: true, error: null });
    try {
      const selected = await getSignalReplaySignal(signalId);
      const chart = await getSignalChart(signalId);
      set({ selected, chart, isLoadingDetail: false });
    } catch (error) {
      set({
        isLoadingDetail: false,
        error: error instanceof Error ? error.message : "Failed to load signal",
      });
    }
  },

  loadAdjacentSignal: async (direction) => {
    const state = get();
    if (!state.selected) return;
    const index = state.signals.findIndex((signal) => signal.id === state.selected?.id);
    if (index < 0) return;

    let target = state.signals[index + direction];
    if (!target && direction === 1 && state.page < state.pages) {
      await get().loadSignals(state.page + 1);
      target = get().signals[0];
    } else if (!target && direction === -1 && state.page > 1) {
      await get().loadSignals(state.page - 1);
      const pageSignals = get().signals;
      target = pageSignals[pageSignals.length - 1];
    }
    if (target) await get().loadSignal(target.id);
  },

  loadMoreChart: async () => {
    const state = get();
    if (!state.selected || !state.chart?.has_after) return;
    const currentEnd = state.chart.requested_end;
    if (!currentEnd) return;
    const minutes = state.selected.timeframe === "5m" ? 5 : 15;
    const nextEnd = new Date(
      new Date(currentEnd).getTime() + minutes * 500 * 60_000,
    ).toISOString();
    try {
      const chart = await getSignalChart(state.selected.id, {
        start: state.chart.requested_start ?? undefined,
        end: nextEnd,
      });
      set({ chart });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to load more chart data" });
    }
  },

  saveReview: async (patch) => {
    const state = get();
    if (!state.selected) return;
    try {
      const review = await updateSignalReview(state.selected.id, patch);
      const selected = { ...state.selected, review };
      set({ selected });
      await get().loadSignals(state.page);
      const chart = await getSignalChart(selected.id, {
        start: state.chart?.requested_start ?? undefined,
      });
      set({ chart });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to save review" });
    }
  },

  startReplay: async (start, end) => {
    set({ isRunning: true, runProgress: 0, runPhase: "starting", error: null });
    try {
      const { run_id: runId } = await startSignalReplay({ start, end });
      set({ activeRunId: runId });
      await new Promise<void>((resolve, reject) => {
        let cleanup: (() => void) | null = null;
        cleanup = streamSignalReplayProgress(
          runId,
          (pct, phase) => set({ runProgress: pct, runPhase: phase ?? "replay" }),
          async () => {
            cleanup?.();
            await get().loadRuns();
            await get().loadSignals(1);
            resolve();
          },
          (message) => {
            cleanup?.();
            reject(new Error(message));
          },
        );
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Replay failed" });
    } finally {
      set({ isRunning: false, activeRunId: null, runProgress: 100, runPhase: "idle" });
    }
  },

  clearSelection: () => set({ selected: null, chart: null }),
}));
