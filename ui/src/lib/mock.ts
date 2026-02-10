/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable @typescript-eslint/ban-ts-comment */
import { BacktestResult, Strategy, StrategyConfig, GlobalConfig, DataFile } from '../types/pywebview';

export const initializeMock = () => {
  // Check if pywebview is already defined
  if (window.pywebview) return;

  console.log('Initializing PyWebView Mock for Development');

  const mockStrategies: Strategy[] = [
    { name: 'RSI_WMA_Strategy', display_name: 'RSI WMA Strategy', description: 'Classic RSI with WMA confirmation', has_override: true },
    { name: 'MACD_Strategy', display_name: 'MACD Trend', description: 'MACD Trend Following', has_override: false },
    { name: 'Bollinger_Breakout', display_name: 'Bollinger Breakout', description: 'Volatility Breakout Strategy', has_override: false },
  ];

  const mockDataFiles: DataFile[] = [
    { name: 'BTCUSDT_1h.csv', symbol: 'BTCUSDT', timeframe: '1h', path: '/data/BTCUSDT_1h.csv', size_mb: 15.2, modified: '2024-01-01' },
    { name: 'ETHUSDT_15m.csv', symbol: 'ETHUSDT', timeframe: '15m', path: '/data/ETHUSDT_15m.csv', size_mb: 45.8, modified: '2024-01-02' },
  ];

  const mockStrategyConfig: StrategyConfig = {
    default: { rsi_period: 14, wma_period: 9, overbought: 70, oversold: 30 },
    override: {},
    merged: { rsi_period: 14, wma_period: 9, overbought: 70, oversold: 30 },
    schema: [
      { key: 'rsi_period', type: 'number', label: 'RSI Period', group: 'indicators', min: 2, max: 50, step: 1 },
      { key: 'wma_period', type: 'number', label: 'WMA Period', group: 'indicators', min: 2, max: 50, step: 1 },
      { key: 'overbought', type: 'number', label: 'Overbought Level', group: 'exits', min: 50, max: 100, step: 1 },
      { key: 'oversold', type: 'number', label: 'Oversold Level', group: 'exits', min: 0, max: 50, step: 1 },
    ]
  };

  const mockGlobalConfig: GlobalConfig = {
    strategy: 'RSI_WMA_Strategy',
    symbols: ['BTCUSDT', 'ETHUSDT'],
    timeframe: '1h',
    backtest: { initial_balance: 10000, leverage: 10 },
    exchange: 'mock'
  };

  // @ts-ignore
  window.pywebview = {
    api: {
      get_strategies: async () => {
        await new Promise(r => setTimeout(r, 500));
        return mockStrategies;
      },
      get_data_files: async () => {
        await new Promise(r => setTimeout(r, 500));
        return mockDataFiles;
      },
      get_strategy_config: async (name: string) => {
        await new Promise(r => setTimeout(r, 300));
        return { ...mockStrategyConfig, override: { strategy_name: name } };
      },
      save_strategy_config: async (name: string, config: any) => {
        console.log(`Saved config for ${name}:`, config);
        return { success: true };
      },
      get_global_config: async () => {
        return mockGlobalConfig;
      },
      save_global_config: async (config: GlobalConfig) => {
        console.log('Saved global config:', config);
        return { success: true };
      },
      run_backtest: async (config: any) => {
        console.log('Running backtest with:', config);
        await new Promise(r => setTimeout(r, 2000));
        const result: BacktestResult = {
          run_id: Math.floor(Math.random() * 1000),
          success: true,
          metrics: {
            net_profit: 1250.50,
            net_profit_pct: 12.5,
            win_rate: 0.65,
            profit_factor: 1.8,
            sharpe_ratio: 1.5,
            sortino_ratio: 2.1,
            calmar_ratio: 1.2,
            max_drawdown_pct: 5.4,
            total_trades: 142,
            winning_trades: 92,
            losing_trades: 50
          },
          equity_preview: Array.from({ length: 50 }, (_, i) => [i, 10000 + i * 20 + Math.random() * 100]),
          exit_distribution: { TP1: 40, TP2: 30, TP3: 10, SL: 20, EOD: 0 }
        };
        return result;
      },
      get_run_history: async () => {
        return [];
      },
      get_run_details: async (_id: number) => {
        return { run: { id: _id, strategy_name: 'Mock', status: 'completed', created_at: '2024-01-01', git_hash: 'abc', version: '1.0' }, config: {}, results: {} as any };
      },
      get_run_timeseries: async (_id: number) => {
        return { equity_curve: [], drawdown_curve: [], monthly_returns: {} };
      },
      get_trades: async (_id: number) => {
        return [];
      },
      run_grid_search: async (_config: any) => [],
      run_walk_forward: async (_config: any) => ({ windows: [], aggregate: { total_oos_profit: 0, avg_efficiency: 0, consistency_score: 0 } }),
      run_sensitivity: async (_config: any) => ({ parameter: '', values: [], results: [], metric: '', optimal: { value: 0, result: 0 }, stability_score: 0 }),
      compare_runs: async (_id1: number, _id2: number) => ({ run_1: {} as any, run_2: {} as any, differences: {} }),
      export_results: async (_id: number, format: 'csv' | 'json') => ({ success: true, file_path: `/tmp/export.${format}` }),
      get_themes: async () => [],
      get_active_theme: async () => ({ name: 'dark', is_active: true, colors: {} }),
      set_active_theme: async (name: string) => {
        console.log('Set theme:', name);
        return true;
      }
    }
  };
};
