import { Moon, Sun } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';

interface HeaderProps {
  title?: string;
}

export function Header({ title }: HeaderProps) {
  const { theme, toggleTheme } = useUIStore();
  const isDark = theme?.is_dark ?? true;

  return (
    <header className="h-14 bg-[var(--color-surface)] border-b border-[var(--color-border)] flex items-center justify-between px-6">
      <div>
        {title && (
          <h2 className="text-lg font-semibold text-[var(--color-text)]">
            {title}
          </h2>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors"
          aria-label="Toggle theme"
        >
          {isDark ? (
            <Sun size={20} className="text-[var(--color-text)]" />
          ) : (
            <Moon size={20} className="text-[var(--color-text)]" />
          )}
        </button>
      </div>
    </header>
  );
}
