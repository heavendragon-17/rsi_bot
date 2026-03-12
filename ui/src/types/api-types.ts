/* AUTO-GENERATED — do not edit manually.
 * Run `npm run generate-types` to regenerate.
 * Generated: 2026-03-12T13:25:24.732977Z
 */

export interface BacktestRequest {
  mode: string;
  symbols: string[];
  timeframe: string;
  strategy: string;
  start_date: string;
  end_date: string;
  initial_capital?: string;
  capital_mode?: string;
  leverage?: number;
  risk_per_trade_pct?: string;
  fee_tier?: string;
  slippage_model?: string;
  slippage_pct?: string;
  params?: Record<string, unknown>;
}

export interface BacktestStartResponse {
  run_id?: number | null;
  batch_run_id?: number | null;
  portfolio_run_id?: number | null;
  mode: string;
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

export interface BatchSymbolResult {
  symbol: string;
  status: string;
  error?: string | null;
  net_profit?: string | null;
  net_profit_pct?: number | null;
  win_rate?: number | null;
  profit_factor?: number | null;
  max_drawdown_pct?: number | null;
  sharpe_ratio?: number | null;
  total_trades?: number | null;
  trades?: Record<string, unknown>[] | null;
}

export interface BatchRunDetail {
  id: number;
  mode?: string;
  strategy_name: string;
  timeframe: string;
  status: string;
  created_at: string;
  config: Record<string, unknown>;
  capital_mode: string;
  symbol_count: number;
  failed_symbols: string[];
  aggregate: Record<string, unknown>;
  symbols: {
    symbol: string;
    status: string;
    error?: string | null;
    net_profit?: string | null;
    net_profit_pct?: number | null;
    win_rate?: number | null;
    profit_factor?: number | null;
    max_drawdown_pct?: number | null;
    sharpe_ratio?: number | null;
    total_trades?: number | null;
    trades?: Record<string, unknown>[] | null;
  }[];
}

export interface PortfolioRunDetail {
  id: number;
  mode?: string;
  strategy_name: string;
  timeframe: string;
  status: string;
  created_at: string;
  config: Record<string, unknown>;
  symbols: string[];
  results: Record<string, unknown>;
  trades: Record<string, unknown>[];
}

export interface BatchTimeseriesResponse {
  batch_run_id: number;
  portfolio_equity_curve: Record<string, unknown>[];
  per_symbol_equity: Record<string, Record<string, unknown>[]>;
  monthly_returns: Record<string, unknown>;
}

export interface PortfolioTimeseriesResponse {
  portfolio_run_id: number;
  equity_curve: Record<string, unknown>[];
  drawdown_curve: Record<string, unknown>[];
  monthly_returns: Record<string, unknown>;
}
