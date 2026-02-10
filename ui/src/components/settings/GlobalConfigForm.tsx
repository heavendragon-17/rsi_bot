import React, { useEffect, useState } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useUIStore } from '../../stores/useUIStore';
import { Save } from 'lucide-react';
import { GlobalConfig } from '../../types/pywebview';

export const GlobalConfigForm: React.FC = () => {
  const { globalConfig, fetchGlobalConfig, updateGlobalConfig } = useConfigStore();
  const { addToast, setLoading, isLoading } = useUIStore();

  const [formData, setFormData] = useState<Partial<GlobalConfig>>({});

  useEffect(() => {
    fetchGlobalConfig();
  }, [fetchGlobalConfig]);

  useEffect(() => {
    if (globalConfig) {
      setFormData(globalConfig);
    }
  }, [globalConfig]);

  const handleSave = async () => {
    setLoading(true);
    try {
      await updateGlobalConfig(formData as GlobalConfig);
      addToast({ type: 'success', message: 'Settings saved successfully' });
    } catch (e) {
      addToast({ type: 'error', message: 'Failed to save settings' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-text">Global Configuration</h3>
        <button
          onClick={handleSave}
          disabled={isLoading}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          <Save size={18} />
          Save Changes
        </button>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Default Symbol</label>
            <input
              value={formData.symbols?.[0] || ''}
              onChange={(e) => setFormData(p => ({ ...p, symbols: [e.target.value] }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Default Timeframe</label>
            <input
              value={formData.timeframe || ''}
              onChange={(e) => setFormData(p => ({ ...p, timeframe: e.target.value }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>

        <h4 className="text-sm font-medium text-text-muted mt-4 uppercase tracking-wider">Backtest Defaults</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Initial Balance</label>
            <input
              type="number"
              value={formData.backtest?.initial_balance || 10000}
              onChange={(e) => setFormData(p => ({
                ...p,
                backtest: { ...p.backtest!, initial_balance: parseFloat(e.target.value) }
              }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>

          <div className="flex flex-col space-y-1">
            <label className="text-sm font-medium text-text">Leverage</label>
            <input
              type="number"
              value={formData.backtest?.leverage || 1}
              onChange={(e) => setFormData(p => ({
                ...p,
                backtest: { ...p.backtest!, leverage: parseFloat(e.target.value) }
              }))}
              className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
