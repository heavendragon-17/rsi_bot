import type { RunDetail, TimeseriesResponse } from "../types/generated";
import type { BatchSymbolResult, CorrelationCell } from "../stores/batchResultsStore";
import type { Trade } from "../stores/resultsStore";

import type { BatchResultsState } from "../stores/batchResultsStore";

function buildUnderwaterCurve(
  equityCurve: { time: string; value: number }[]
): { time: string; value: number }[] {
  let peak = -Infinity;
  return equityCurve.map((p) => {
    if (p.value > peak) peak = p.value;
    const dd = peak > 0 ? ((p.value - peak) / peak) * 100 : 0;
    return { time: p.time, value: dd };
  });
}

export function aggregateBatchResults(
  runs: { symbol: string; detail: RunDetail; timeseries: TimeseriesResponse; initialCapital: number }[]
): Partial<BatchResultsState> {
  let totalPnL = 0;
  let totalInitialCap = 0;
  let maxDrawdownPct = 0;
  let totalTrades = 0;
  let totalWins = 0;

  const symbolResults: BatchSymbolResult[] = [];
  const mapByTime = new Map<string, number>();

  for (const { symbol, detail, timeseries, initialCapital } of runs) {
    const res = (detail.results || {}) as any;
    const pnl = parseFloat(res.net_profit || "0");
    const pnlPct = res.net_profit_pct || 0;
    const tradesCount = res.total_trades || 0;
    const winRate = res.win_rate || 0;
    const sharpe = res.sharpe_ratio || 0;
    const mdPct = res.max_drawdown_pct || 0;

    totalInitialCap += initialCapital;
    totalPnL += pnl;
    totalTrades += tradesCount;
    totalWins += Math.round(tradesCount * (winRate / 100));

    const rawTrades = (detail.trades || []) as any[];
    const trades: Trade[] = rawTrades.map((t, i) => ({
      id: typeof t.id === 'number' ? t.id : i,
      entryTime: String(t.entry_time || ""),
      exitTime: String(t.exit_time || ""),
      symbol: String(t.symbol || ""),
      side: (t.side === "LONG" || t.side === "SHORT") ? t.side : "LONG",
      size: parseFloat(t.amount || "0"),
      entryPrice: parseFloat(t.entry_price || "0"),
      exitPrice: parseFloat(t.exit_price || "0"),
      fees: parseFloat(t.fee || "0"),
      pnl: parseFloat(t.pnl || "0"),
      pnlPct: typeof t.pnl_pct === 'number' ? t.pnl_pct : parseFloat(t.pnl_pct || "0"),
      exitReason: String(t.exit_reason || "Unknown") as any,
    }));

    // Convert equity curve
    const rawCurve = (timeseries.equity_curve || []) as any[];
    const eqCurve = rawCurve.map(p => {
      const originalTime = String(p.date || p.time || "");
      const formattedTime = originalTime.split("T")[0]; // Extract YYYY-MM-DD
      return {
        time: formattedTime,
        value: typeof p.equity === 'number' ? p.equity : parseFloat(p.equity || "0")
      };
    });

    // Sum curve for portfolio
    for (const pt of eqCurve) {
      // align by local date string approx
      const ts = pt.time.split("T")[0]; // group by day
      const existing = mapByTime.get(ts) || 0;
      mapByTime.set(ts, existing + (pt.value - initialCapital));
    }

    const winC = Math.round(tradesCount * (winRate / 100));

    symbolResults.push({
      symbol,
      contribution: pnl,
      netPnL: pnl,
      netPnLPct: pnlPct,
      winRate,
      tradeCount: tradesCount,
      sharpe,
      maxDrawdownPct: mdPct,
      isPinned: false,
      trades,
      equityCurve: eqCurve,
      // Extended fields for drill-down
      profitFactor: parseFloat(res.profit_factor || "0") || 0,
      grossWin: parseFloat(res.gross_profit || "0") || 0,
      grossLoss: parseFloat(res.gross_loss || "0") || 0,
      maxDrawdownValue: parseFloat(res.max_drawdown_value || "0") || 0,
      sortinoRatio: res.sortino_ratio || 0,
      calmarRatio: res.calmar_ratio || 0,
      volatility: res.volatility || 0,
      expectancy: parseFloat(res.expectancy || "0") || 0,
      maxConsecWins: res.max_consecutive_wins || 0,
      winCount: winC,
      lossCount: tradesCount - winC,
      avgWin: parseFloat(res.avg_win || "0") || 0,
      avgLoss: parseFloat(res.avg_loss || "0") || 0,
      bestTrade: parseFloat(res.largest_win || "0") || 0,
      worstTrade: parseFloat(res.largest_loss || "0") || 0,
      benchmarkProfitPct: 0,
      exitReasons: (res.exit_reasons as Record<string, number>) ?? {},
      underwaterCurve: buildUnderwaterCurve(eqCurve),
    });
  }

  // Finalize portfolio curve
  const dates = Array.from(mapByTime.keys()).sort();
  const portfolioEquityCurve = dates.map(d => ({
    time: d,
    value: totalInitialCap + mapByTime.get(d)!,
  }));

  const totalPnLPct = totalInitialCap > 0 ? (totalPnL / totalInitialCap) * 100 : 0;

  // Compute portfolio DD approx (naive for now)
  let peak = totalInitialCap;
  for (const pt of portfolioEquityCurve) {
    if (pt.value > peak) peak = pt.value;
    const dd = ((peak - pt.value) / peak) * 100;
    if (dd > maxDrawdownPct) maxDrawdownPct = dd;
  }

  const sorted = [...symbolResults].sort((a,b) => b.netPnLPct - a.netPnLPct);
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];

  return {
    totalPnL,
    totalPnLPct,
    portfolioSharpe: symbolResults.length ? symbolResults.reduce((acc, curr) => acc + curr.sharpe, 0) / symbolResults.length : 0, // Pseudo average sharpe
    portfolioMaxDrawdownPct: maxDrawdownPct,
    portfolioMaxDrawdownValue: maxDrawdownPct * totalInitialCap / 100,
    symbolResults,
    portfolioEquityCurve,
    benchmarkEquityCurve: portfolioEquityCurve.map(p => ({ time: p.time, value: p.value * 0.95 })), // mock
    dispersionRange: portfolioEquityCurve.map(p => ({ time: p.time, min: p.value * 0.9, max: p.value * 1.1 })), // mock
    correlationMatrix: [], // Empty for now
    avgCorrelation: 0.5,
    bestSymbol: best ? { symbol: best.symbol, pnlPct: best.netPnLPct } : { symbol: "", pnlPct: 0 },
    worstSymbol: worst ? { symbol: worst.symbol, pnlPct: worst.netPnLPct } : { symbol: "", pnlPct: 0 }
  };
}
