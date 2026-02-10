import React, { useState } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { Play } from 'lucide-react';
import { SensitivityResult } from '../../types/pywebview';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

export const SensitivityAnalysis: React.FC = () => {
  const { strategies, selectedStrategy, selectStrategy } = useConfigStore();
  const { dataFiles } = useDataStore();
  const { addToast, setLoading, isLoading, theme } = useUIStore();

  const [selectedFile, setSelectedFile] = useState('');
  const [config, setConfig] = useState({
    param_name: '',
    min: '',
    max: '',
    step: ''
  });
  const [result, setResult] = useState<SensitivityResult | null>(null);

  const handleRun = async () => {
    if (!selectedStrategy || !selectedFile || !config.param_name) {
      addToast({ type: 'error', message: 'Please complete configuration' });
      return;
    }

    setLoading(true);
    try {
      const min = parseFloat(config.min);
      const max = parseFloat(config.max);
      const step = parseFloat(config.step);

      const range = [];
      for (let i = min; i <= max; i += step) {
        range.push(parseFloat(i.toFixed(4)));
      }

      const file = dataFiles.find(f => f.name === selectedFile);
      const res = await window.pywebview.api.run_sensitivity({
        strategy_name: selectedStrategy,
        symbol: file?.symbol || 'Unknown',
        data_file: selectedFile,
        base_config: {},
        param_name: config.param_name,
        param_range: range,
        metric: 'profit'
      });

      setResult(res);
      addToast({ type: 'success', message: 'Sensitivity analysis completed' });
    } catch (e) {
      addToast({ type: 'error', message: 'Analysis failed' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const chartData = result ? result.values.map((val, i) => ({
    value: val,
    metric: result.results[i]
  })) : [];

  const isDark = theme === 'dark' || theme === 'midnight';

  return (
    <div className="space-y-6">
      <div className="bg-surface border border-border rounded-xl p-6">
        <h3 className="text-lg font-semibold text-text mb-4">Configuration</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
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
            <select
              value={selectedFile}
              onChange={(e) => setSelectedFile(e.target.value)}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            >
              <option value="" disabled>Select Data File</option>
              {dataFiles.map(f => (
                <option key={f.name} value={f.name}>{f.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Parameter Name</label>
            <input
              value={config.param_name}
              onChange={(e) => setConfig(prev => ({ ...prev, param_name: e.target.value }))}
              placeholder="e.g. rsi_period"
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Min Value</label>
            <input
              type="number"
              value={config.min}
              onChange={(e) => setConfig(prev => ({ ...prev, min: e.target.value }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Max Value</label>
            <input
              type="number"
              value={config.max}
              onChange={(e) => setConfig(prev => ({ ...prev, max: e.target.value }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Step Size</label>
            <input
              type="number"
              value={config.step}
              onChange={(e) => setConfig(prev => ({ ...prev, step: e.target.value }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={handleRun}
            disabled={isLoading}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white px-6 py-2 rounded-lg font-medium transition-colors"
          >
            <Play size={18} />
            Run Analysis
          </button>
        </div>
      </div>

      {result && (
        <div className="bg-surface border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-text">Sensitivity Curve</h3>
            <div className="text-sm text-text-muted">
              Stability Score: <span className="font-bold text-text">{result.stability_score.toFixed(2)}</span>
            </div>
          </div>

          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#334155' : '#e2e8f0'} />
                <XAxis
                  dataKey="value"
                  stroke={isDark ? '#94a3b8' : '#64748b'}
                  tick={{ fill: isDark ? '#94a3b8' : '#64748b' }}
                />
                <YAxis
                  stroke={isDark ? '#94a3b8' : '#64748b'}
                  tick={{ fill: isDark ? '#94a3b8' : '#64748b' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1e293b' : '#ffffff',
                    borderColor: isDark ? '#334155' : '#cbd5e1',
                    color: isDark ? '#f8fafc' : '#0f172a'
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="metric"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={{ fill: '#3b82f6' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 text-center">
            <p className="text-text">
              Optimal {result.parameter}: <span className="font-bold text-success">{result.optimal.value}</span>
              (Result: {result.optimal.result.toFixed(2)})
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
