/**
 * History API functions.
 */

import { apiFetch } from "./client";
import type { HistoryResponse } from "../types/generated";

export interface HistoryFilters {
  page?: number;
  limit?: number;
  strategy?: string;
  symbol?: string;
  status?: string;
  profitable_only?: boolean;
  date_range?: string;
  search?: string;
}

// ---------------------------------------------------------------------------
// fetchHistory
// ---------------------------------------------------------------------------

/** GET /api/history — paginated, server-side filtered list of runs */
export async function fetchHistory(
  filters: HistoryFilters = {},
): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  for (const [key, val] of Object.entries(filters)) {
    if (val !== undefined && val !== null && val !== "") {
      params.set(key, String(val));
    }
  }
  const qs = params.toString();
  return apiFetch<HistoryResponse>(`/api/history${qs ? `?${qs}` : ""}`);
}

// ---------------------------------------------------------------------------
// deleteRun
// ---------------------------------------------------------------------------

/** DELETE /api/history/{run_id} — cascade delete run + all related rows */
export async function deleteRun(runId: number): Promise<void> {
  await apiFetch<void>(`/api/history/${runId}`, { method: "DELETE" });
}
