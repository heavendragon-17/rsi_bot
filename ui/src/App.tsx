import React, { useEffect } from 'react';
import { Toaster } from 'sonner';
import { Layout } from './components/layout/Layout';
import { EmptyState } from './components/dashboard/EmptyState';
import { DataPrepModal } from './components/data-modal/DataPrepModal';
import { SingleResultsDashboard } from './components/results/single/SingleResultsDashboard';
import { BatchResultsDashboard } from './components/results/batch/BatchResultsDashboard';
import { PortfolioResultsDashboard } from './components/results/portfolio/PortfolioResultsDashboard';
import { RunHistory } from './components/history/RunHistory';
import { GridSearch } from './components/GridSearch';
import { WalkForward } from './components/WalkForward';
import { SensitivityAnalysis } from './components/Sensitivity';
import { useResultsStore } from './stores/resultsStore';
import { useBatchResultsStore } from './stores/batchResultsStore';
import { useBacktestStore } from './stores/backtestStore';
import { useThemeStore } from './stores/themeStore';

// Main App Component
function App() {
  const { hasResults } = useResultsStore();
  const { hasBatchResults } = useBatchResultsStore();
  const { mode } = useBacktestStore();
  const { fetchThemes } = useThemeStore();

  // Initialize themes on mount
  useEffect(() => {
    // Fetch available themes
    fetchThemes();
  }, [fetchThemes]);

  const showSingle = mode === "single";
  const showBatch = mode === "batch";
  const showPortfolio = mode === "portfolio";
  const showHistory = mode === "history";
  const showGridSearch = mode === "grid-search";
  const showWalkForward = mode === "walk-forward";
  const showSensitivity = mode === "sensitivity";

  return (
    <Layout>
      {showSingle && <SingleResultsDashboard />}
      {showBatch && <BatchResultsDashboard />}
      {showPortfolio && <PortfolioResultsDashboard />}
      {showHistory && <RunHistory />}
      {showGridSearch && <GridSearch />}
      {showWalkForward && <WalkForward />}
      {showSensitivity && <SensitivityAnalysis />}

      {!showSingle && !showBatch && !showPortfolio && !showHistory && !showGridSearch && !showWalkForward && !showSensitivity && <EmptyState />}
      
      <DataPrepModal />
      <Toaster richColors position="bottom-right" />
    </Layout>
  );
}

export default App;