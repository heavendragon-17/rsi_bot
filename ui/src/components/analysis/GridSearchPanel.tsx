import React, { useState } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useDataStore } from '../../stores/useDataStore';
import { useUIStore } from '../../stores/useUIStore';
import { Play, Plus, Trash2 } from 'lucide-react';
import { GridSearchResult } from '../../types/pywebview';

export const GridSearchPanel: React.FC = () => {
  const { strategies, selectedStrategy, selectStrategy } = useConfigStore();
  const { dataFiles } = useDataStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [selectedFile, setSelectedFile] = useState('');
  const [params, setParams] = useState<{key: string, values: string}[]>([]);
  const [results, setResults] = useState<GridSearchResult[]>([]);

  const addParam = () => {
    setParams([...params, { key: '', values: '' }]);
  };

  const removeParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index));
  };

  const updateParam = (index: number, field: 'key' | 'values', value: string) => {
    const newParams = [...params];
    newParams[index][field] = value;
    setParams(newParams);
  };

  const handleRun = async () => {
    if (!selectedStrategy || !selectedFile || params.length === 0) {
      addToast({ type: 'error', message: 'Please complete configuration' });
      return;
    }

    setLoading(true);
    try {
      const paramGrid: Record<string, any[]> = {};
      params.forEach(p => {
        if (p.key && p.values) {
          // Parse values (comma separated)
          const parsed = p.values.split(',').map(v => {
            const num = parseFloat(v.trim());
            return isNaN(num) ? v.trim() : num;
          });
          paramGrid[p.key] = parsed;
        }
      });

      const file = dataFiles.find(f => f.name === selectedFile);

      const res = await window.pywebview.api.run_grid_search({
        strategy_name: selectedStrategy,
        symbol: file?.symbol || 'Unknown',
        data_file: selectedFile,
        param_grid: paramGrid,
        base_config: {}
      });

      setResults(res);
      addToast({ type: 'success', message: 'Grid search completed' });
    } catch (e) {
      addToast({ type: 'error', message: 'Grid search failed' });
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

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-muted">Parameter Grid</h4>
            <button
              onClick={addParam}
              className="text-xs flex items-center gap-1 text-primary hover:text-primary-hover"
            >
              <Plus size={14} /> Add Parameter
            </button>
          </div>

          {params.map((param, i) => (
            <div key={i} className="flex items-center gap-3">
              <input
                placeholder="Parameter Name (e.g. rsi_period)"
                value={param.key}
                onChange={(e) => updateParam(i, 'key', e.target.value)}
                className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:ring-1 focus:ring-primary outline-none"
              />
              <input
                placeholder="Values (comma separated, e.g. 10, 14, 20)"
                value={param.values}
                onChange={(e) => updateParam(i, 'values', e.target.value)}
                className="flex-[2] bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:ring-1 focus:ring-primary outline-none"
              />
              <button
                onClick={() => removeParam(i)}
                className="text-text-muted hover:text-danger p-2"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={handleRun}
            disabled={isLoading}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white px-6 py-2 rounded-lg font-medium transition-colors"
          >
            <Play size={18} />
            Run Search
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border">
            <h3 className="font-semibold text-text">Results</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-hover text-text-muted font-medium">
                <tr>
                  <th className="px-4 py-3">Run ID</th>
                  <th className="px-4 py-3">Parameters</th>
                  <th className="px-4 py-3">Profit</th>
                  <th className="px-4 py-3">Win Rate</th>
                  <th className="px-4 py-3">Trades</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {results.sort((a, b) => b.profit - a.profit).map((res) => (
                  <tr key={res.run_id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-text-muted">#{res.run_id}</td>
                    <td className="px-4 py-3 text-text">
                      {Object.entries(res.params).map(([k, v]) => `${k}=${v}`).join(', ')}
                    </td>
                    <td className="px-4 py-3 text-success font-medium">${res.profit.toFixed(2)}</td>
                    <td className="px-4 py-3 text-text">{(res.win_rate * 100).toFixed(1)}%</td>
                    <td className="px-4 py-3 text-text">{res.trades}</td>
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
