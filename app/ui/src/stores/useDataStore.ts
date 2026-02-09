import { create } from 'zustand';
import { Trade, RunSummary, DataFile } from '../types/pywebview';

interface DataState {
    runs: RunSummary[];
    currentRun: any | null;
    trades: Trade[];
    timeseries: any | null;
    dataFiles: DataFile[];
    isLoading: boolean;
    error: string | null;

    fetchRuns: (filters?: any) => Promise<void>;
    fetchRunDetails: (runId: number) => Promise<void>;
    fetchTimeseries: (runId: number) => Promise<void>;
    fetchDataFiles: () => Promise<void>;
}

export const useDataStore = create<DataState>((set) => ({
    runs: [],
    currentRun: null,
    trades: [],
    timeseries: null,
    dataFiles: [],
    isLoading: false,
    error: null,

    fetchRuns: async (filters) => {
        set({ isLoading: true });
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_run_history(filters);
                if (res.success && res.data) {
                    set({ runs: res.data, isLoading: false });
                } else {
                    set({ error: res.error, isLoading: false });
                }
            } else {
                set({ runs: [], isLoading: false });
            }
        } catch (err) {
            set({ error: String(err), isLoading: false });
        }
    },

    fetchRunDetails: async (runId) => {
        set({ isLoading: true });
        try {
            if (window.pywebview) {
                const [detailsRes, tradesRes] = await Promise.all([
                    window.pywebview.api.get_run_details(runId),
                    window.pywebview.api.get_trades(runId)
                ]);

                if (detailsRes.success && tradesRes.success) {
                    set({
                        currentRun: detailsRes.data,
                        trades: tradesRes.data,
                        isLoading: false
                    });
                } else {
                    set({ error: detailsRes.error || tradesRes.error, isLoading: false });
                }
            } else {
                set({ currentRun: null, trades: [], isLoading: false });
            }
        } catch (err) {
            set({ error: String(err), isLoading: false });
        }
    },

    fetchTimeseries: async (runId) => {
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_run_timeseries(runId);
                if (res.success) {
                    set({ timeseries: res.data });
                }
            }
        } catch (err) {
            console.error(err);
        }
    },

    fetchDataFiles: async () => {
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_data_files();
                if (res.success && res.data) {
                    set({ dataFiles: res.data });
                }
            } else {
                // Mock
                set({
                    dataFiles: [
                        { name: 'XPLUSDT_5m.csv', symbol: 'XPL/USDT', timeframe: '5m', path: '/data/XPLUSDT_5m.csv', size_mb: 1.2, rows: 1000, modified: '2025-01-01' }
                    ]
                });
            }
        } catch (err) {
            console.error(err);
        }
    }
}));
