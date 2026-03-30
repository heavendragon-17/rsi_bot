import { create } from "zustand";
import { apiFetch } from "../api/client";
import { toast } from "sonner";

interface Preset {
  id: number;
  name: string;
  strategy: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface PresetState {
  presets: Preset[];
  isLoading: boolean;

  fetchPresets: (strategy?: string) => Promise<void>;
  savePreset: (name: string) => Promise<void>;
  loadPreset: (preset: Preset) => void;
  deletePreset: (id: number) => Promise<void>;
}

export const usePresetStore = create<PresetState>()((set, get) => ({
  presets: [],
  isLoading: false,

  fetchPresets: async (strategy) => {
    set({ isLoading: true });
    try {
      const qs = strategy ? `?strategy=${strategy}` : "";
      const presets = await apiFetch<Preset[]>(`/api/presets${qs}`);
      set({ presets, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  savePreset: async (name) => {
    const { useBacktestStore } = await import("./backtestStore");
    const state = useBacktestStore.getState();

    await apiFetch("/api/presets", {
      method: "POST",
      body: JSON.stringify({
        name,
        strategy: state.strategy,
        config: {
          symbol: state.symbol,
          timeframe: state.timeframe,
          leverage: state.leverage,
          capital: state.capital,
          riskPercent: state.riskPercent,
          params: state.params,
          startDate: state.startDate,
          endDate: state.endDate,
        },
      }),
    });

    toast.success(`Preset "${name}" saved`);
    get().fetchPresets(state.strategy);
  },

  loadPreset: async (preset) => {
    const { useBacktestStore } = await import("./backtestStore");
    const store = useBacktestStore.getState();

    const c = preset.config;
    if (c.symbol) store.setSymbol(c.symbol as string);
    if (c.timeframe) store.setTimeframe(c.timeframe as string);
    if (c.leverage) store.setLeverage(String(c.leverage));
    if (c.capital) store.setCapital(String(c.capital));
    if (c.riskPercent) store.setRiskPercent(String(c.riskPercent));
    if (c.startDate) store.setStartDate(c.startDate as string);
    if (c.endDate) store.setEndDate(c.endDate as string);
    if (c.params) {
      Object.entries(c.params as Record<string, unknown>).forEach(([k, v]) => {
        store.setParam(k, v);
      });
    }

    toast.success(`Loaded preset "${preset.name}"`);
  },

  deletePreset: async (id) => {
    await apiFetch(`/api/presets/${id}`, { method: "DELETE" });
    set((s) => ({ presets: s.presets.filter((p) => p.id !== id) }));
    toast.success("Preset deleted");
  },
}));
