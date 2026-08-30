import { create } from "zustand";
import {
  getSignalChart,
  getSignalReplayAvailability,
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
  SignalReplayAvailabilityResponse,
  SignalReplayRunSummary,
  SignalReplaySignalDetail,
  SignalReplaySignalSummary,
  SignalReviewUpdate,
} from "../types/generated";
import {
  REVIEW_CHART_CHUNK_CANDLES,
  REVIEW_SIGNAL_PAGE_SIZE,
} from "../lib/signal-review";

export type SignalReplayScope = "all" | "30d" | "90d" | "365d";
export type ReviewSaveState = "idle" | "saving" | "saved" | "error";

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
  selectedRunId: number | null;
  availability: SignalReplayAvailabilityResponse | null;
  activeRunId: number | null;
  runProgress: number;
  runPhase: string;
  isLoading: boolean;
  isLoadingDetail: boolean;
  isLoadingAvailability: boolean;
  isRunning: boolean;
  reviewSaveState: ReviewSaveState;
  error: string | null;
  initialize: () => Promise<void>;
  setTimeframe: (timeframe: "5m" | "15m") => void;
  setQualityFilter: (quality: string) => void;
  setOutcomeFilter: (outcome: string) => void;
  setSelectedRunId: (runId: number) => void;
  loadSignals: (page?: number) => Promise<void>;
  loadRuns: () => Promise<void>;
  loadAvailability: () => Promise<void>;
  loadSignal: (signalId: number) => Promise<void>;
  loadAdjacentSignal: (direction: -1 | 1) => Promise<void>;
  loadMoreChart: () => Promise<void>;
  saveReview: (patch: SignalReviewUpdate) => Promise<void>;
  monitorReplay: (runId: number) => Promise<void>;
  startReplay: (scope: SignalReplayScope) => Promise<void>;
  clearSelection: () => void;
}

function replayWindow(
  availability: SignalReplayAvailabilityResponse,
  scope: SignalReplayScope,
): { start: string; end: string } {
  if (!availability.common_start_at || !availability.common_end_at) {
    throw new Error("The replay sources do not have a common date range");
  }
  const earliest = new Date(availability.common_start_at);
  const latest = new Date(availability.common_end_at);
  if (scope === "all") {
    return { start: earliest.toISOString(), end: latest.toISOString() };
  }
  const days = scope === "30d" ? 30 : scope === "90d" ? 90 : 365;
  const requestedStart = new Date(latest.getTime() - days * 24 * 60 * 60 * 1000);
  return {
    start: new Date(Math.max(earliest.getTime(), requestedStart.getTime())).toISOString(),
    end: latest.toISOString(),
  };
}

export const useSignalReviewStore = create<SignalReviewState>((set, get) => ({
  timeframe: "5m",
  qualityFilter: "UNREVIEWED",
  outcomeFilter: "",
  signals: [],
  total: 0,
  page: 1,
  pages: 1,
  selected: null,
  chart: null,
  runs: [],
  selectedRunId: null,
  availability: null,
  activeRunId: null,
  runProgress: 0,
  runPhase: "idle",
  isLoading: false,
  isLoadingDetail: false,
  isLoadingAvailability: false,
  isRunning: false,
  reviewSaveState: "idle",
  error: null,

  initialize: async () => {
    await Promise.all([get().loadAvailability(), get().loadRuns()]);
    await get().loadSignals(1);
  },

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

  setSelectedRunId: (selectedRunId) => {
    set({ selectedRunId, selected: null, chart: null });
    void get().loadSignals(1);
  },

  loadSignals: async (page = get().page) => {
    const state = get();
    if (state.selectedRunId == null) {
      set({ signals: [], total: 0, page: 1, pages: 1, isLoading: false });
      return;
    }
    set({ isLoading: true, error: null });
    try {
      const filters: SignalReplayListFilters = {
        timeframe: state.timeframe,
        replay_run_id: state.selectedRunId,
        quality: state.qualityFilter || undefined,
        human_outcome: state.outcomeFilter || undefined,
        page,
        limit: REVIEW_SIGNAL_PAGE_SIZE,
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
      const runs = await listSignalReplayRuns();
      const currentRunId = get().selectedRunId;
      const completedRuns = runs.filter((run) => run.status === "completed");
      const selectedRunId = completedRuns.some((run) => run.id === currentRunId)
        ? currentRunId
        : (completedRuns[0]?.id ?? null);
      set({ runs, selectedRunId });
      const active = runs.find((run) => run.status === "running");
      if (active && !get().isRunning) {
        void get().monitorReplay(active.id);
      }
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to load replay runs" });
    }
  },

  loadAvailability: async () => {
    set({ isLoadingAvailability: true });
    try {
      const availability = await getSignalReplayAvailability();
      set({ availability, isLoadingAvailability: false });
    } catch (error) {
      set({
        isLoadingAvailability: false,
        error: error instanceof Error ? error.message : "Failed to inspect replay data",
      });
    }
  },

  loadSignal: async (signalId) => {
    set({ isLoadingDetail: true, error: null, reviewSaveState: "idle" });
    try {
      const [selected, chart] = await Promise.all([
        getSignalReplaySignal(signalId),
        getSignalChart(signalId),
      ]);
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
      new Date(currentEnd).getTime()
      + minutes * REVIEW_CHART_CHUNK_CANDLES * 60_000,
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
    const signalId = state.selected.id;
    const previousReview = state.selected.review;
    set({ reviewSaveState: "saving", error: null });
    try {
      const review = await updateSignalReview(signalId, patch);
      const current = get();
      const selected = current.selected?.id === signalId
        ? { ...current.selected, review }
        : current.selected;
      const signals = current.signals.map((signal) =>
        signal.id === signalId
          ? {
              ...signal,
              quality: review.quality,
              human_outcome: review.human_outcome,
              note_present: Boolean(review.note),
            }
          : signal,
      );
      set({ selected, signals, reviewSaveState: "saved" });

      const wasUnlocked = previousReview.quality !== "UNREVIEWED";
      const isUnlocked = review.quality !== "UNREVIEWED";
      if (selected?.id === signalId && wasUnlocked !== isUnlocked) {
        const chart = await getSignalChart(signalId, {
          start: current.chart?.requested_start ?? undefined,
        });
        if (get().selected?.id === signalId) set({ chart });
      }
    } catch (error) {
      set({
        reviewSaveState: "error",
        error: error instanceof Error ? error.message : "Failed to save review",
      });
    }
  },

  monitorReplay: async (runId) => {
    if (get().isRunning && get().activeRunId === runId) return;
    set({
      isRunning: true,
      activeRunId: runId,
      runProgress: 0,
      runPhase: "starting",
      error: null,
    });
    try {
      await new Promise<void>((resolve, reject) => {
        let cleanup: (() => void) | null = null;
        cleanup = streamSignalReplayProgress(
          runId,
          (pct, phase) => set({ runProgress: pct, runPhase: phase ?? "signals" }),
          async () => {
            cleanup?.();
            set({ runProgress: 100, runPhase: "complete", selectedRunId: runId });
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
      set({ isRunning: false, activeRunId: null });
    }
  },

  startReplay: async (scope) => {
    try {
      let availability = get().availability;
      if (!availability) {
        await get().loadAvailability();
        availability = get().availability;
      }
      if (!availability?.ready) {
        throw new Error("Prepare all four replay data files before building the dataset");
      }
      set({ isRunning: true, runProgress: 0, runPhase: "starting", error: null });
      const range = replayWindow(availability, scope);
      const { run_id: runId } = await startSignalReplay(range);
      set({ selectedRunId: runId });
      await get().monitorReplay(runId);
    } catch (error) {
      set({
        isRunning: false,
        activeRunId: null,
        error: error instanceof Error ? error.message : "Replay failed",
      });
    }
  },

  clearSelection: () => set({ selected: null, chart: null, reviewSaveState: "idle" }),
}));
