import React from 'react';
import { useUIStore, TabType } from '../../stores/useUIStore';
import { LayoutDashboard, History, Zap, Settings, LineChart } from 'lucide-react';
import { cn } from '../../lib/utils';

export const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab } = useUIStore();

  const tabs: { id: TabType; label: string; icon: React.ElementType }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'history', label: 'History', icon: History },
    { id: 'optimization', label: 'Optimization', icon: Zap },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col h-screen">
      <div className="p-6 border-b border-border flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <LineChart className="text-white" size={20} />
        </div>
        <h1 className="font-bold text-lg text-text">RSI Bot</h1>
      </div>

      <nav className="flex-1 p-4 space-y-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-text-muted hover:bg-surface-hover hover:text-text"
              )}
            >
              <Icon size={20} className={isActive ? "text-primary" : "text-text-muted"} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-border">
        <div className="text-xs text-text-muted text-center">
          v1.0.0 • Connected
        </div>
      </div>
    </aside>
  );
};
