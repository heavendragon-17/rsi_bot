import React from 'react';
import { useSingleRunStore } from "../../../stores/singleRunStore";

export function SingleResultsDashboard() {
    const { result } = useSingleRunStore();
    return (
        <div className="p-6">
            <h2 className="text-2xl font-bold mb-4">Single Backtest Results</h2>
            {result ? (
                <div>
                    <p>Status: {result.status}</p>
                    <p>Net Profit: {String(result.results?.net_profit) || 'N/A'}</p>
                    <p>Total Trades: {String(result.results?.total_trades) || 0}</p>
                </div>
            ) : (
                <p>No results yet.</p>
            )}
        </div>
    );
}
