import React, { useEffect } from 'react';
import { Layout } from './components/layout/Layout';
import { EmptyState } from './components/dashboard/EmptyState';
import { DataPrepModal } from './components/data-modal/DataPrepModal';
import { ResultsDashboard } from './components/results/ResultsDashboard';
import { BatchResultsDashboard } from './components/results/batch/BatchResultsDashboard';
import { PineTranslator } from './components/pine/PineTranslator';
import { RunHistory } from './components/history/RunHistory';
import { GridSearch } from './components/GridSearch';
import { WalkForward } from './components/WalkForward';
import { SensitivityAnalysis } from './components/Sensitivity';
import { useResultsStore } from './stores/resultsStore';
import { useBatchResultsStore } from './stores/batchResultsStore';
import { useBacktestStore } from './stores/backtestStore';
import { useThemeStore } from './stores/themeStore';
import { DevTools } from './components/dev/DevTools';
import { SettingsPage } from './components/settings/SettingsPage';

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

  const showSingle = mode === "single" && hasResults;
  const showBatch = mode === "batch" && hasBatchResults;
  const showPine = mode === "pine";
  const showHistory = mode === "history";
  const showGridSearch = mode === "grid-search";
  const showWalkForward = mode === "walk-forward";
  const showSensitivity = mode === "sensitivity";
  const showSettings = mode === "settings";

  return (
    <Layout>
      {showSingle && <ResultsDashboard />}
      {showBatch && <BatchResultsDashboard />}
      {showPine && <PineTranslator />}
      {showHistory && <RunHistory />}
      {showGridSearch && <GridSearch />}
      {showWalkForward && <WalkForward />}
      {showSensitivity && <SensitivityAnalysis />}
      {showSettings && <SettingsPage />}
      
      {!showSingle && !showBatch && !showPine && !showHistory && !showGridSearch && !showWalkForward && !showSensitivity && !showSettings && <EmptyState />}
      
      <DataPrepModal />
      <DevTools />
    </Layout>
  );
}

export default App;