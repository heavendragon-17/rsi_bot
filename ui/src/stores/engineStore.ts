import { create } from "zustand";

const API_BASE = "http://localhost:8765/api";

export interface RunMetrics {
  net_profit: number;
  net_profit_pct: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
}

export interface RunResult {
  run_id: number;
  status: string;
  metrics: RunMetrics;
}

interface EngineState {
  isRunning: boolean;
  currentRunId: number | null;
  progress: number;
  progressMessage: string;
  result: RunResult | null;
  error: string | null;

  runBacktest: (sessionId: string, config: Record<string, unknown>) => Promise<void>;
  getRunResult: (runId: number) => Promise<RunResult>;
  reset: () => void;
}

export const useEngineStore = create<EngineState>((set) => ({
  isRunning: false,
  currentRunId: null,
  progress: 0,
  progressMessage: "",
  result: null,
  error: null,

  runBacktest: async (sessionId: string, config: Record<string, unknown>) => {
    set({ isRunning: true, progress: 0, progressMessage: "Submitting...", result: null, error: null });

    let runId: number;
    try {
      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, config }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      runId = data.run_id;
      set({ currentRunId: runId });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isRunning: false, error: msg, progressMessage: "" });
      return;
    }

    // Open SSE stream for progress
    await new Promise<void>((resolve) => {
      const eventSource = new EventSource(`${API_BASE}/backtest/${runId}/progress`);

      eventSource.addEventListener("progress", (e) => {
        const data = JSON.parse(e.data) as { pct: number; message: string };
        set({ progress: data.pct, progressMessage: data.message });
      });

      eventSource.addEventListener("done", (e) => {
        const data = JSON.parse(e.data) as RunResult;
        set({ isRunning: false, progress: 100, progressMessage: "Done", result: data });
        eventSource.close();
        resolve();
      });

      eventSource.addEventListener("error", (e) => {
        // SSE "error" event (custom, from server)
        try {
          const data = JSON.parse((e as MessageEvent).data) as { message: string };
          set({ isRunning: false, error: data.message, progressMessage: "" });
        } catch {
          set({ isRunning: false, error: "Backtest failed", progressMessage: "" });
        }
        eventSource.close();
        resolve();
      });

      // Network-level error
      eventSource.onerror = () => {
        set({ isRunning: false, error: "Connection lost", progressMessage: "" });
        eventSource.close();
        resolve();
      };
    });
  },

  getRunResult: async (runId: number) => {
    const res = await fetch(`${API_BASE}/backtest/${runId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch run ${runId}: HTTP ${res.status}`);
    }
    const data = await res.json();
    return { run_id: runId, status: data.run.status, metrics: data.metrics };
  },

  reset: () => set({ isRunning: false, currentRunId: null, progress: 0, progressMessage: "", result: null, error: null }),
}));
