import React, { useState } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { Play } from 'lucide-react';
import { WalkForwardResult } from '../../types/pywebview';

export const WalkForwardPanel: React.FC = () => {
  const { strategies, selectedStrategy, selectStrategy } = useConfigStore();
  const { dataFiles } = useDataStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [selectedFile, setSelectedFile] = useState('');
  const [config, setConfig] = useState({
    train_days: 90,
    test_days: 30,
    step_days: 30
  });
  const [result, setResult] = useState<WalkForwardResult | null>(null);

  const handleRun = async () => {
    if (!selectedStrategy || !selectedFile) {
      addToast({ type: 'error', message: 'Please select strategy and data file' });
      return;
    }

    setLoading(true);
    try {
      const file = dataFiles.find(f => f.name === selectedFile);
      const res = await window.pywebview.api.run_walk_forward({
        strategy_name: selectedStrategy,
        symbol: file?.symbol || 'Unknown',
        data_file: selectedFile,
        config: {}, // Use defaults for now
        ...config
      });

      setResult(res);
      addToast({ type: 'success', message: 'Walk-forward analysis completed' });
    } catch (e) {
      addToast({ type: 'error', message: 'Analysis failed' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Train Period (Days)</label>
            <input
              type="number"
              value={config.train_days}
              onChange={(e) => setConfig(prev => ({ ...prev, train_days: parseInt(e.target.value) }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Test Period (Days)</label>
            <input
              type="number"
              value={config.test_days}
              onChange={(e) => setConfig(prev => ({ ...prev, test_days: parseInt(e.target.value) }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Step Size (Days)</label>
            <input
              type="number"
              value={config.step_days}
              onChange={(e) => setConfig(prev => ({ ...prev, step_days: parseInt(e.target.value) }))}
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
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-surface border border-border rounded-xl p-4">
              <p className="text-text-muted text-xs uppercase font-bold">Total OOS Profit</p>
              <p className="text-2xl font-bold text-success">${result.aggregate.total_oos_profit.toFixed(2)}</p>
            </div>
            <div className="bg-surface border border-border rounded-xl p-4">
              <p className="text-text-muted text-xs uppercase font-bold">Avg Efficiency</p>
              <p className="text-2xl font-bold text-primary">{result.aggregate.avg_efficiency.toFixed(2)}</p>
            </div>
            <div className="bg-surface border border-border rounded-xl p-4">
              <p className="text-text-muted text-xs uppercase font-bold">Consistency Score</p>
              <p className="text-2xl font-bold text-text">{result.aggregate.consistency_score.toFixed(2)}</p>
            </div>
          </div>

          <div className="bg-surface border border-border rounded-xl overflow-hidden">
            <div className="p-4 border-b border-border">
              <h3 className="font-semibold text-text">Windows</h3>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-hover text-text-muted font-medium">
                <tr>
                  <th className="px-4 py-3">Train Period</th>
                  <th className="px-4 py-3">Test Period</th>
                  <th className="px-4 py-3">IS Profit</th>
                  <th className="px-4 py-3">OOS Profit</th>
                  <th className="px-4 py-3">Efficiency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.windows.map((w, i) => (
                  <tr key={i} className="hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-text-muted">
                      {new Date(w.train_start).toLocaleDateString()} - {new Date(w.train_end).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-text">
                      {new Date(w.test_start).toLocaleDateString()} - {new Date(w.test_end).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-success">${w.in_sample_profit.toFixed(2)}</td>
                    <td className="px-4 py-3 text-success">${w.out_of_sample_profit.toFixed(2)}</td>
                    <td className="px-4 py-3 text-text">{w.efficiency_ratio.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
