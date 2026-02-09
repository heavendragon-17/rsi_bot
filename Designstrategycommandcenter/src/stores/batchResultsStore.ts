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
  generateMockBatchResults: (capital: number, symbolsList: string[]) => void;
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

      clearBatchResults: () => set({ hasBatchResults: false, selectedSymbol: null, pinnedSymbols: [] }),

      generateMockBatchResults: (capital, symbolsList) => {
          // Mock generation logic
          const days = 100;
          const initialPerSymbol = capital / symbolsList.length;
          
          let portfolioCurve = [];
          let benchmarkCurve = [];
          let dispersion = [];
          let totalEquity = capital;
          let benchmarkEquity = capital;
          
          // Generate individual symbol curves first
          const symbolCurves: Record<string, number[]> = {};
          const symbolPnLs: Record<string, number> = {};
          const symbolTrades: Record<string, Trade[]> = {};

          symbolsList.forEach(sym => {
              let val = initialPerSymbol;
              const curve = [val];
              
              // Random performance bias
              const bias = (Math.random() - 0.4) * 0.02; // -0.4 to +0.6 bias
              const vol = 0.03 + Math.random() * 0.05;

              for (let i = 0; i < days; i++) {
                  const change = val * (bias + (Math.random() - 0.5) * vol);
                  val += change;
                  curve.push(val);
              }
              symbolCurves[sym] = curve;
              symbolPnLs[sym] = val - initialPerSymbol;
          });

          // Aggregate Portfolio
          const dateStart = new Date("2025-01-01").getTime();
          
          for (let i = 0; i <= days; i++) {
              let dayTotal = 0;
              let dayMin = Infinity;
              let dayMax = -Infinity;
              
              symbolsList.forEach(sym => {
                  const val = symbolCurves[sym][i];
                  dayTotal += val;
                  // Normalize to % return for dispersion comparison
                  const ret = (val - initialPerSymbol) / initialPerSymbol;
                  if (ret < dayMin) dayMin = ret;
                  if (ret > dayMax) dayMax = ret;
              });
              
              const dateStr = new Date(dateStart + i * 86400000).toISOString().split('T')[0];
              portfolioCurve.push({ time: dateStr, value: dayTotal });
              
              // Benchmark (just a smoother random walk)
              benchmarkEquity *= (1 + (Math.random() * 0.015 - 0.005));
              benchmarkCurve.push({ time: dateStr, value: benchmarkEquity });
              
              dispersion.push({ 
                  time: dateStr, 
                  min: dayMin * 100, // stored as %
                  max: dayMax * 100 
              });
          }

          // Generate Symbol Results Metadata
          const symbolResults: BatchSymbolResult[] = symbolsList.map(sym => {
              const pnl = symbolPnLs[sym];
              const pnlPct = (pnl / initialPerSymbol) * 100;
              return {
                  symbol: sym,
                  contribution: pnl,
                  netPnL: pnl,
                  netPnLPct: pnlPct,
                  winRate: 40 + Math.random() * 40,
                  tradeCount: 20 + Math.floor(Math.random() * 50),
                  sharpe: (Math.random() * 3) - 0.5,
                  maxDrawdownPct: 5 + Math.random() * 20,
                  isPinned: false,
                  trades: [], // empty for mock summary
                  equityCurve: symbolCurves[sym].map((v, i) => ({
                      time: portfolioCurve[i].time,
                      value: v
                  }))
              };
          });

          // Sort for best/worst
          symbolResults.sort((a, b) => b.netPnLPct - a.netPnLPct);
          const best = { symbol: symbolResults[0].symbol, pnlPct: symbolResults[0].netPnLPct };
          const worst = { symbol: symbolResults[symbolResults.length - 1].symbol, pnlPct: symbolResults[symbolResults.length - 1].netPnLPct };

          // Mock Correlation Matrix
          const matrix: CorrelationCell[] = [];
          for (let i = 0; i < symbolsList.length; i++) {
              for (let j = 0; j < symbolsList.length; j++) {
                  let corr = 1;
                  if (i !== j) {
                      // Random correlation usually high in crypto
                      corr = 0.3 + Math.random() * 0.6; 
                  }
                  matrix.push({
                      symbolA: symbolsList[i],
                      symbolB: symbolsList[j],
                      correlation: corr
                  });
              }
          }
          
          // Calculate avg correlation (upper triangle only)
          let corrSum = 0;
          let corrCount = 0;
          for (let i = 0; i < symbolsList.length; i++) {
              for (let j = i + 1; j < symbolsList.length; j++) {
                   const c = matrix.find(m => m.symbolA === symbolsList[i] && m.symbolB === symbolsList[j])?.correlation || 0;
                   corrSum += c;
                   corrCount++;
              }
          }

          const finalTotalPnL = portfolioCurve[portfolioCurve.length-1].value - capital;

          set({
              hasBatchResults: true,
              batchRunId: Date.now(),
              symbols: symbolsList,
              allocationMode: "equal_weight",
              
              totalPnL: finalTotalPnL,
              totalPnLPct: (finalTotalPnL / capital) * 100,
              benchmarkPnLPct: ((benchmarkEquity - capital) / capital) * 100,
              portfolioSharpe: 0.8 + Math.random() * 1.5,
              portfolioMaxDrawdownPct: 5 + Math.random() * 15,
              portfolioMaxDrawdownValue: capital * 0.1,
              avgCorrelation: corrCount > 0 ? corrSum / corrCount : 1,
              bestSymbol: best,
              worstSymbol: worst,
              
              symbolResults: symbolResults,
              correlationMatrix: matrix,
              
              portfolioEquityCurve: portfolioCurve,
              benchmarkEquityCurve: benchmarkCurve,
              dispersionRange: dispersion,
              
              pinnedSymbols: [],
              selectedSymbol: null
          });
      }
    }),
    {
      name: "batch-results-storage",
      partialize: (state) => ({ hasBatchResults: state.hasBatchResults }), 
    }
  )
);
