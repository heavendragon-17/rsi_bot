/* AUTO-GENERATED — do not edit manually.
 * Source: Pydantic models in app/api/schemas.py
 * Run `python scripts/gen_ts_types.py` to regenerate.
 * Generated: 2026-03-20T18:03:16Z
 */

export type BacktestMode = "single" | "portfolio" | "batch" | "tick_replay";

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

export interface DataStatusResponse {
  symbol: string;
  timeframe: string;
  available: boolean;
  file_path: string | null;
  candle_count: number | null;
  date_range: Record<string, string> | null;
}

export interface TimeseriesResponse {
  run_id: number;
  equity_curve: Record<string, unknown>[];
  drawdown_curve: Record<string, unknown>[];
  monthly_returns: Record<string, unknown>;
}

export interface DownloadStartResponse {
  job_id: string;
  status: string;
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
  fee_tier?: string;
  slippage_model?: string;
  slippage_pct?: string;
  params?: Record<string, unknown>;
  max_workers?: number | null;
  tick_data_path?: string | null;
}

export interface ParamSchemaProp {
  type: "integer" | "number" | "boolean" | "string";
  title: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  description?: string;
  ui_group?: string;
  ui_order?: number;
  ui_step?: number;
  ui_suffix?: string;
  ui_hidden?: boolean;
}

export interface JSONSchema {
  type: "object";
  properties: Record<string, ParamSchemaProp>;
  ui_groups?: Record<string, { title: string; icon?: string; order: number }>;
  required?: string[];
}

export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  default_config: Record<string, unknown>;
  param_schema: JSONSchema;
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

export interface HistoryResponse {
  runs: RunSummary[];
  total: number;
  page: number;
  pages: number;
}

export interface BacktestStartResponse {
  run_id: number;
  status: string;
}
