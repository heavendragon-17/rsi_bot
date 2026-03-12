/* AUTO-GENERATED — do not edit manually.
 * Run `npm run generate-types` to regenerate.
 * Generated: 2026-02-20T05:44:11.120213Z
 */

export interface BacktestRequest {
  symbol?: string;          // Single-symbol mode — provide exactly one of symbol or symbols
  symbols?: string[];       // Portfolio mode — provide exactly one of symbol or symbols
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
}

export interface BacktestStartResponse {
  run_id: number;
  status: string;
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
}

export interface HistoryResponse {
  runs: {
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
  }[];
  total: number;
  page: number;
  pages: number;
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

export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  default_config: Record<string, unknown>;
}
