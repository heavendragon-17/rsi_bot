import { apiFetch, apiSSE } from "./client";
import type {
  SignalChartResponse,
  SignalReplayAvailabilityResponse,
  SignalReplayListResponse,
  SignalReplayRunDetail,
  SignalReplayRunRequest,
  SignalReplayRunSummary,
  SignalReplaySignalDetail,
  SignalReviewResponse,
  SignalReviewUpdate,
  SignalReplayStartResponse,
} from "../types/generated";
import type { ReviewChartTimeframe } from "../lib/signal-review";

export interface SignalReplayListFilters {
  timeframe?: "5m" | "15m";
  replay_run_id?: number;
  quality?: string;
  human_outcome?: string;
  start?: string;
  end?: string;
  page?: number;
  limit?: number;
}

function queryString(filters: object): string {
  const params = new URLSearchParams();
  Object.entries(filters as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export async function startSignalReplay(
  body: SignalReplayRunRequest,
): Promise<SignalReplayStartResponse> {
  return apiFetch<SignalReplayStartResponse>("/api/signal-replays/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getSignalReplayAvailability(): Promise<SignalReplayAvailabilityResponse> {
  return apiFetch<SignalReplayAvailabilityResponse>(
    "/api/signal-replays/availability",
  );
}

export async function listSignalReplayRuns(): Promise<SignalReplayRunSummary[]> {
  return apiFetch<SignalReplayRunSummary[]>("/api/signal-replays/runs");
}

export async function getSignalReplayRun(
  runId: number,
): Promise<SignalReplayRunDetail> {
  return apiFetch<SignalReplayRunDetail>(`/api/signal-replays/runs/${runId}`);
}

export function streamSignalReplayProgress(
  runId: number,
  onProgress: (pct: number, phase?: string) => void,
  onComplete: (data: unknown) => void,
  onError: (message: string) => void,
): () => void {
  return apiSSE(
    `/api/signal-replays/runs/${runId}/progress`,
    (eventName, data) => {
      const payload = data as { pct?: number; phase?: string; message?: string };
      if (eventName === "progress") onProgress(payload.pct ?? 0, payload.phase);
      else if (eventName === "complete") onComplete(data);
      else if (eventName === "error") onError(payload.message ?? "Replay failed");
    },
    () => onError("SSE connection lost"),
  );
}

export async function listSignalReplaySignals(
  filters: SignalReplayListFilters = {},
): Promise<SignalReplayListResponse> {
  return apiFetch<SignalReplayListResponse>(
    `/api/signal-replays/signals${queryString(filters)}`,
  );
}

export async function getSignalReplaySignal(
  signalId: number,
): Promise<SignalReplaySignalDetail> {
  return apiFetch<SignalReplaySignalDetail>(
    `/api/signal-replays/signals/${signalId}`,
  );
}

export async function getSignalChart(
  signalId: number,
  range: { timeframe?: ReviewChartTimeframe; start?: string; end?: string } = {},
): Promise<SignalChartResponse> {
  return apiFetch<SignalChartResponse>(
    `/api/signal-replays/signals/${signalId}/chart${queryString(range)}`,
  );
}

export async function getSignalForwardMetrics(signalId: number) {
  return apiFetch<SignalReplaySignalDetail["forward_metrics"]>(
    `/api/signal-replays/signals/${signalId}/forward-metrics`,
  );
}

export async function updateSignalReview(
  signalId: number,
  body: SignalReviewUpdate,
): Promise<SignalReviewResponse> {
  return apiFetch<SignalReviewResponse>(
    `/api/signal-replays/signals/${signalId}/review`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}
