import React from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { Search, Filter, X } from 'lucide-react';

interface HistoryFiltersProps {
  onFilterChange: (filters: any) => void;
  isOpen: boolean;
  onClose: () => void;
}

export const HistoryFilters: React.FC<HistoryFiltersProps> = ({ onFilterChange, isOpen, onClose }) => {
  const { strategies } = useConfigStore();

  if (!isOpen) return null;

  return (
    <div className="bg-surface border border-border rounded-xl p-4 mb-6 animate-slide-up">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-text flex items-center gap-2">
          <Filter size={16} /> Filters
        </h3>
        <button onClick={onClose} className="text-text-muted hover:text-text p-1">
          <X size={16} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="flex flex-col space-y-1">
          <label className="text-xs font-medium text-text-muted">Strategy</label>
          <select
            onChange={(e) => onFilterChange({ strategy: e.target.value })}
            className="bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:ring-1 focus:ring-primary outline-none"
          >
            <option value="">All Strategies</option>
            {strategies.map(s => (
              <option key={s.name} value={s.name}>{s.display_name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col space-y-1">
          <label className="text-xs font-medium text-text-muted">Symbol</label>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-text-muted" />
            <input
              placeholder="BTC, ETH..."
              onChange={(e) => onFilterChange({ symbol: e.target.value })}
              className="w-full bg-surface border border-border rounded-md pl-9 pr-3 py-2 text-sm text-text focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>

        <div className="flex flex-col space-y-1">
          <label className="text-xs font-medium text-text-muted">Min Profit %</label>
          <input
            type="number"
            placeholder="0"
            onChange={(e) => onFilterChange({ minProfit: e.target.value })}
            className="bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:ring-1 focus:ring-primary outline-none"
          />
        </div>

        <div className="flex items-end">
          <button className="w-full bg-primary hover:bg-primary-hover text-white py-2 rounded-md text-sm font-medium transition-colors">
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};
