/**
 * Backtest API functions.
 */

import { apiFetch, apiSSE } from "./client";
import type {
  BacktestRequest,
  BacktestStartResponse,
  RunDetail,
  TimeseriesResponse,
} from "../types/api-types";

// ---------------------------------------------------------------------------
// startBacktest
// ---------------------------------------------------------------------------

/**
 * POST /api/backtest/run
 * Returns run_id and initial status.
 * Throws ApiError 400 if data file is missing or strategy is unknown.
 */
export async function startBacktest(
  params: BacktestRequest,
): Promise<BacktestStartResponse> {
  return apiFetch<BacktestStartResponse>("/api/backtest/run", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ---------------------------------------------------------------------------
// streamProgress
// ---------------------------------------------------------------------------

/**
 * GET /api/backtest/{run_id}/progress  (SSE)
 *
 * @param runId      - active run ID
 * @param onProgress - called with progress percentage (0-100) on each tick
 * @param onComplete - called when the run finishes successfully
 * @param onError    - called if the run fails or the connection drops
 * @returns cleanup function — call it to close the EventSource early
 */
export function streamProgress(
  runId: number,
  onProgress: (pct: number) => void,
  onComplete: (data: { run_id: number; status: string }) => void,
  onError: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/backtest/${runId}/progress`,
    (eventName, data) => {
      if (eventName === "progress") {
        const d = data as { pct?: number };
        onProgress(d.pct ?? 0);
      } else if (eventName === "complete") {
        onComplete(data as { run_id: number; status: string });
      } else if (eventName === "error") {
        const d = data as { message?: string };
        onError(d.message ?? "Unknown backtest error");
      }
    },
    () => onError("SSE connection lost"),
  );
}

// ---------------------------------------------------------------------------
// cancelBacktest
// ---------------------------------------------------------------------------

/** DELETE /api/backtest/{run_id} */
export async function cancelBacktest(runId: number): Promise<void> {
  await apiFetch<void>(`/api/backtest/${runId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// getRunDetail
// ---------------------------------------------------------------------------

/** GET /api/backtest/{run_id} — full metrics + trades (no timeseries) */
export async function getRunDetail(runId: number): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/api/backtest/${runId}`);
}

// ---------------------------------------------------------------------------
// getTimeseries
// ---------------------------------------------------------------------------

/** GET /api/backtest/{run_id}/timeseries — lazy-load equity + drawdown curves */
export async function getTimeseries(runId: number): Promise<TimeseriesResponse> {
  return apiFetch<TimeseriesResponse>(`/api/backtest/${runId}/timeseries`);
}
