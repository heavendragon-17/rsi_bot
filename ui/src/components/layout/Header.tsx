import React from 'react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useUIStore } from '../../stores/useUIStore';
import { Settings, Sun, Moon, Monitor, LayoutDashboard } from 'lucide-react';
import { cn } from '../../lib/utils';

export const Header: React.FC = () => {
  const { strategies, selectedStrategy, selectStrategy } = useConfigStore();
  const { theme, setTheme, setActiveTab } = useUIStore();

  const handleThemeToggle = async () => {
    const nextTheme = theme === 'dark' ? 'light' : theme === 'light' ? 'midnight' : 'dark';
    setTheme(nextTheme);
    try {
      if (window.pywebview) {
        await window.pywebview.api.set_active_theme(nextTheme);
      }
    } catch (e) {
      console.warn("Failed to save theme", e);
    }
  };

  const ThemeIcon = theme === 'light' ? Sun : theme === 'dark' ? Moon : Monitor;

  return (
    <header className={cn(
      "h-16 bg-surface/90 backdrop-blur-md border-b border-border flex items-center justify-between px-6 shadow-sm sticky top-0 z-20 transition-all duration-300",
      theme === 'midnight' ? 'border-primary/20 shadow-primary/5' : ''
    )}>
      <div className="flex items-center gap-4">
        <div className="md:hidden">
          <LayoutDashboard className="text-primary" size={24} />
        </div>
        <h2 className="text-lg font-bold text-text tracking-tight hidden sm:block bg-gradient-to-r from-primary to-primary-hover bg-clip-text text-transparent">
          Dashboard
        </h2>

        {/* Mobile Strategy Selector */}
        <div className="sm:hidden relative group">
           <select
             className="w-40 appearance-none bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-text focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-shadow"
             value={selectedStrategy || ""}
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
        {/* Desktop Strategy Indicator */}
        <div className="hidden md:flex items-center gap-2 mr-2 bg-surface hover:bg-surface-hover px-4 py-1.5 rounded-full border border-border transition-colors duration-200 cursor-default shadow-sm">
          <div className={cn("w-2 h-2 rounded-full animate-pulse", selectedStrategy ? 'bg-success' : 'bg-warning')} />
          <span className="text-xs font-medium text-text-muted select-none">
            {selectedStrategy ? strategies.find(s => s.name === selectedStrategy)?.display_name : 'No Strategy Selected'}
          </span>
        </div>

        <div className="h-6 w-px bg-border mx-2" />

        <button
          onClick={handleThemeToggle}
          className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50"
          title={`Switch to ${theme === 'dark' ? 'light' : theme === 'light' ? 'midnight' : 'dark'} mode`}
        >
          <ThemeIcon size={20} />
        </button>

        <button
          onClick={() => setActiveTab('settings')}
          className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/50"
          title="Settings"
        >
          <Settings size={20} />
        </button>
      </div>
    </header>
  );
};
