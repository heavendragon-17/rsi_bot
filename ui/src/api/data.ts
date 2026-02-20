/**
 * Data availability and download API functions.
 */

import { apiFetch, apiSSE } from "./client";
import type { DataStatusResponse, DownloadStartResponse } from "../types/api-types";

// ---------------------------------------------------------------------------
// checkDataStatus
// ---------------------------------------------------------------------------

/**
 * GET /api/data/status?symbol=BTC/USDT&timeframe=5m
 * Returns whether a CSV file exists for the given symbol/timeframe.
 */
export async function checkDataStatus(
  symbol: string,
  timeframe: string,
): Promise<DataStatusResponse> {
  const params = new URLSearchParams({ symbol, timeframe });
  return apiFetch<DataStatusResponse>(`/api/data/status?${params.toString()}`);
}

// ---------------------------------------------------------------------------
// startDownload
// ---------------------------------------------------------------------------

/**
 * POST /api/data/download
 * Initiates an async download of historical candle data.
 * Returns a job_id to track progress via SSE.
 */
export async function startDownload(
  symbol: string,
  timeframe: string,
  limit: number = 5000,
): Promise<DownloadStartResponse> {
  return apiFetch<DownloadStartResponse>("/api/data/download", {
    method: "POST",
    body: JSON.stringify({ symbol, timeframe, limit }),
  });
}

// ---------------------------------------------------------------------------
// streamDownload
// ---------------------------------------------------------------------------

/**
 * GET /api/data/download/{job_id}/progress  (SSE)
 *
 * @param jobId      - job ID returned by startDownload()
 * @param onProgress - called with progress percentage (0-100) on each tick
 * @param onComplete - called when download finishes
 * @param onError    - called if download fails or connection drops
 * @returns cleanup function
 */
export function streamDownload(
  jobId: string,
  onProgress: (pct: number) => void,
  onComplete: () => void,
  onError?: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/data/download/${jobId}/progress`,
    (eventName, data) => {
      if (eventName === "download_progress" || eventName === "progress") {
        const d = data as { pct?: number };
        onProgress(d.pct ?? 0);
      } else if (eventName === "download_complete" || eventName === "complete") {
        onComplete();
      } else if (eventName === "error") {
        const d = data as { message?: string };
        onError?.(d.message ?? "Download failed");
      }
    },
    () => onError?.("SSE connection lost during download"),
  );
}
