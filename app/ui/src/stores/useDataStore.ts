import { create } from 'zustand';
import { Trade } from '../types/pywebview';

interface RunHistoryItem {
    run_id: number;
    strategy_name: string;
    symbol: string;
    net_profit_pct: number;
    created_at: string;
}

interface DataState {
    runs: RunHistoryItem[];
    currentRun: any | null; // Detailed run
    trades: Trade[];
    timeseries: any | null;
    isLoading: boolean;
    error: string | null;

    fetchRuns: (filters?: any) => Promise<void>;
    fetchRunDetails: (runId: number) => Promise<void>;
    fetchTimeseries: (runId: number) => Promise<void>;
}

export const useDataStore = create<DataState>((set) => ({
    runs: [],
    currentRun: null,
    trades: [],
    timeseries: null,
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
                // Mock
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
        // Lazy load logic
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
    }
}));
