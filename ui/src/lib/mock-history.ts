import type { HistoryRun } from "../stores/historyStore";

// Generate sample history runs for testing
export function generateMockHistory(count: number = 20): Omit<HistoryRun, "id" | "runNumber" | "timestamp">[] {
  const strategies = ["rsi_no_retest", "macd_cross", "bollinger_breakout"];
  const symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "ADA/USDT"];
  const timeframes = ["15m", "1h", "4h", "1d"];
  
  const runs: Omit<HistoryRun, "id" | "runNumber" | "timestamp">[] = [];
  
  for (let i = 0; i < count; i++) {
    const isBatch = Math.random() > 0.7; // 30% chance of batch
    const isProf = Math.random() > 0.45; // 55% profitable
    
    const netPnL = isProf 
      ? Math.random() * 5000 + 100 
      : -(Math.random() * 2000 + 50);
    
    const capital = 10000;
    const winRate = isProf ? 55 + Math.random() * 20 : 35 + Math.random() * 15;
    
    runs.push({
      strategyName: strategies[Math.floor(Math.random() * strategies.length)],
      strategyVersion: "v1.0",
      symbol: isBatch ? "PORTFOLIO" : symbols[Math.floor(Math.random() * symbols.length)],
      isBatch,
      parameters: {
        rsi_period: 10 + Math.floor(Math.random() * 20),
        ema_fast: 5 + Math.floor(Math.random() * 10),
        ema_slow: 15 + Math.floor(Math.random() * 25),
        tp1_rr: 1 + Math.random() * 2,
        tp2_rr: 2 + Math.random() * 3,
        sl_buffer_pct: 0.5 + Math.random() * 2,
        capital,
        leverage: 1 + Math.floor(Math.random() * 3),
        riskPercent: 0.5 + Math.random() * 2,
        timeframe: timeframes[Math.floor(Math.random() * timeframes.length)],
        startDate: null,
        endDate: null,
      },
      netPnL,
      netPnLPct: (netPnL / capital) * 100,
      winRate,
      profitFactor: isProf ? 1.2 + Math.random() * 1.5 : 0.5 + Math.random() * 0.4,
      maxDrawdownPct: 5 + Math.random() * 20,
      sharpeRatio: isProf ? 0.5 + Math.random() * 1.5 : -0.5 + Math.random() * 0.8,
      tradeCount: 50 + Math.floor(Math.random() * 200),
    });
  }
  
  return runs;
}
