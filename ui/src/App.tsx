import { useEffect } from 'react'
import { useUIStore } from './stores/useUIStore'
import { useConfigStore } from './stores/useConfigStore'
import { useDataStore } from './stores/useDataStore'
import { Layout } from './components/layout/Layout'
import { Dashboard } from './components/dashboard/Dashboard'
import { History } from './components/history/History'
import { OptimizationDashboard } from './components/analysis/OptimizationDashboard'
import { Settings } from './components/settings/Settings'

export default function App() {
  const activeTab = useUIStore((state) => state.activeTab)
  const { fetchStrategies, fetchGlobalConfig } = useConfigStore()
  const { fetchDataFiles, fetchRunHistory } = useDataStore()
  const { setTheme } = useUIStore()

  useEffect(() => {
    const init = async () => {
      console.log("Initializing App Data...")
      try {
        // Parallel fetch for faster load
        await Promise.all([
          fetchStrategies(),
          fetchDataFiles(),
          fetchRunHistory(),
          fetchGlobalConfig()
        ]);

        // Initialize theme
        try {
          const theme = await window.pywebview.api.get_active_theme();
          if (theme && theme.name) {
            setTheme(theme.name);
          }
        } catch (e) {
          console.warn("Failed to sync theme from backend", e);
        }
      } catch (e) {
        console.error("Initialization failed", e);
      }
    };

    // Check if pywebview is ready
    if (window.pywebview) {
      init();
    } else {
      // Wait for injection
      window.addEventListener('pywebviewready', init);
    }

    return () => {
      window.removeEventListener('pywebviewready', init);
    }
  }, [fetchStrategies, fetchDataFiles, fetchRunHistory, fetchGlobalConfig, setTheme]);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />
      case 'history':
        return <History />
      case 'optimization':
        return <OptimizationDashboard />
      case 'settings':
        return <Settings />
      default:
        return <div>Not found</div>
    }
  }

  return (
    <Layout>
      {renderContent()}
    </Layout>
  )
}
