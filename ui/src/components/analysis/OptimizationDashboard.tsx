import React, { useState } from 'react';
import { GridSearchPanel } from './GridSearchPanel';
import { WalkForwardPanel } from './WalkForwardPanel';
import { SensitivityAnalysis } from './SensitivityAnalysis';
import { cn } from '../../lib/utils';

export const OptimizationDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'grid' | 'walk' | 'sensitivity'>('grid');

  const tabs = [
    { id: 'grid', label: 'Grid Search' },
    { id: 'walk', label: 'Walk Forward' },
    { id: 'sensitivity', label: 'Sensitivity' }
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-border">
        <div className="flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={cn(
                "pb-3 text-sm font-medium transition-colors relative",
                activeTab === tab.id
                  ? "text-primary"
                  : "text-text-muted hover:text-text"
              )}
            >
              {tab.label}
              {activeTab === tab.id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-t-full" />
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="animate-fade-in">
        {activeTab === 'grid' && <GridSearchPanel />}
        {activeTab === 'walk' && <WalkForwardPanel />}
        {activeTab === 'sensitivity' && <SensitivityAnalysis />}
      </div>
    </div>
  );
};
