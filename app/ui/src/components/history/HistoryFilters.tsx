import { Search, Filter, Calendar } from 'lucide-react';
import { useState } from 'react';

interface HistoryFiltersProps {
  onSearch: (query: string) => void;
  onFilterChange: (filters: { strategy?: string; symbol?: string; dateRange?: string }) => void;
}

export function HistoryFilters({ onSearch, onFilterChange }: HistoryFiltersProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeStrategy, setActiveStrategy] = useState<string>('all');
  const [activeSymbol, setActiveSymbol] = useState<string>('all');

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);
    onSearch(query);
  };

  const handleStrategyChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const strategy = e.target.value;
    setActiveStrategy(strategy);
    onFilterChange({ strategy: strategy === 'all' ? undefined : strategy });
  };

  const handleSymbolChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const symbol = e.target.value;
    setActiveSymbol(symbol);
    onFilterChange({ symbol: symbol === 'all' ? undefined : symbol });
  };

  return (
    <div className="flex flex-col md:flex-row gap-4 p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg mb-6">
      {/* Search Bar */}
      <div className="flex-1 relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          type="text"
          placeholder="Search by ID or Config..."
          value={searchQuery}
          onChange={handleSearch}
          className="w-full pl-10 pr-4 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded hover:border-[var(--color-primary)] focus:border-[var(--color-primary)] outline-none transition-colors text-[var(--color-text)]"
        />
      </div>

      {/* Filters Group */}
      <div className="flex gap-2">
        {/* Strategy Filter */}
        <div className="relative">
          <Filter size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <select
            value={activeStrategy}
            onChange={handleStrategyChange}
            className="pl-9 pr-8 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded appearance-none hover:border-[var(--color-primary)] focus:border-[var(--color-primary)] outline-none cursor-pointer text-[var(--color-text)] min-w-[140px]"
          >
            <option value="all">All Strategies</option>
            <option value="rsi_wma_retest">RSI WMA Retest</option>
            <option value="rsi_no_retest">RSI No Retest</option>
            <option value="grid_search">Grid Search</option>
          </select>
        </div>

        {/* Symbol Filter */}
        <div className="relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] font-bold text-xs">S</div>
          <select
            value={activeSymbol}
            onChange={handleSymbolChange}
            className="pl-8 pr-8 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded appearance-none hover:border-[var(--color-primary)] focus:border-[var(--color-primary)] outline-none cursor-pointer text-[var(--color-text)] min-w-[120px]"
          >
            <option value="all">All Symbols</option>
            <option value="BTC/USDT">BTC/USDT</option>
            <option value="ETH/USDT">ETH/USDT</option>
            <option value="SOL/USDT">SOL/USDT</option>
            <option value="XRP/USDT">XRP/USDT</option>
          </select>
        </div>

        {/* Date Filter (Placeholder for now) */}
        <button className="flex items-center gap-2 px-3 py-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded hover:bg-[var(--color-surface-hover)] transition-colors text-[var(--color-text)]">
          <Calendar size={18} className="text-[var(--color-text-muted)]" />
          <span className="hidden sm:inline">Date</span>
        </button>
      </div>
    </div>
  );
}
