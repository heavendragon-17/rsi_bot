import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RunDetail, TimeseriesResponse } from "../types/generated";
import type { Trade } from "./resultsStore";

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

// ---------------------------------------------------------------------------
// mapApiToBatchResults — converts API response to batch store state
// ---------------------------------------------------------------------------

const _str = (v: unknown): number => parseFloat(String(v ?? "0")) || 0;
const _num = (v: unknown): number => (typeof v === "number" ? v : _str(v));

function maxConsecutiveWins(trades: Record<string, unknown>[]): number {
  let max = 0;
  let cur = 0;
  for (const t of trades) {
    if (_str(t["pnl"]) > 0) { cur++; max = Math.max(max, cur); } else { cur = 0; }
  }
  return max;
}

function mapTrade(t: Record<string, unknown>, i: number): Trade {
  return {
    id: _num(t["id"]) || i + 1,
    entryTime: String(t["entry_time"] ?? ""),
    exitTime: String(t["exit_time"] ?? ""),
    symbol: String(t["symbol"] ?? ""),
    side: (String(t["side"] ?? "LONG").toUpperCase() === "SHORT" ? "SHORT" : "LONG") as Trade["side"],
    entryPrice: _str(t["entry_price"]),
    exitPrice: _str(t["exit_price"]),
    size: _str(t["size_usd"]),
    pnl: _str(t["pnl"]),
    pnlPct: _num(t["pnl_pct"]),
    exitReason: (t["exit_reason"] as Trade["exitReason"]) ?? "MANUAL",
    fees: 0,
  };
}

function dedupeByDate<T extends { time: string }>(points: T[]): T[] {
  const seen = new Map<string, T>();
  for (const p of points) seen.set(p.time, p);
  return Array.from(seen.values()).sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}

export function mapApiToBatchResults(
  detail: RunDetail,
  timeseries: TimeseriesResponse,
): Partial<BatchResultsState> {
  const r = detail.results as Record<string, unknown> | null;
  if (!r) return {};

  const initialCapital = _str((detail.config as Record<string, unknown>)["initial_capital"]) || 10000;

  // Group trades by symbol
  const rawTrades = (detail.trades ?? []) as Record<string, unknown>[];
  const bySymbol: Record<string, Record<string, unknown>[]> = {};
  for (const t of rawTrades) {
    const sym = String(t["symbol"] ?? "UNKNOWN");
    if (!bySymbol[sym]) bySymbol[sym] = [];
    bySymbol[sym].push(t);
  }

  const totalPnL = _str(r["net_profit"]);

  // Build per-symbol results from trade groupings
  const symbolResults: BatchSymbolResult[] = Object.entries(bySymbol).map(([sym, symTrades]) => {
    const mapped = symTrades.map(mapTrade);
    const pnls = symTrades.map((t) => _str(t["pnl"]));
    const netPnL = pnls.reduce((a, b) => a + b, 0);
    const wins = symTrades.filter((t) => _str(t["pnl"]) > 0);
    const losses = symTrades.filter((t) => _str(t["pnl"]) <= 0);
    const grossWin = wins.reduce((acc, t) => acc + _str(t["pnl"]), 0);
    const grossLoss = losses.reduce((acc, t) => acc + _str(t["pnl"]), 0);
    const winRate = symTrades.length > 0 ? (wins.length / symTrades.length) * 100 : 0;
    const profitFactor = Math.abs(grossLoss) > 0 ? grossWin / Math.abs(grossLoss) : 0;
    const avgWin = wins.length > 0 ? grossWin / wins.length : 0;
    const avgLoss = losses.length > 0 ? grossLoss / losses.length : 0;
    const bestTrade = pnls.length > 0 ? Math.max(...pnls) : 0;
    const worstTrade = pnls.length > 0 ? Math.min(...pnls) : 0;
    const netPnLPct = initialCapital > 0 ? (netPnL / initialCapital) * 100 : 0;

    const exitReasons: Record<string, number> = {};
    for (const t of symTrades) {
      const reason = String(t["exit_reason"] ?? "UNKNOWN");
      exitReasons[reason] = (exitReasons[reason] ?? 0) + 1;
    }

    return {
      symbol: sym,
      contribution: totalPnL !== 0 ? (netPnL / Math.abs(totalPnL)) * 100 : 0,
      netPnL,
      netPnLPct,
      winRate,
      tradeCount: symTrades.length,
      sharpe: 0,
      maxDrawdownPct: 0,
      isPinned: false,
      trades: mapped,
      equityCurve: [],
      profitFactor,
      grossWin,
      grossLoss,
      maxDrawdownValue: 0,
      sortinoRatio: 0,
      calmarRatio: 0,
      volatility: 0,
      expectancy: symTrades.length > 0 ? netPnL / symTrades.length : 0,
      maxConsecWins: maxConsecutiveWins(symTrades),
      winCount: wins.length,
      lossCount: losses.length,
      avgWin,
      avgLoss,
      bestTrade,
      worstTrade,
      benchmarkProfitPct: 0,
      exitReasons,
      underwaterCurve: [],
    };
  });

  // Sort by PnL% to find best/worst
  const sorted = [...symbolResults].sort((a, b) => b.netPnLPct - a.netPnLPct);
  const bestSymbol = sorted[0]
    ? { symbol: sorted[0].symbol, pnlPct: sorted[0].netPnLPct }
    : { symbol: "", pnlPct: 0 };
  const worstSymbol = sorted[sorted.length - 1]
    ? { symbol: sorted[sorted.length - 1].symbol, pnlPct: sorted[sorted.length - 1].netPnLPct }
    : { symbol: "", pnlPct: 0 };

  // Portfolio equity curve from timeseries (populated for portfolio mode; empty for batch)
  const portfolioEquityCurve = dedupeByDate(
    timeseries.equity_curve.map((p) => ({
      time: String(p["date"] ?? p["time"] ?? "").slice(0, 10),
      value: typeof p["balance"] === "string" ? parseFloat(p["balance"]) : _num(p["balance"]),
    })),
  );

  return {
    batchRunId: detail.id,
    symbols: Object.keys(bySymbol),
    allocationMode: "equal_weight",
    totalPnL,
    totalPnLPct: _num(r["net_profit_pct"]),
    benchmarkPnLPct: 0,
    portfolioSharpe: _num(r["sharpe_ratio"]),
    portfolioMaxDrawdownPct: _num(r["max_drawdown_pct"]),
    portfolioMaxDrawdownValue: _str(r["max_drawdown_value"]),
    avgCorrelation: 0,
    bestSymbol,
    worstSymbol,
    symbolResults,
    correlationMatrix: [],
    portfolioEquityCurve,
    benchmarkEquityCurve: [],
    dispersionRange: [],
    pinnedSymbols: [],
    selectedSymbol: null,
  };
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
