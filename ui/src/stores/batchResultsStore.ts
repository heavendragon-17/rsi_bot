import { create } from "zustand";
import { persist } from "zustand/middleware";
import { Trade } from "./resultsStore";

export interface BatchSymbolResult {
  symbol: string;
  contribution: number;
  netPnL: number;
  netPnLPct: number;
  winRate: number;
  tradeCount: number;
  sharpe: number;
  maxDrawdownPct: number;
  isPinned: boolean;

  // Full data needed for drill-down
  trades: Trade[];
  equityCurve: { time: string; value: number }[];

  // Extended fields for drill-down hydration
  profitFactor: number;
  grossWin: number;
  grossLoss: number;
  maxDrawdownValue: number;
  sortinoRatio: number;
  calmarRatio: number;
  volatility: number;
  expectancy: number;
  maxConsecWins: number;
  winCount: number;
  lossCount: number;
  avgWin: number;
  avgLoss: number;
  bestTrade: number;
  worstTrade: number;
  benchmarkProfitPct: number;
  exitReasons: Record<string, number>;
  underwaterCurve: { time: string; value: number }[];
}

export interface CorrelationCell {
  symbolA: string;
  symbolB: string;
  correlation: number;
}

export interface BatchResultsState {
  hasBatchResults: boolean;
  batchRunId: number;
  symbols: string[];
  allocationMode: "equal_weight" | "risk_parity" | "custom";

  // Portfolio Aggregate
  totalPnL: number;
  totalPnLPct: number;
  benchmarkPnLPct: number;
  portfolioSharpe: number;
  portfolioMaxDrawdownPct: number;
  portfolioMaxDrawdownValue: number;
  avgCorrelation: number;
  bestSymbol: { symbol: string; pnlPct: number };
  worstSymbol: { symbol: string; pnlPct: number };

  // Per-Symbol Data
  symbolResults: BatchSymbolResult[];

  // Correlation Matrix
  correlationMatrix: CorrelationCell[];

  // Charts
  portfolioEquityCurve: { time: string; value: number }[];
  benchmarkEquityCurve: { time: string; value: number }[];
  dispersionRange: { time: string; min: number; max: number }[];

  // UI State
  pinnedSymbols: string[]; // Max 3
  selectedSymbol: string | null; // For drill-down

  // Actions
  setBatchResults: (data: Partial<BatchResultsState>) => void;
  togglePin: (symbol: string) => void;
  selectSymbol: (symbol: string | null) => void;
  clearBatchResults: () => void;
}

export const useBatchResultsStore = create<BatchResultsState>()(
  persist(
    (set, get) => ({
      hasBatchResults: false,
      batchRunId: 0,
      symbols: [],
      allocationMode: "equal_weight",

      totalPnL: 0,
      totalPnLPct: 0,
      benchmarkPnLPct: 0,
      portfolioSharpe: 0,
      portfolioMaxDrawdownPct: 0,
      portfolioMaxDrawdownValue: 0,
      avgCorrelation: 0,
      bestSymbol: { symbol: "", pnlPct: 0 },
      worstSymbol: { symbol: "", pnlPct: 0 },

      symbolResults: [],
      correlationMatrix: [],

      portfolioEquityCurve: [],
      benchmarkEquityCurve: [],
      dispersionRange: [],

      pinnedSymbols: [],
      selectedSymbol: null,

      setBatchResults: (data) => set((state) => ({ ...state, ...data, hasBatchResults: true })),

      togglePin: (symbol) => set((state) => {
        const isPinned = state.pinnedSymbols.includes(symbol);
        if (isPinned) {
            return { pinnedSymbols: state.pinnedSymbols.filter(s => s !== symbol) };
        } else {
            if (state.pinnedSymbols.length >= 3) return state; // Max 3
            return { pinnedSymbols: [...state.pinnedSymbols, symbol] };
        }
      }),

      selectSymbol: (symbol) => set({ selectedSymbol: symbol }),

      clearBatchResults: () => set({ hasBatchResults: false, selectedSymbol: null, pinnedSymbols: [] })
    }),
    {
      name: "batch-results-storage",
      partialize: (state) => ({ hasBatchResults: state.hasBatchResults }),
    }
  )
);
