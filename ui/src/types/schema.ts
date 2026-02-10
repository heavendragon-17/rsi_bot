/**
 * SQLite Database Schema Types
 * Based on the Context Bundle provided for the Strategy Command Center
 */

export interface Run {
  id: number;
  created_at: string;
  config_id: number;
  status: 'running' | 'completed' | 'failed';
  tags?: string[];
}

export interface RunConfig {
  id: number;
  strategy_name: string;
  parameters: Record<string, any>; // JSON stored as text
  start_date: string;
  end_date: string;
  initial_capital: number;
  timeframe: string;
}

export interface RunResult {
  run_id: number;
  net_profit: number;
  net_profit_pct: number;
  win_rate: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  profit_factor: number;
  total_trades: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
}

export interface RunTimeseries {
  run_id: number;
  equity_curve: any; // BLOB - zlib compressed JSON
  drawdown_curve: any; // BLOB - zlib compressed JSON
}

export interface Trade {
  id: number;
  run_id: number;
  entry_time: string;
  exit_time: string;
  symbol: string;
  side: 'long' | 'short';
  entry_price: number;
  exit_price: number;
  pnl: number;
  exit_reason: string;
}

export interface Theme {
  id: number;
  name: string;
  display_name: string;
  is_dark: boolean;
  css_variables: Record<string, string>; // JSON
}
