/* AUTO-GENERATED — do not edit manually.
 * Source: Pydantic models in app/api/schemas.py
 * Run `python scripts/gen_ts_types.py` to regenerate.
 * Generated: 2026-09-02T10:33:09Z
 */

export type BacktestMode = "single" | "portfolio" | "batch" | "tick_replay";

export type SignalQuality = "UNREVIEWED" | "GOOD" | "BAD" | "UNCERTAIN";

export type SignalHumanOutcome = "UNSET" | "WIN" | "LOSS" | "SKIP";

export type SignalTradeExit = "TAKE_PROFIT" | "STOP_LOSS" | "BOTH_SAME_CANDLE" | "OPEN" | "NO_DATA";

export interface SignalReplayRunSummary {
  id: number;
  status: string;
  strategy_name: string;
  definition_version: string;
  git_hash: string | null;
  symbol: string;
  requested_start_at: string | null;
  requested_end_at: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  signal_count: number;
  m5_count: number;
  m15_count: number;
  error_message: string | null;
}

export interface BacktestStartResponse {
  run_id: number;
  status: string;
}

export interface SignalReplayListResponse {
  signals: SignalReplaySignalSummary[];
  total: number;
  page: number;
  pages: number;
}

export interface SignalReplaySignalDetail {
  id: number;
  replay_run_id: number;
  event_id: string;
  sequence: number;
  timeframe: string;
  definition_version: string;
  trigger_open_at: string;
  trigger_close_at: string;
  trigger_close_price: string;
  trigger_price_ema21: string;
  rsi21: number;
  rsi_ema9: number;
  rsi_wma45: number;
  rsi_spread: number;
  previous_rsi_ema9: number | null;
  previous_rsi_wma45: number | null;
  h4_close_price: string;
  h4_price_ema21: string;
  h4_close_at: string;
  decision_reason: string;
  telegram_card: string;
  snapshot: Record<string, unknown>;
  review: SignalReviewResponse;
  forward_metrics: SignalForwardMetricResponse[];
}

export interface SignalForwardMetricResponse {
  horizon_minutes: number;
  price_at_observation: string | null;
  return_pct: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
  observed_at: string | null;
  complete: boolean;
  warning: string | null;
}

export interface PresetUpdate {
  name?: string | null;
  config?: Record<string, unknown> | null;
}

export interface PresetResponse {
  id: number;
  name: string;
  strategy: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DataStatusResponse {
  symbol: string;
  timeframe: string;
  available: boolean;
  file_path: string | null;
  candle_count: number | null;
  date_range: Record<string, string> | null;
}

export interface DownloadStartResponse {
  job_id: string;
  status: string;
}

export interface SignalReviewUpdate {
  quality?: SignalQuality | null;
  human_outcome?: SignalHumanOutcome | null;
  note?: string | null;
  take_profit_price?: string | null;
  stop_loss_price?: string | null;
}

export interface SignalReplaySourceAvailability {
  timeframe: string;
  available: boolean;
  row_count: number;
  available_start: string | null;
  available_end: string | null;
  source_modified_at: string | null;
  error: string | null;
}

export interface SignalReplayAvailabilityResponse {
  ready: boolean;
  common_start_at: string | null;
  common_end_at: string | null;
  sources: SignalReplaySourceAvailability[];
}

export interface PresetCreate {
  name: string;
  strategy: string;
  config: Record<string, unknown>;
}

export interface HistoryResponse {
  runs: RunSummary[];
  total: number;
  page: number;
  pages: number;
}

export interface SignalReviewResponse {
  entry_price: string;
  take_profit_price: string | null;
  stop_loss_price: string | null;
  exit_reason: SignalTradeExit | null;
  exit_at: string | null;
  duration_minutes: number | null;
  evaluation_warning: string | null;
  evaluated_at: string | null;
  quality: SignalQuality;
  human_outcome: SignalHumanOutcome;
  note: string | null;
  reviewed_at: string | null;
  updated_at: string | null;
  future_unlocked_at: string | null;
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

export interface SignalReplaySignalSummary {
  id: number;
  replay_run_id: number;
  event_id: string;
  sequence: number;
  timeframe: string;
  trigger_close_at: string;
  trigger_close_price: string;
  decision_reason: string;
  quality: SignalQuality;
  human_outcome: SignalHumanOutcome;
  note_present: boolean;
}

export interface SignalChartResponse {
  signal_id: number;
  timeframe: string;
  candles: Record<string, unknown>[];
  available_start: string | null;
  available_end: string | null;
  requested_start: string | null;
  requested_end: string | null;
  has_before: boolean;
  has_after: boolean;
  future_allowed: boolean;
  signal_time: string | null;
  anchor_time: string | null;
  warning: string | null;
}

export interface SignalReplayStartResponse {
  run_id: number;
  status: string;
}

export interface SignalReplayRunRequest {
  start?: string | null;
  end?: string | null;
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

export interface TimeseriesResponse {
  run_id: number;
  equity_curve: Record<string, unknown>[];
  drawdown_curve: Record<string, unknown>[];
  monthly_returns: Record<string, unknown>;
  dispersion_range: Record<string, unknown>[];
  benchmark_curve: Record<string, unknown>[];
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

export interface SignalReplayRunDetail {
  run: SignalReplayRunSummary;
  source_metadata: Record<string, unknown>;
  counters: Record<string, unknown>;
}
