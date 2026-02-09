import React, { useState, useEffect } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { DynamicForm } from '../common/DynamicForm';
import { Play, Calendar, FileText } from 'lucide-react';
import { BacktestConfig } from '../../types/pywebview';

export const BacktestRunner: React.FC = () => {
  const {
    strategies,
    selectedStrategy,
    strategyConfig,
    selectStrategy,
    saveStrategyConfig
  } = useConfigStore();

  const { dataFiles, fetchDataFiles, fetchRunHistory } = useDataStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [config, setConfig] = useState<Partial<BacktestConfig> & { start_date?: string; end_date?: string }>({
    initial_balance: 10000,
    leverage: 10,
    start_date: '2024-01-01',
    end_date: '2024-12-31'
  });

  const [params, setParams] = useState<Record<string, any>>({});

  useEffect(() => {
    fetchDataFiles();
  }, [fetchDataFiles]);

  useEffect(() => {
    if (strategyConfig) {
      // Initialize params from merged config
      setParams(strategyConfig.merged);
    }
  }, [strategyConfig]);

  const handleRun = async () => {
    if (!selectedStrategy || !config.data_file) {
      addToast({ type: 'error', message: 'Please select a strategy and data file' });
      return;
    }

    setLoading(true);
    try {
      // 1. Save current params override
      await saveStrategyConfig(params);

      // 2. Run backtest
      const result = await window.pywebview.api.run_backtest({
        strategy_name: selectedStrategy,
        data_file: config.data_file,
        initial_balance: config.initial_balance || 10000,
        leverage: config.leverage || 10,
        symbol: config.symbol,
        timeframe: config.timeframe
      });

      if (result.success) {
        addToast({ type: 'success', message: 'Backtest completed!' });
        fetchRunHistory();
      } else {
        addToast({ type: 'error', message: result.error || 'Backtest failed' });
      }
    } catch (e) {
      addToast({ type: 'error', message: 'Execution error' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDataFileChange = (filename: string) => {
    const file = dataFiles.find(f => f.name === filename);
    if (file) {
      setConfig(prev => ({
        ...prev,
        data_file: filename,
        symbol: file.symbol,
        timeframe: file.timeframe
      }));
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-text">Backtest Configuration</h2>
        <button
          onClick={handleRun}
          disabled={isLoading}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white px-6 py-2 rounded-lg font-medium transition-colors"
        >
          {isLoading ? 'Running...' : (
            <>
              <Play size={18} />
              Run Backtest
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: General Settings */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Setup</h3>

          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Strategy</label>
            <select
              value={selectedStrategy || ''}
              onChange={(e) => selectStrategy(e.target.value)}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            >
              <option value="" disabled>Select Strategy</option>
              {strategies.map(s => (
                <option key={s.name} value={s.name}>{s.display_name}</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Data File</label>
            <div className="relative">
              <FileText size={16} className="absolute left-3 top-3 text-text-muted" />
              <select
                value={config.data_file || ''}
                onChange={(e) => handleDataFileChange(e.target.value)}
                className="w-full bg-surface border border-border rounded-md pl-10 pr-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none appearance-none"
              >
                <option value="" disabled>Select CSV Data</option>
                {dataFiles.map(f => (
                  <option key={f.name} value={f.name}>{f.name} ({f.size_mb} MB)</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col space-y-1">
              <label className="text-sm font-medium text-text">Start Date</label>
              <div className="relative">
                <Calendar size={16} className="absolute left-3 top-3 text-text-muted" />
                <input
                  type="date"
                  value={config.start_date || ''}
                  onChange={(e) => setConfig(p => ({ ...p, start_date: e.target.value }))}
                  className="w-full bg-surface border border-border rounded-md pl-10 pr-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
                />
              </div>
            </div>
            <div className="flex flex-col space-y-1">
              <label className="text-sm font-medium text-text">End Date</label>
              <div className="relative">
                <Calendar size={16} className="absolute left-3 top-3 text-text-muted" />
                <input
                  type="date"
                  value={config.end_date || ''}
                  onChange={(e) => setConfig(p => ({ ...p, end_date: e.target.value }))}
                  className="w-full bg-surface border border-border rounded-md pl-10 pr-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Strategy Params */}
        <div className="lg:col-span-2 border-l border-border pl-8">
          {strategyConfig ? (
            <DynamicForm
              schema={strategyConfig.schema}
              values={params}
              onChange={(k, v) => setParams(p => ({ ...p, [k]: v }))}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-text-muted">
              Select a strategy to configure parameters
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
