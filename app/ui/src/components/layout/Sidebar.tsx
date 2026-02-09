import { Home, History, Settings, Activity } from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isRunning?: boolean;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <Home size={20} /> },
  { id: 'backtest', label: 'Backtest', icon: <Activity size={20} /> },
  { id: 'history', label: 'History', icon: <History size={20} /> },
  { id: 'settings', label: 'Settings', icon: <Settings size={20} /> },
];

export function Sidebar({ activeTab, onTabChange, isRunning }: SidebarProps) {
  return (
    <aside className="w-64 bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b border-[var(--color-border)]">
        <h1 className="text-xl font-bold text-[var(--color-primary)]">
          RSI Bot
        </h1>
        <p className="text-xs text-[var(--color-text-muted)]">Backtest UI</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={`
              w-full flex items-center gap-3 px-4 py-3 rounded-lg mb-1
              transition-colors duration-150
              ${activeTab === item.id
                ? 'bg-[var(--color-primary)] text-white'
                : 'text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]'
              }
            `}
          >
            {item.icon}
            <span className="font-medium">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Status */}
      <div className="p-4 border-t border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <div className={`
            w-2 h-2 rounded-full
            ${isRunning ? 'bg-yellow-500 animate-pulse' : 'bg-green-500'}
          `} />
          <span className="text-sm text-[var(--color-text-muted)]">
            {isRunning ? 'Running...' : 'Idle'}
          </span>
        </div>
      </div>
    </aside>
  );
}
