import React from 'react';
import { usePortfolioRunStore } from "../../../stores/portfolioRunStore";

export function PortfolioResultsDashboard() {
    const { result } = usePortfolioRunStore();
    return (
        <div className="p-6">
            <h2 className="text-2xl font-bold mb-4">Portfolio Backtest Results</h2>
            {result ? (
                <div>
                    <p>Status: {result.status}</p>
                    <p>Net Profit: {String(result.results?.net_profit) || 'N/A'}</p>
                    <p>Total Trades: {String(result.results?.total_trades) || 0}</p>
                    <p>Symbols in Portfolio: {result.symbols.join(', ')}</p>
                </div>
            ) : (
                <p>No results yet.</p>
            )}
        </div>
    );
}
