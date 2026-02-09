import { useEffect } from 'react';
import { useUIStore } from './stores/useUIStore';
import DashboardStats from './components/DashboardStats';
import RunHistoryTable from './components/RunHistoryTable';
import StrategyConfigEditor from './components/StrategyConfigEditor';
import BacktestRunner from './components/BacktestRunner';

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

        <div className="space-y-6">
          {activeTab === 'dashboard' && (
            <>
              <DashboardStats />
              <div className="bg-[var(--bg-surface)] rounded-lg border border-[var(--border)] shadow-sm overflow-hidden">
                 <div className="p-4 border-b border-[var(--border)]">
                    <h3 className="font-bold text-lg">Recent Backtest Runs</h3>
                 </div>
                 <RunHistoryTable />
              </div>
            </>
          )}

          {activeTab === 'backtest' && (
            <BacktestRunner />
          )}

          {activeTab === 'settings' && (
            <StrategyConfigEditor />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
