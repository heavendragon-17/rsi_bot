import { useUIStore } from './stores/useUIStore'
import { Layout } from './components/layout/Layout'
import { EmptyState } from './components/common/EmptyState'
import { Dashboard } from './components/dashboard/Dashboard'
import { History } from './components/history/History'
import { OptimizationDashboard } from './components/analysis/OptimizationDashboard'
import { Settings as SettingsIcon } from 'lucide-react'

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
        return (
          <EmptyState
            icon={SettingsIcon}
            title="Settings"
            description="Configure global application settings (Phase 8)."
          />
        )
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
