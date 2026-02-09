import { useEffect } from 'react';
import { useUIStore } from './stores/useUIStore';

function App() {
  const { activeTab, setActiveTab, initTheme } = useUIStore();

  useEffect(() => {
    initTheme();
  }, [initTheme]);

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] text-[var(--text-primary)] font-sans transition-colors duration-200 flex">
      {/* Sidebar */}
      <aside className="w-64 bg-[var(--bg-secondary)] border-r border-[var(--border)] p-4 flex flex-col h-screen fixed top-0 left-0">
        <h1 className="text-xl font-bold mb-8 text-[var(--accent)]">RSI Bot UI</h1>
        
        <nav className="flex-1 space-y-2">
          {['dashboard', 'backtest', 'settings'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={`w-full text-left px-4 py-2 rounded-md transition-colors ${
                activeTab === tab 
                  ? 'bg-[var(--accent)] text-white' 
                  : 'hover:bg-[var(--bg-surface)] text-[var(--text-secondary)]'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
        
        <div className="mt-auto text-sm text-[var(--text-muted)]">
          Sprint 3 Build
        </div>
      </aside>

      {/* Main Content */}
      <main className="ml-64 p-8 w-full">
        <header className="mb-8 border-b border-[var(--border)] pb-4">
          <h2 className="text-2xl font-bold">
            {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}
          </h2>
        </header>

        <div className="bg-[var(--bg-surface)] rounded-lg p-6 shadow-sm border border-[var(--border)]">
          {activeTab === 'dashboard' && (
            <div className="space-y-4">
              <p>Dashboard placeholder. Stats will go here.</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 bg-[var(--bg-secondary)] rounded-md border border-[var(--border)]">
                  <h3 className="text-sm font-medium text-[var(--text-secondary)]">Win Rate</h3>
                  <p className="text-2xl font-bold text-[var(--success)]">65.4%</p>
                </div>
                <div className="p-4 bg-[var(--bg-secondary)] rounded-md border border-[var(--border)]">
                  <h3 className="text-sm font-medium text-[var(--text-secondary)]">Net Profit</h3>
                  <p className="text-2xl font-bold text-[var(--success)]">+12.5%</p>
                </div>
                <div className="p-4 bg-[var(--bg-secondary)] rounded-md border border-[var(--border)]">
                  <h3 className="text-sm font-medium text-[var(--text-secondary)]">Trades</h3>
                  <p className="text-2xl font-bold">142</p>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'backtest' && (
            <div className="text-center py-12 text-[var(--text-muted)]">
              Backtest Runner Configuration (Coming Sprint 4)
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="text-center py-12 text-[var(--text-muted)]">
              Global Settings & Strategy Configs (Coming Sprint 4)
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
