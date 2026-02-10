import React, { useEffect, useState } from 'react';
import { useUIStore } from '../../stores/useUIStore';
import { Check, Moon, Sun, Monitor } from 'lucide-react';
import { cn } from '../../lib/utils';

export const ThemeSelector: React.FC = () => {
  const { theme, setTheme, addToast } = useUIStore();
  const [themes] = useState<string[]>(['dark', 'light', 'midnight']);

  const themesMap: Record<string, { label: string; icon: React.ElementType; color: string }> = {
    dark: { label: 'Dark', icon: Moon, color: 'bg-slate-900' },
    light: { label: 'Light', icon: Sun, color: 'bg-slate-100' },
    midnight: { label: 'Midnight', icon: Monitor, color: 'bg-slate-950' }
  };

  useEffect(() => {
    // Sync theme with document
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);

    // Apply CSS variables based on theme (simplified)
    if (theme === 'light') {
      root.style.setProperty('--color-bg', '#ffffff');
      root.style.setProperty('--color-surface', '#f1f5f9');
      root.style.setProperty('--color-text', '#0f172a');
      root.style.setProperty('--color-text-muted', '#64748b');
      root.style.setProperty('--color-border', '#cbd5e1');
    } else if (theme === 'midnight') {
      root.style.setProperty('--color-bg', '#020617');
      root.style.setProperty('--color-surface', '#0f172a');
      root.style.setProperty('--color-text', '#e2e8f0');
      root.style.setProperty('--color-text-muted', '#64748b');
      root.style.setProperty('--color-border', '#1e293b');
    } else {
      // Dark (default)
      root.style.setProperty('--color-bg', '#0f172a');
      root.style.setProperty('--color-surface', '#1e293b');
      root.style.setProperty('--color-text', '#f8fafc');
      root.style.setProperty('--color-text-muted', '#94a3b8');
      root.style.setProperty('--color-border', '#334155');
    }
  }, [theme]);

  const handleThemeChange = async (newTheme: string) => {
    setTheme(newTheme);
    try {
      await window.pywebview.api.set_active_theme(newTheme);
      addToast({ type: 'success', message: `Theme changed to ${newTheme}` });
    } catch (e) {
      console.error("Failed to persist theme", e);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-6">
      <h3 className="text-lg font-semibold text-text mb-4">Appearance</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {themes.map((t) => {
          const info = themesMap[t] || { label: t, icon: Monitor, color: 'bg-gray-500' };
          const Icon = info.icon;
          const isActive = theme === t;

          return (
            <button
              key={t}
              onClick={() => handleThemeChange(t)}
              className={cn(
                "relative flex items-center gap-3 p-4 rounded-lg border transition-all",
                isActive
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-surface-hover text-text-muted hover:text-text"
              )}
            >
              <div className={cn("w-10 h-10 rounded-full flex items-center justify-center bg-surface border border-border")}>
                <Icon size={20} />
              </div>
              <div className="text-left">
                <p className="font-medium">{info.label}</p>
              </div>
              {isActive && (
                <div className="absolute top-4 right-4 text-primary">
                  <Check size={16} />
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
