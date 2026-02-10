import { useUIStore } from './stores/useUIStore'
import { Layout } from './components/layout/Layout'
import { Dashboard } from './components/dashboard/Dashboard'
import { History } from './components/history/History'
import { OptimizationDashboard } from './components/analysis/OptimizationDashboard'
import { Settings } from './components/settings/Settings'

export default function App() {
  const activeTab = useUIStore((state) => state.activeTab)

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
