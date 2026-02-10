import { SymbolDataStatus } from "../stores/dataPrepStore";

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

// Simulated Data Check
export const checkDataStatus = async (
    symbols: string[], 
    timeframe: string,
    startDate: string,
    endDate: string
): Promise<{ allFresh: boolean, symbolStatuses: SymbolDataStatus[] }> => {
    // Simulate network delay (random between 100ms and 800ms to test grace period)
    // We'll control this via a deterministic random or just randomness for the demo
    const delay = Math.random() * 800 + 100; 
    await new Promise(resolve => setTimeout(resolve, delay));

    const symbolStatuses: SymbolDataStatus[] = symbols.map(sym => {
        // Simulate random status
        const rand = Math.random();
        let status: SymbolDataStatus["status"] = "fresh";
        let size = 1.2 * 1024 * 1024; // 1.2 MB
        
        if (rand > 0.8) status = "missing";
        else if (rand > 0.6) status = "outdated";

        return {
            symbol: sym,
            status,
            sizeBytes: status === "missing" ? null : size,
            downloadedBytes: status === "fresh" ? size : 0,
            lastUpdated: status === "fresh" ? Date.now() : Date.now() - 1000 * 60 * 60 * 24 * 10, // 10 days ago
        };
    });

    const allFresh = symbolStatuses.every(s => s.status === "fresh");
    return { allFresh, symbolStatuses };
};
