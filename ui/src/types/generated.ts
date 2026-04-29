/* AUTO-GENERATED — do not edit manually.
 * Source: Pydantic models in app/api/schemas.py
 * Run `python scripts/gen_ts_types.py` to regenerate.
 * Generated: 2026-04-29T15:16:59Z
 */

export type BacktestMode = "single" | "portfolio" | "batch" | "tick_replay";

export interface BacktestStartResponse {
  run_id: number;
  status: string;
}

export interface PresetResponse {
  id: number;
  name: string;
  strategy: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface HistoryResponse {
  runs: RunSummary[];
  total: number;
  page: number;
  pages: number;
}

export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  default_config: Record<string, unknown>;
  param_schema?: Record<string, unknown>;
}

export interface BacktestRequest {
  mode?: BacktestMode | null;
  symbol?: string | null;
  symbols?: string[] | null;
  timeframe: string;
  strategy: string;
  start_date: string;
  end_date: string;
  initial_capital?: string;
  leverage?: number;
  risk_per_trade_pct?: string;
  taker_fee_pct?: string;
  maker_fee_pct?: string;
  slippage_model?: string;
  slippage_pct?: string;
  params?: Record<string, unknown>;
  benchmark?: string | null;
  max_workers?: number | null;
  tick_data_path?: string | null;
  tp1_close_pct?: number;
  tp2_close_pct?: number;
  max_position_size_pct?: number;
  min_sl_distance_pct?: number;
  use_risk_based_sizing?: boolean;
  use_initial_capital_for_risk?: boolean;
}

export interface DownloadStartResponse {
  job_id: string;
  status: string;
}

export interface TimeseriesResponse {
  run_id: number;
  equity_curve: Record<string, unknown>[];
  drawdown_curve: Record<string, unknown>[];
  monthly_returns: Record<string, unknown>;
  dispersion_range: Record<string, unknown>[];
  benchmark_curve: Record<string, unknown>[];
}

export interface DataStatusResponse {
  symbol: string;
  timeframe: string;
  available: boolean;
  file_path: string | null;
  candle_count: number | null;
  date_range: Record<string, string> | null;
}

export interface RunSummary {
  id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  status: string;
  created_at: string;
  start_date: string;
  end_date: string;
  initial_capital: string;
  leverage: number;
  net_profit: string | null;
  net_profit_pct: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  total_trades: number | null;
  tags: string[];
}

export interface PresetCreate {
  name: string;
  strategy: string;
  config: Record<string, unknown>;
}

export interface PresetUpdate {
  name?: string | null;
  config?: Record<string, unknown> | null;
}

export interface RunDetail {
  id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  status: string;
  created_at: string;
  config: Record<string, unknown>;
  results: Record<string, unknown> | null;
  trades: Record<string, unknown>[] | null;
}
