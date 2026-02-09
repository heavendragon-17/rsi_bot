import { Moon, Sun } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';

export function ThemeSelector() {
  const { theme, toggleTheme } = useUIStore();
  const isDark = theme?.is_dark ?? true;

  return (
    <div className="flex items-center justify-between p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
      <div>
        <h3 className="text-lg font-medium text-[var(--color-text)]">Appearance</h3>
        <p className="text-sm text-[var(--color-text-muted)]">
          Customize the look and feel of the application.
        </p>
      </div>

      <button
        onClick={toggleTheme}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors text-[var(--color-text)]"
      >
        {isDark ? <Moon size={18} /> : <Sun size={18} />}
        <span>{isDark ? 'Dark Mode' : 'Light Mode'}</span>
      </button>
    </div>
  );
}
