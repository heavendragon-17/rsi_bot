/**
 * Backtest API functions.
 */

import { apiFetch, apiSSE } from "./client";
import type {
  BacktestRequest,
  BacktestStartResponse,
  RunDetail,
  TimeseriesResponse,
  BatchRunDetail,
  BatchTimeseriesResponse,
  PortfolioRunDetail,
  PortfolioTimeseriesResponse,
} from "../types/api-types";

// ---------------------------------------------------------------------------
// startBacktest
// ---------------------------------------------------------------------------

/**
 * POST /api/backtest/run
 * Returns run_id and initial status.
 * Pass `symbol` for single-symbol mode or `symbols` (array) for portfolio mode.
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
  onProgress: (pct: number, payload?: any) => void,
  onComplete: (data: { run_id: number; status: string }) => void,
  onError: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/backtest/${runId}/progress`,
    (eventName, data) => {
      if (eventName === "progress") {
        const d = data as { pct?: number; symbol?: string; symbol_status?: string };
        onProgress(d.pct ?? 0, d);
      } else if (eventName === "complete") {
        onComplete(data as { run_id: number; status: string });
      } else if (eventName === "error" || eventName === "symbol_error") {
        const d = data as { message?: string; symbol?: string };
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
export async function cancelBacktest(runId: number, mode: string = "single"): Promise<void> {
  await apiFetch<void>(`/api/backtest/${runId}?mode=${mode}`, { method: "DELETE" });
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

export async function getBatchRunDetail(id: number): Promise<BatchRunDetail> {
  return apiFetch<BatchRunDetail>(`/api/backtest/batch/${id}`);
}

export async function getBatchTimeseries(id: number): Promise<BatchTimeseriesResponse> {
  return apiFetch<BatchTimeseriesResponse>(`/api/backtest/batch/${id}/timeseries`);
}

export async function getPortfolioRunDetail(id: number): Promise<PortfolioRunDetail> {
  return apiFetch<PortfolioRunDetail>(`/api/backtest/portfolio/${id}`);
}

export async function getPortfolioTimeseries(id: number): Promise<PortfolioTimeseriesResponse> {
  return apiFetch<PortfolioTimeseriesResponse>(`/api/backtest/portfolio/${id}/timeseries`);
}
