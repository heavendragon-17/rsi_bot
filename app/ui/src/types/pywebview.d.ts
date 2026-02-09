// Type definitions for PyWebView Bridge API

export interface DataFile {
    name: string;
    symbol: string;
    timeframe: string;
    path: string;
    size_mb: number;
    rows: number;
    modified: string;
}

export interface Strategy {
    name: string;
    display_name: string;
    description: string;
    has_override: boolean;
}

export interface GlobalConfig {
    strategy: string;
    symbols: string[];
    timeframe: string;
    exchange: string;
    backtest: {
        initial_balance: number;
        leverage: number;
    };
}

export interface SchemaItem {
    key: string;
    type: 'text' | 'number' | 'boolean' | 'select';
    label: string;
    default: any;
    group: string;
    min?: number;
    max?: number;
    step?: number;
    options?: string[];
}

export interface StrategyConfig {
    default: Record<string, any>;
    override: Record<string, any>;
    merged: Record<string, any>;
    schema: SchemaItem[];
}

export interface Theme {
    id: number;
    name: string;
    display_name: string;
    is_dark: boolean;
}

export interface ThemeDetails extends Theme {
    css_variables: Record<string, string>;
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
    results: any; // Simplified for now
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

export interface TimeseriesData {
    equity_curve: any[];
    drawdown_curve: any[];
    monthly_returns: Record<string, number>;
}

declare global {
    interface Window {
        pywebview: {
            api: {
                // ConfigAPI
                get_global_config(): Promise<{ success: boolean; data: GlobalConfig; error?: string }>;
                save_global_config(config: GlobalConfig): Promise<{ success: boolean; error?: string }>;
                get_strategies(): Promise<{ success: boolean; data: Strategy[]; error?: string }>;
                get_strategy_config(name: string): Promise<{ success: boolean; data: any; error?: string }>;
                save_strategy_config(name: string, config: any): Promise<{ success: boolean; path?: string; error?: string }>;

                // ThemeAPI
                get_active_theme(): Promise<{ success: boolean; data: ThemeDetails; error?: string }>;

                // DataAPI
                get_run_history(filters?: any): Promise<{ success: boolean; data: RunSummary[]; error?: string }>;
                get_run_details(run_id: number): Promise<{ success: boolean; data: RunDetails; error?: string }>;
                get_run_timeseries(run_id: number): Promise<{ success: boolean; data: TimeseriesData; error?: string }>;
                get_trades(run_id: number, options?: any): Promise<{ success: boolean; data: Trade[]; error?: string }>;

                // BacktestAPI (for future use)
                get_data_files(): Promise<{ success: boolean; data: DataFile[]; error?: string }>;
                run_backtest(params: any): Promise<{ success: boolean; data: any; error?: string }>;
            };
        };
    }
}

export { };
