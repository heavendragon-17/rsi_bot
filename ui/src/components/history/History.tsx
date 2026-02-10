import React, { useState } from 'react';
import { RunHistoryTable } from './RunHistoryTable';
import { HistoryFilters } from './HistoryFilters';
import { ComparisonView } from './ComparisonView';
import { useDataStore } from '../../stores/useDataStore';
import { Filter } from 'lucide-react';

export const History: React.FC = () => {
  const [showFilters, setShowFilters] = useState(false);
  const { activeRun } = useDataStore();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-text">Run History</h2>

        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-2 px-4 py-2 bg-surface border border-border rounded-lg text-text hover:bg-surface-hover transition-colors"
        >
          <Filter size={16} />
          Filters
        </button>
      </div>

      <HistoryFilters
        isOpen={showFilters}
        onClose={() => setShowFilters(false)}
        onFilterChange={(f) => console.log(f)}
      />

      <RunHistoryTable />

      {activeRun && (
        <ComparisonView runId1={activeRun.run.id} />
      )}
    </div>
  );
};
