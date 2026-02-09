export interface StrategyConfig {
  default: Record<string, any>;
  override: Record<string, any>;
  merged: Record<string, any>;
  schema: ParameterSchema[];
}

export interface ParameterSchema {
  key: string;
  type: "number" | "select" | "boolean";
  label: string;
  group: "indicators" | "risk" | "exits";
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}

export interface GlobalConfig {
  strategy: string;
  symbols: string[];
  timeframe: string;
  backtest: {
    initial_balance: number;
    leverage: number;
  };
  exchange: string;
}

export interface BacktestConfig {
  data_file: string;
  strategy_name: string;
  initial_balance: number;
  leverage: number;
  symbol?: string;
  timeframe?: string;
}

export interface BacktestResult {
  run_id: number;
  success: boolean;
  metrics: {
    net_profit: number;
    net_profit_pct: number;
    win_rate: number;
    profit_factor: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    calmar_ratio: number;
    max_drawdown_pct: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
  };
  equity_preview: [number, number][];
  exit_distribution: {
    TP1: number;
    TP2: number;
    TP3: number;
    SL: number;
    EOD: number;
  };
  error?: string;
}

export interface RunSummary {
  run_id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  net_profit_pct: number;
  win_rate: number;
  sharpe_ratio: number;
  total_trades: number;
  created_at: string;
  tags: string[];
}

export interface RunDetails {
  run: {
    id: number;
    strategy_name: string;
    status: string;
    created_at: string;
    git_hash: string;
    version: string;
  };
  config: Record<string, any>;
  results: BacktestResult["metrics"];
}

export interface TimeseriesData {
  equity_curve: [number, number][];
  drawdown_curve: [number, number][];
  monthly_returns: Record<string, number>;
}

export interface Trade {
  id: number;
  symbol: string;
  side: "LONG" | "SHORT";
  entry_time: string;
  exit_time: string;
  entry_price: string;
  exit_price: string;
  quantity: string;
  pnl: string;
  pnl_pct: number;
  exit_reason: string;
  hold_time_hours: number;
  note?: string;
}

export interface GridSearchConfig {
  strategy_name: string;
  symbol: string;
  data_file: string;
  param_grid: Record<string, any[]>;
  base_config: Record<string, any>;
}

export interface GridSearchResult {
  params: Record<string, any>;
  profit: number;
  win_rate: number;
  trades: number;
  run_id: number;
}

export interface WalkForwardConfig {
  strategy_name: string;
  symbol: string;
  data_file: string;
  config: Record<string, any>;
  train_days: number;
  test_days: number;
  step_days: number;
}

export interface WalkForwardResult {
  windows: {
    train_start: string;
    train_end: string;
    test_start: string;
    test_end: string;
    in_sample_profit: number;
    out_of_sample_profit: number;
    efficiency_ratio: number;
  }[];
  aggregate: {
    total_oos_profit: number;
    avg_efficiency: number;
    consistency_score: number;
  };
}

export interface SensitivityConfig {
  strategy_name: string;
  symbol: string;
  data_file: string;
  base_config: Record<string, any>;
  param_name: string;
  param_range: any[];
  metric: string;
}

export interface SensitivityResult {
  parameter: string;
  values: any[];
  results: number[];
  metric: string;
  optimal: {
    value: any;
    result: number;
  };
  stability_score: number;
}

export interface ComparisonResult {
  run_1: RunDetails["run"] & BacktestResult["metrics"];
  run_2: RunDetails["run"] & BacktestResult["metrics"];
  differences: Record<string, number>;
  verdict?: string;
}

export interface DataFile {
  name: string;
  symbol: string;
  timeframe: string;
  path: string;
  size_mb: number;
  rows?: number;
  modified: string;
}

export interface Strategy {
  name: string;
  display_name: string;
  description: string;
  has_override: boolean;
}

export interface Theme {
  name: string;
  is_active: boolean;
  colors: Record<string, string>;
}

declare global {
  interface Window {
    pywebview: {
      api: {
        // Data
        get_data_files: () => Promise<DataFile[]>;
        get_strategies: () => Promise<Strategy[]>;

        // Config
        get_strategy_config: (strategyName: string) => Promise<StrategyConfig>;
        save_strategy_config: (strategyName: string, config: Record<string, any>) => Promise<{success: boolean, path?: string, error?: string}>;
        get_global_config: () => Promise<GlobalConfig>;
        save_global_config: (config: GlobalConfig) => Promise<{success: boolean, error?: string}>;

        // Backtest
        run_backtest: (config: BacktestConfig) => Promise<BacktestResult>;
        get_run_history: (filters?: any) => Promise<RunSummary[]>;
        get_run_details: (runId: number) => Promise<RunDetails>;
        get_run_timeseries: (runId: number) => Promise<TimeseriesData>;
        get_trades: (runId: number) => Promise<Trade[]>;

        // Analysis
        run_grid_search: (config: GridSearchConfig) => Promise<GridSearchResult[]>;
        run_walk_forward: (config: WalkForwardConfig) => Promise<WalkForwardResult>;
        run_sensitivity: (config: SensitivityConfig) => Promise<SensitivityResult>;
        compare_runs: (runId1: number, runId2: number) => Promise<ComparisonResult>;

        // Export
        export_results: (runId: number, format: 'csv' | 'json') => Promise<{success: boolean, file_path?: string, error?: string}>;

        // Themes
        get_themes: () => Promise<Theme[]>;
        get_active_theme: () => Promise<Theme>;
        set_active_theme: (themeName: string) => Promise<boolean>;
      }
    }
  }
}
