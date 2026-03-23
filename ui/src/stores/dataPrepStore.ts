import { create } from "zustand";

export interface SymbolDataStatus {
  symbol: string;
  status: "fresh" | "outdated" | "missing" | "downloading" | "error";
  sizeBytes: number | null;
  downloadedBytes: number;
  lastUpdated: number | null; // Timestamp
  errorMsg?: string;
}

interface DataPrepState {
  isOpen: boolean;
  state: "checking" | "ready" | "downloading" | "error" | "complete";

  symbols: SymbolDataStatus[];

  currentDownload: string | null;
  overallProgress: number; // 0-100
  estimatedTimeRemaining: number; // seconds

  currentFact: string;

  // Actions
  openModal: () => void;
  closeModal: () => void;
  setPrepState: (state: DataPrepState["state"]) => void;
  setSymbols: (symbols: SymbolDataStatus[]) => void;
  updateSymbolStatus: (symbol: string, updates: Partial<SymbolDataStatus>) => void;
  setProgress: (progress: number, eta?: number) => void;
  setFact: (fact: string) => void;
  reset: () => void;
}

export const useDataPrepStore = create<DataPrepState>((set) => ({
  isOpen: false,
  state: "checking",
  symbols: [],
  currentDownload: null,
  overallProgress: 0,
  estimatedTimeRemaining: 0,
  currentFact: "",

  openModal: () => set({ isOpen: true }),
  closeModal: () => set({ isOpen: false }),
  setPrepState: (state) => set({ state }),
  setSymbols: (symbols) => set({ symbols }),
  updateSymbolStatus: (symbol, updates) =>
    set((state) => ({
      symbols: state.symbols.map((s) =>
        s.symbol === symbol ? { ...s, ...updates } : s
      )
    })),
  setProgress: (progress, eta) => set((state) => ({
    overallProgress: progress,
    estimatedTimeRemaining: eta !== undefined ? eta : state.estimatedTimeRemaining
  })),
  setFact: (fact) => set({ currentFact: fact }),
  reset: () => set({
    state: "checking",
    symbols: [],
    currentDownload: null,
    overallProgress: 0,
    estimatedTimeRemaining: 0
  })
}));
