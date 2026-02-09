import { create } from 'zustand';
import { GlobalConfig, Strategy } from '../types/pywebview';

interface ConfigState {
    globalConfig: GlobalConfig | null;
    strategies: Strategy[];
    isLoading: boolean;
    error: string | null;

    fetchGlobalConfig: () => Promise<void>;
    updateGlobalConfig: (newConfig: GlobalConfig) => Promise<void>;
    fetchStrategies: () => Promise<void>;
}

// Mock data for development outside PyWebView
const MOCK_CONFIG: GlobalConfig = {
    strategy: 'rsi_wma_retest',
    symbols: ['XPL/USDT'],
    timeframe: '5m',
    exchange: 'binance',
    backtest: { initial_balance: 10000, leverage: 10 }
};

const MOCK_STRATEGIES: Strategy[] = [
    { name: 'rsi_wma_retest', display_name: 'RSI WMA Retest', description: 'Mock Strategy', has_override: false }
];

export const useConfigStore = create<ConfigState>((set) => ({
    globalConfig: null,
    strategies: [],
    isLoading: false,
    error: null,

    fetchGlobalConfig: async () => {
        set({ isLoading: true, error: null });
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_global_config();
                if (res.success) {
                    set({ globalConfig: res.data, isLoading: false });
                } else {
                    set({ error: res.error, isLoading: false });
                }
            } else {
                // Dev mode fallback
                console.warn('PyWebView not detected, using mock config');
                set({ globalConfig: MOCK_CONFIG, isLoading: false });
            }
        } catch (err) {
            set({ error: String(err), isLoading: false });
        }
    },

    updateGlobalConfig: async (newConfig) => {
        set({ isLoading: true, error: null });
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.save_global_config(newConfig);
                if (res.success) {
                    set({ globalConfig: newConfig, isLoading: false });
                } else {
                    set({ error: res.error, isLoading: false });
                }
            } else {
                console.warn('PyWebView not detected, mocking save');
                set({ globalConfig: newConfig, isLoading: false });
            }
        } catch (err) {
            set({ error: String(err), isLoading: false });
        }
    },

    fetchStrategies: async () => {
        set({ isLoading: true });
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.get_strategies();
                if (res.success && res.data) {
                    set({ strategies: res.data, isLoading: false });
                } else {
                    set({ error: res.error, isLoading: false });
                }
            } else {
                set({ strategies: MOCK_STRATEGIES, isLoading: false });
            }
        } catch (err) {
            set({ error: String(err), isLoading: false });
        }
    }
}));
