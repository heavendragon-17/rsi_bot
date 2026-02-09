import { create } from 'zustand'
import { DataFile, RunSummary, RunDetails, TimeseriesData, Trade } from '../types/pywebview'

interface DataState {
  dataFiles: DataFile[];
  runHistory: RunSummary[];
  activeRun: RunDetails | null;
  activeRunTimeseries: TimeseriesData | null;
  activeRunTrades: Trade[];

  fetchDataFiles: () => Promise<void>;
  fetchRunHistory: () => Promise<void>;
  loadRun: (runId: number) => Promise<void>;
}

export const useDataStore = create<DataState>((set) => ({
  dataFiles: [],
  runHistory: [],
  activeRun: null,
  activeRunTimeseries: null,
  activeRunTrades: [],

  fetchDataFiles: async () => {
    try {
      const files = await window.pywebview.api.get_data_files();
      set({ dataFiles: files });
    } catch (e) {
      console.error("Failed to fetch data files", e);
    }
  },

  fetchRunHistory: async () => {
    try {
      const history = await window.pywebview.api.get_run_history();
      set({ runHistory: history });
    } catch (e) {
      console.error("Failed to fetch run history", e);
    }
  },

  loadRun: async (runId: number) => {
    try {
      // Parallel fetch
      const [details, timeseries, trades] = await Promise.all([
        window.pywebview.api.get_run_details(runId),
        window.pywebview.api.get_run_timeseries(runId),
        window.pywebview.api.get_trades(runId)
      ]);

      set({
        activeRun: details,
        activeRunTimeseries: timeseries,
        activeRunTrades: trades
      });
    } catch (e) {
      console.error(`Failed to load run ${runId}`, e);
    }
  }
}))
