import React, { useEffect } from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useUIStore } from '../../stores/useUIStore';
import { Play, Settings2 } from 'lucide-react';

export const Header: React.FC = () => {
  const { strategies, selectedStrategy, fetchStrategies, selectStrategy } = useConfigStore();
  const { addToast, setLoading } = useUIStore();

  useEffect(() => {
    fetchStrategies();
  }, [fetchStrategies]);

  const handleRunBacktest = async () => {
    if (!selectedStrategy) {
      addToast({ type: 'error', message: 'Please select a strategy first' });
      return;
    }

    setLoading(true);
    addToast({ type: 'info', message: 'Starting backtest...' });

    // Simulate delay for now or call actual API
    setTimeout(() => {
      setLoading(false);
      addToast({ type: 'success', message: 'Backtest completed successfully' });
    }, 2000);
  };

  return (
    <header className="h-16 bg-surface border-b border-border flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <label className="text-xs text-text-muted mb-1">Strategy</label>
          <select
            className="bg-surface-hover border border-border rounded px-3 py-1 text-sm text-text focus:outline-none focus:ring-1 focus:ring-primary"
            value={selectedStrategy || ''}
            onChange={(e) => selectStrategy(e.target.value)}
          >
            <option value="" disabled>Select Strategy</option>
            {strategies.map(s => (
              <option key={s.name} value={s.name}>{s.display_name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="p-2 text-text-muted hover:text-text hover:bg-surface-hover rounded-lg transition-colors">
          <Settings2 size={20} />
        </button>
        <button
          onClick={handleRunBacktest}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          <Play size={16} />
          Run Backtest
        </button>
      </div>
    </header>
  );
};
