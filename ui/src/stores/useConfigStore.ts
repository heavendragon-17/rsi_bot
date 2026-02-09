import { create } from 'zustand'
import { Strategy, StrategyConfig, GlobalConfig } from '../types/pywebview'

interface ConfigState {
  strategies: Strategy[];
  selectedStrategy: string | null;
  strategyConfig: StrategyConfig | null;
  globalConfig: GlobalConfig | null;

  fetchStrategies: () => Promise<void>;
  selectStrategy: (name: string) => Promise<void>;
  fetchGlobalConfig: () => Promise<void>;
  updateGlobalConfig: (config: GlobalConfig) => Promise<void>;
  saveStrategyConfig: (config: Record<string, any>) => Promise<boolean>;
}

export const useConfigStore = create<ConfigState>((set, get) => ({
  strategies: [],
  selectedStrategy: null,
  strategyConfig: null,
  globalConfig: null,

  fetchStrategies: async () => {
    try {
      const strategies = await window.pywebview.api.get_strategies();
      set({ strategies });
    } catch (e) {
      console.error("Failed to fetch strategies", e);
    }
  },

  selectStrategy: async (name: string) => {
    try {
      const config = await window.pywebview.api.get_strategy_config(name);
      set({ selectedStrategy: name, strategyConfig: config });
    } catch (e) {
      console.error("Failed to load strategy config", e);
    }
  },

  fetchGlobalConfig: async () => {
    try {
      const config = await window.pywebview.api.get_global_config();
      set({ globalConfig: config });
    } catch (e) {
      console.error("Failed to fetch global config", e);
    }
  },

  updateGlobalConfig: async (config: GlobalConfig) => {
    try {
      const result = await window.pywebview.api.save_global_config(config);
      if (result.success) {
        set({ globalConfig: config });
      }
    } catch (e) {
      console.error("Failed to save global config", e);
    }
  },

  saveStrategyConfig: async (config: Record<string, any>) => {
    const { selectedStrategy } = get();
    if (!selectedStrategy) return false;

    try {
      const result = await window.pywebview.api.save_strategy_config(selectedStrategy, config);
      if (result.success) {
        // Refresh config
        const newConfig = await window.pywebview.api.get_strategy_config(selectedStrategy);
        set({ strategyConfig: newConfig });
        return true;
      }
      return false;
    } catch (e) {
      console.error("Failed to save strategy config", e);
      return false;
    }
  }
}))
