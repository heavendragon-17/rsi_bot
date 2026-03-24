import React from 'react';
import { useBatchRunStore } from "../../../stores/batchRunStore";

export function BatchResultsDashboard() {
    const { result } = useBatchRunStore();
    return (
        <div className="p-6">
            <h2 className="text-2xl font-bold mb-4">Batch Backtest Results</h2>
            {result ? (
                <div>
                    <p>Status: {result.status}</p>
                    <p>Total PnL: {String(result.aggregate?.total_pnl) || 'N/A'}</p>
                    <p>Symbols Run: {result.symbol_count}</p>
                    <ul>
                        {result.symbols.map(s => (
                            <li key={s.symbol}>{s.symbol}: {s.status} (PnL: {String(s.net_profit) || 'N/A'})</li>
                        ))}
                    </ul>
                </div>
            ) : (
                <p>No results yet.</p>
            )}
        </div>
    );
}
