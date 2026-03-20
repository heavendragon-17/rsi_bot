/**
 * Strategies API functions.
 */

import { apiFetch } from "./client";
import type { StrategyInfo } from "../types/generated";

// ---------------------------------------------------------------------------
// fetchStrategies
// ---------------------------------------------------------------------------

/** GET /api/strategies — list all available strategies with default configs */
export async function fetchStrategies(): Promise<StrategyInfo[]> {
  return apiFetch<StrategyInfo[]>("/api/strategies");
}
