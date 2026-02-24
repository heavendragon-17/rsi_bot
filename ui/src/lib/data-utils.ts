import { SymbolDataStatus } from "../stores/dataPrepStore";
import { checkDataStatus as apiCheckDataStatus } from "../api/data";

const CONTEXT_FACTS: Record<string, string[]> = {
  BTC: [
    "BTC averages 12% monthly volatility since 2020.",
    "Bitcoin's average drawdown duration is 89 days.",
    "BTC/ETH correlation is currently 0.87.",
    "Max drawdown for BTC was -83% in 2018.",
  ],
  ETH: [
    "ETH gas fees peaked at $70 in May 2021.",
    "Ethereum merge reduced energy use by 99.95%.",
    "ETH trades 24/7, unlike NYSE's 6.5 hours.",
    "ETH beta relative to BTC is typically 1.2x.",
  ],
  SOL: [
    "Solana uses Proof of History consensus.",
    "SOL handles 65,000 transactions per second theoretically.",
    "Average block time on Solana is ~400ms.",
  ],
  DEFAULT: [
    "The best traders review their losing trades first.",
    "A 60% win rate with 2:1 R:R is highly profitable.",
    "Drawdown is the silent killer of trading accounts.",
    "RSI was invented by J. Welles Wilder in 1978.",
    "Trend following works best in high volatility.",
    "Mean reversion works best in ranging markets.",
  ],
  ERROR: [
    "Check your API quota in Settings.",
    "Binance rate limit resets every minute.",
    "Try reducing the number of symbols in batch.",
    "Check your internet connection.",
  ],
};

export const getRandomFact = (symbol?: string, isError: boolean = false): string => {
  if (isError) {
    const facts = CONTEXT_FACTS["ERROR"];
    return facts[Math.floor(Math.random() * facts.length)];
  }
  
  const base = symbol ? symbol.split("/")[0] : "DEFAULT";
  const facts = CONTEXT_FACTS[base] || CONTEXT_FACTS["DEFAULT"];
  return facts[Math.floor(Math.random() * facts.length)];
};

export const checkDataStatus = async (
    symbols: string[],
    timeframe: string,
    _startDate?: Date | null,
    _endDate?: Date | null,
): Promise<{ allFresh: boolean; symbolStatuses: SymbolDataStatus[] }> => {
    const results = await Promise.all(
        symbols.map(sym => apiCheckDataStatus(sym, timeframe).catch(() => null))
    );

    const symbolStatuses: SymbolDataStatus[] = symbols.map((sym, i) => {
        const r = results[i];
        if (!r || !r.available) {
            return { symbol: sym, status: "missing" as const, sizeBytes: null, downloadedBytes: 0, lastUpdated: 0 };
        }
        return {
            symbol: sym,
            status: "fresh" as const,
            sizeBytes: r.candle_count ? r.candle_count * 80 : null,
            downloadedBytes: r.candle_count ? r.candle_count * 80 : 0,
            lastUpdated: Date.now(),
        };
    });

    const allFresh = symbolStatuses.every(s => s.status === "fresh");
    return { allFresh, symbolStatuses };
};
