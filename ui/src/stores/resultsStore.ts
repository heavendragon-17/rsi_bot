import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Trade {
  id: number;
  entryTime: string;
  exitTime: string;
  symbol: string;
  side: "LONG" | "SHORT";
  entryPrice: number;
  exitPrice: number;
  size: number;
  pnl: number;
  pnlPct: number;
  exitReason: "TP1" | "TP2" | "TP3" | "LOCK_PROFIT" | "SL" | "DISASTER_SL" | "MANUAL";
  fees: number;
}

export interface EquityPoint {
  time: string; // YYYY-MM-DD
  value: number;
}

export interface BenchmarkPoint {
  time: string;
  value: number;
}

export interface ResultsState {
  hasResults: boolean;

  // Integrity
  feesEnabled: boolean;

  // Hero Stats
  netProfit: number;
  netProfitPct: number;
  benchmarkProfitPct: number;
  profitFactor: number;
  maxDrawdownPct: number;
  maxDrawdownValue: number;
  sharpeRatio: number;

  // Metrics Grid
  grossWin: number;
  grossLoss: number;
  volatility: number;
  expectancy: number;
  maxConsecWins: number;
  winRate: number;
  winCount: number;
  lossCount: number;
  avgWin: number;
  avgLoss: number;
  bestTrade: number;
  worstTrade: number;

  // Charts
  equityCurve: EquityPoint[];
  benchmarkCurve: BenchmarkPoint[];
  underwaterCurve: EquityPoint[];
  exitReasons: Record<string, number>;

  // Data
  trades: Trade[];
  filteredTrades: Trade[];
  activeFilter: string | null;

  // Actions
  setResults: (data: Partial<ResultsState>) => void;
  setFilter: (reason: string | null) => void;
  clearResults: () => void;
  generateMockResults: (capital: number) => void;
}

export const useResultsStore = create<ResultsState>()(
  persist(
    (set, get) => ({
      hasResults: false,
      feesEnabled: true,

      netProfit: 0,
      netProfitPct: 0,
      benchmarkProfitPct: 0,
      profitFactor: 0,
      maxDrawdownPct: 0,
      maxDrawdownValue: 0,
      sharpeRatio: 0,

      grossWin: 0,
      grossLoss: 0,
      volatility: 0,
      expectancy: 0,
      maxConsecWins: 0,
      winRate: 0,
      winCount: 0,
      lossCount: 0,
      avgWin: 0,
      avgLoss: 0,
      bestTrade: 0,
      worstTrade: 0,

      equityCurve: [],
      benchmarkCurve: [],
      underwaterCurve: [],
      exitReasons: {},

      trades: [],
      filteredTrades: [],
      activeFilter: null,

      setResults: (data) => set((state) => ({ ...state, ...data, hasResults: true })),

      setFilter: (reason) => set((state) => {
        const filtered = reason
          ? state.trades.filter(t => t.exitReason === reason)
          : state.trades;
        return { activeFilter: reason, filteredTrades: filtered };
      }),

      clearResults: () => set({ hasResults: false, activeFilter: null }),

      generateMockResults: (capital) => {
        // Simulate generating results
        const tradeCount = 150;
        const trades: Trade[] = [];
        let balance = capital;
        let equityCurve: EquityPoint[] = [];
        let benchmarkCurve: BenchmarkPoint[] = [];
        let underwaterCurve: EquityPoint[] = [];
        let peak = capital;
        let maxDD = 0;
        let maxDDVal = 0;
        let consecutiveWins = 0;
        let maxConsec = 0;

        let wins = 0;
        let losses = 0;
        let grossWin = 0;
        let grossLoss = 0;
        let best = -Infinity;
        let worst = Infinity;
        let exitCounts: Record<string, number> = {
          "TP1": 0, "TP2": 0, "TP3": 0, "LOCK_PROFIT": 0, "SL": 0, "DISASTER_SL": 0
        };

        const reasons = ["TP1", "TP2", "TP3", "LOCK_PROFIT", "SL", "DISASTER_SL"];
        const start = new Date("2025-01-01").getTime();

        // Benchmark simulation (buy and hold start)
        let benchmarkVal = capital;

        for (let i = 0; i < tradeCount; i++) {
          const isWin = Math.random() > 0.45; // 55% win rate bias
          const pnl = isWin
            ? (Math.random() * 500 + 50)
            : -(Math.random() * 300 + 50);

          balance += pnl;
          if (balance > peak) peak = balance;
          const dd = (peak - balance);
          const ddPct = (dd / peak) * 100;
          if (ddPct > maxDD) {
            maxDD = ddPct;
            maxDDVal = dd;
          }

          if (pnl > 0) {
            wins++;
            grossWin += pnl;
            consecutiveWins++;
            if (consecutiveWins > maxConsec) maxConsec = consecutiveWins;
          } else {
            losses++;
            grossLoss += Math.abs(pnl);
            consecutiveWins = 0;
          }

          if (pnl > best) best = pnl;
          if (pnl < worst) worst = pnl;

          const reason = isWin
            ? reasons[Math.floor(Math.random() * 4)] // Win reasons
            : reasons[Math.floor(Math.random() * 2) + 4]; // Loss reasons

          exitCounts[reason] = (exitCounts[reason] || 0) + 1;

          const date = new Date(start + i * 1000 * 60 * 60 * 24); // 1 day per trade
          const dateStr = date.toISOString().split('T')[0];

          trades.push({
            id: i + 1,
            entryTime: dateStr + " 10:00",
            exitTime: dateStr + " 14:00",
            symbol: "BTC/USDT",
            side: Math.random() > 0.5 ? "LONG" : "SHORT",
            entryPrice: 50000 + Math.random() * 10000,
            exitPrice: 50000 + Math.random() * 10000, // fake
            size: 1000,
            pnl,
            pnlPct: (pnl / capital) * 100, // rough
            exitReason: reason as any,
            fees: 5
          });

          equityCurve.push({ time: dateStr, value: balance });
          underwaterCurve.push({ time: dateStr, value: -ddPct }); // Negative for underwater

          // Benchmark drift
          benchmarkVal *= (1 + (Math.random() * 0.02 - 0.009)); // random daily drift
          benchmarkCurve.push({ time: dateStr, value: benchmarkVal });
        }

        set({
          hasResults: true,
          feesEnabled: true,
          trades,
          filteredTrades: trades,
          activeFilter: null,

          netProfit: balance - capital,
          netProfitPct: ((balance - capital) / capital) * 100,
          benchmarkProfitPct: ((benchmarkVal - capital) / capital) * 100,
          profitFactor: grossLoss === 0 ? grossWin : grossWin / grossLoss,
          maxDrawdownPct: maxDD,
          maxDrawdownValue: maxDDVal,
          sharpeRatio: 1.2, // Fake

          grossWin,
          grossLoss,
          volatility: 12.5,
          expectancy: (balance - capital) / tradeCount,
          maxConsecWins: maxConsec,
          winRate: (wins / tradeCount) * 100,
          winCount: wins,
          lossCount: losses,
          avgWin: wins > 0 ? grossWin / wins : 0,
          avgLoss: losses > 0 ? -grossLoss / losses : 0,
          bestTrade: best,
          worstTrade: worst,

          equityCurve,
          benchmarkCurve,
          underwaterCurve,
          exitReasons: exitCounts
        });
      }
    }),
    {
      name: "results-storage",
      partialize: (state) => ({ hasResults: state.hasResults }), // Only persist presence, data is ephemeral/large
    }
  )
);
