import React, { useState, useEffect } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { DynamicForm } from '../common/DynamicForm';
import { Play, Settings2, Info } from 'lucide-react';
import { BacktestConfig } from '../../types/pywebview';
import { Select } from '../common/Select';
import { cn } from '../../lib/utils';

export const BacktestRunner: React.FC = () => {
  const {
    strategies,
    selectedStrategy,
    strategyConfig,
    selectStrategy,
    saveStrategyConfig
  } = useConfigStore();

  const { dataFiles, fetchRunHistory } = useDataStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [config, setConfig] = useState<Partial<BacktestConfig> & { start_date?: string; end_date?: string }>({
    initial_balance: 10000,
    leverage: 10,
    start_date: '2024-01-01',
    end_date: '2024-12-31'
  });

  const [params, setParams] = useState<Record<string, any>>({});

  useEffect(() => {
    if (strategyConfig) {
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
      await saveStrategyConfig(params);

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

  const strategyOptions = strategies.map(s => ({
    value: s.name,
    label: s.display_name
  }));

  const dataFileOptions = dataFiles.map(f => ({
    value: f.name,
    label: `${f.symbol} ${f.timeframe} (${f.size_mb} MB)`
  }));

  const activeStrategyDesc = strategies.find(s => s.name === selectedStrategy)?.description;

  return (
    <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden flex flex-col h-full">
      {/* Header Section */}
      <div className="p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface-hover/30">
        <div>
          <h2 className="text-xl font-bold text-text flex items-center gap-2">
            <Settings2 className="text-primary" size={24} />
            Backtest Configuration
          </h2>
          <p className="text-text-muted text-sm mt-1">
            Configure strategy parameters and execution settings
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={isLoading || !selectedStrategy}
          className={cn(
            "flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-white shadow-lg shadow-primary/20 transition-all active:scale-95",
            isLoading || !selectedStrategy
              ? "bg-text-muted/20 text-text-muted cursor-not-allowed shadow-none"
              : "bg-primary hover:bg-primary-hover hover:shadow-primary/40"
          )}
        >
          {isLoading ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Play size={18} fill="currentColor" />
          )}
          {isLoading ? 'Running...' : 'Run Backtest'}
        </button>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-border">
        {/* Left Column: General Settings (4 cols) */}
        <div className="lg:col-span-4 p-6 space-y-6 bg-surface-hover/10">
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-primary font-medium text-sm uppercase tracking-wider mb-2">
              <span className="w-1 h-4 bg-primary rounded-full"></span>
              Setup
            </div>

            <Select
              label="Strategy"
              options={strategyOptions}
              value={selectedStrategy || ''}
              onChange={(e) => selectStrategy(e.target.value)}
              placeholder="Select Strategy"
            />

            {activeStrategyDesc && (
              <div className="bg-primary/5 border border-primary/10 rounded-lg p-3 flex gap-3 text-xs text-text-muted">
                <Info className="text-primary shrink-0" size={16} />
                {activeStrategyDesc}
              </div>
            )}

            <Select
              label="Data File"
              options={dataFileOptions}
              value={config.data_file || ''}
              onChange={(e) => handleDataFileChange(e.target.value)}
              placeholder="Select CSV Data"
            />
          </div>

          <div className="pt-4 border-t border-border space-y-4">
            <div className="flex items-center gap-2 text-primary font-medium text-sm uppercase tracking-wider mb-2">
              <span className="w-1 h-4 bg-primary rounded-full"></span>
              Environment
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider">Start Date</label>
                <div className="relative">
                  <input
                    type="date"
                    value={config.start_date || ''}
                    onChange={(e) => setConfig(p => ({ ...p, start_date: e.target.value }))}
                    className="w-full bg-surface border border-border rounded-lg pl-3 pr-3 py-2 text-sm text-text focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider">End Date</label>
                <div className="relative">
                  <input
                    type="date"
                    value={config.end_date || ''}
                    onChange={(e) => setConfig(p => ({ ...p, end_date: e.target.value }))}
                    className="w-full bg-surface border border-border rounded-lg pl-3 pr-3 py-2 text-sm text-text focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider">Balance</label>
                <input
                  type="number"
                  value={config.initial_balance}
                  onChange={(e) => setConfig(p => ({ ...p, initial_balance: parseFloat(e.target.value) }))}
                  className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text focus:ring-2 focus:ring-primary outline-none transition-all"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider">Leverage</label>
                <input
                  type="number"
                  value={config.leverage}
                  onChange={(e) => setConfig(p => ({ ...p, leverage: parseFloat(e.target.value) }))}
                  className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text focus:ring-2 focus:ring-primary outline-none transition-all"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Strategy Params (8 cols) */}
        <div className="lg:col-span-8 p-6 bg-surface">
          <div className="flex items-center justify-between mb-6">
             <div className="flex items-center gap-2 text-primary font-medium text-sm uppercase tracking-wider">
               <span className="w-1 h-4 bg-primary rounded-full"></span>
               Parameters
             </div>
             {strategyConfig && (
               <span className="text-xs text-text-muted bg-surface-hover px-2 py-1 rounded border border-border">
                 {Object.keys(params).length} parameters configured
               </span>
             )}
          </div>

          <div className="h-[400px] overflow-y-auto pr-2 custom-scrollbar">
            {strategyConfig ? (
              <DynamicForm
                schema={strategyConfig.schema}
                values={params}
                onChange={(k, v) => setParams(p => ({ ...p, [k]: v }))}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-text-muted space-y-4 opacity-50">
                <Settings2 size={48} strokeWidth={1} />
                <p>Select a strategy to configure parameters</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
