import React, { useEffect } from 'react';
import { Toaster } from 'sonner';
import { Layout } from './components/layout/Layout';
import { EmptyState } from './components/dashboard/EmptyState';
import { DataPrepModal } from './components/data-modal/DataPrepModal';
import { ResultsDashboard } from './components/results/ResultsDashboard';
import { BatchResultsDashboard } from './components/results/batch/BatchResultsDashboard';
import { RunHistory } from './components/history/RunHistory';
import { GridSearch } from './components/GridSearch';
import { WalkForward } from './components/WalkForward';
import { SensitivityAnalysis } from './components/Sensitivity';
import { FloatingProgressPill } from './components/layout/FloatingProgressPill';
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
  const loadStrategies = useBacktestStore(s => s.loadStrategies);
  const recoverActiveRun = useBacktestStore(s => s.recoverActiveRun);

  // Initialize on mount
  useEffect(() => {
    fetchThemes();
    loadStrategies();
    recoverActiveRun();
  }, [fetchThemes, loadStrategies, recoverActiveRun]);

  const showSingle = mode === "single" && hasResults;
  const showBatch = mode === "batch" && hasBatchResults;
  const showHistory = mode === "history";
  const showGridSearch = mode === "grid-search";
  const showWalkForward = mode === "walk-forward";
  const showSensitivity = mode === "sensitivity";

  return (
    <Layout>
      {showSingle && <ResultsDashboard />}
      {showBatch && <BatchResultsDashboard />}
      {showHistory && <RunHistory />}
      {showGridSearch && <GridSearch />}
      {showWalkForward && <WalkForward />}
      {showSensitivity && <SensitivityAnalysis />}

      {!showSingle && !showBatch && !showHistory && !showGridSearch && !showWalkForward && !showSensitivity && <EmptyState />}

      <DataPrepModal />
      <FloatingProgressPill />
      <Toaster richColors position="bottom-right" />
    </Layout>
  );
}

export default App;
