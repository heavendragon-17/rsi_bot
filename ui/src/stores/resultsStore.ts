import { create } from "zustand";
import type { RunDetail, TimeseriesResponse } from "../types/generated";

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
  time: string; // ISO string or YYYY-MM-DD
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
  grossWin: number;
  grossLoss: number;
  maxDrawdownPct: number;
  maxDrawdownValue: number;
  sharpeRatio: number;

  // Metrics Grid
  sortinoRatio: number;
  calmarRatio: number;
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
}

// ---------------------------------------------------------------------------
// mapApiToResults — converts API RunDetail + TimeseriesResponse to store state
// ---------------------------------------------------------------------------

export function mapApiToResults(
  detail: RunDetail,
  timeseries: TimeseriesResponse,
): Partial<ResultsState> {
  const r = detail.results as Record<string, unknown> | null;
  if (!r) return { hasResults: false };

  const _str = (v: unknown): number => parseFloat(String(v ?? "0")) || 0;
  const _num = (v: unknown): number => (typeof v === "number" ? v : _str(v));

  return {
    hasResults: true,
    feesEnabled: true,

    netProfit: _str(r["net_profit"]),
    netProfitPct: _num(r["net_profit_pct"]),
    benchmarkProfitPct: 0, // not provided by backend yet
    profitFactor: _num(r["profit_factor"]),
    grossWin: _str(r["gross_profit"]),
    grossLoss: _str(r["gross_loss"]),
    maxDrawdownPct: _num(r["max_drawdown_pct"]),
    maxDrawdownValue: _str(r["max_drawdown_value"]),
    sharpeRatio: _num(r["sharpe_ratio"]),

    sortinoRatio: _num(r["sortino_ratio"]),
    calmarRatio: _num(r["calmar_ratio"]),
    volatility: _num(r["volatility"]),
    expectancy: _str(r["expectancy"]),
    maxConsecWins: _num(r["max_consecutive_wins"]),
    winRate: _num(r["win_rate"]),
    winCount: _num(r["winning_trades"]),
    lossCount: _num(r["losing_trades"]),
    avgWin: _str(r["avg_win"]),
    avgLoss: _str(r["avg_loss"]),
    bestTrade: _str(r["largest_win"]),
    worstTrade: _str(r["largest_loss"]),
    exitReasons: (r["exit_reasons"] as Record<string, number>) ?? {},

    equityCurve: timeseries.equity_curve.map((p) => ({
      time: String(p["date"] ?? p["time"] ?? ""),
      value: typeof p["balance"] === "string" ? parseFloat(p["balance"]) : _num(p["balance"]),
    })),

    underwaterCurve: timeseries.drawdown_curve.map((p) => ({
      time: String(p["date"] ?? p["time"] ?? ""),
      value: -(typeof p["drawdown"] === "number" ? p["drawdown"] : _str(p["drawdown"])),
    })),

    benchmarkCurve: [],

    trades: ((detail.trades ?? []) as Record<string, unknown>[]).map((t, i) => ({
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
    })),

    filteredTrades: [],
    activeFilter: null,
  };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useResultsStore = create<ResultsState>()((set, get) => ({
  hasResults: false,
  feesEnabled: true,

  netProfit: 0,
  netProfitPct: 0,
  benchmarkProfitPct: 0,
  profitFactor: 0,
  grossWin: 0,
  grossLoss: 0,
  maxDrawdownPct: 0,
  maxDrawdownValue: 0,
  sharpeRatio: 0,

  sortinoRatio: 0,
  calmarRatio: 0,
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

  setResults: (data) =>
    set((state) => ({ ...state, ...data, hasResults: true })),

  setFilter: (reason) =>
    set((state) => {
      const filtered = reason
        ? state.trades.filter((t) => t.exitReason === reason)
        : state.trades;
      return { activeFilter: reason, filteredTrades: filtered };
    }),

  clearResults: () => set({ hasResults: false, activeFilter: null }),
}));
