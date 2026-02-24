/**
 * API layer barrel export.
 * Import from here: `import { startBacktest, fetchHistory } from "../api"`
 */

export { apiFetch, apiSSE, ApiError } from "./client";
export { startBacktest, streamProgress, cancelBacktest, getRunDetail, getTimeseries } from "./backtest";
export { fetchHistory, deleteRun } from "./history";
export type { HistoryFilters } from "./history";
export { fetchStrategies } from "./strategies";
export { checkDataStatus, startDownload, streamDownload } from "./data";
