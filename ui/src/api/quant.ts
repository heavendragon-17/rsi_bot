import { apiFetch, apiSSE } from "./client";

export interface QuantStartResponse {
  run_id: number;
  status: string;
}

export interface ChartCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  rsi?: number | null;
  ema9?: number | null;
  wma45?: number | null;
  ema21?: number | null;
  ema200?: number | null;
  spread?: number | null;
  above_ema21?: boolean | null;
  active_sl?: number;
  lock_profit_active?: boolean;
  is_entry?: boolean;
  is_exit?: boolean;
}

export async function startGridSearch(params: Record<string, any>): Promise<QuantStartResponse> {
  return apiFetch<QuantStartResponse>("/api/grid-search", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function startWalkForward(params: Record<string, any>): Promise<QuantStartResponse> {
  return apiFetch<QuantStartResponse>("/api/walk-forward", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function startSensitivity(params: Record<string, any>): Promise<QuantStartResponse> {
  return apiFetch<QuantStartResponse>("/api/sensitivity", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function streamQuantProgress(
  runId: number,
  onProgress: (pct: number, bestResult?: any) => void,
  onComplete: (data: any) => void,
  onError: (message: string) => void,
  onFailedNode?: (data: any) => void,
  onSkippedWindow?: (data: any) => void
): () => void {
  return apiSSE(
    `/api/backtest/${runId}/progress`,
    (eventName, data: any) => {
      if (eventName === "progress") {
        onProgress(data?.pct ?? 0, data?.best_result);
      } else if (eventName === "complete") {
        onComplete(data);
      } else if (eventName === "failed_node") {
        if (onFailedNode) onFailedNode(data);
      } else if (eventName === "skipped_window") {
        if (onSkippedWindow) onSkippedWindow(data);
      } else if (eventName === "error") {
        onError(data?.message ?? "Unknown SSE error");
      }
    },
    () => onError("SSE connection lost")
  );
}

export async function getTradeChart(tradeId: string): Promise<ChartCandle[]> {
  return apiFetch<ChartCandle[]>(`/api/trades/${tradeId}/chart`);
}
