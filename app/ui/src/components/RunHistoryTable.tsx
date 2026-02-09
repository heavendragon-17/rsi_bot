import React from 'react';
import { format } from 'date-fns';
import { useDataStore } from '../stores/useDataStore';
import { Eye } from 'lucide-react';

const RunHistoryTable: React.FC = () => {
    const { runs, isLoading, fetchRuns, fetchRunDetails } = useDataStore();

    React.useEffect(() => {
        fetchRuns();
    }, [fetchRuns]);

    if (isLoading && runs.length === 0) {
        return <div className="p-8 text-center text-[var(--text-muted)]">Loading history...</div>;
    }

    if (runs.length === 0) {
        return (
            <div className="p-8 text-center border-t border-[var(--border)]">
                <p className="text-[var(--text-muted)]">No backtest runs found.</p>
            </div>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
                <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-secondary)] text-sm">
                        <th className="p-4 font-medium">Date</th>
                        <th className="p-4 font-medium">Strategy</th>
                        <th className="p-4 font-medium">Symbol</th>
                        <th className="p-4 font-medium text-right">Net Profit</th>
                        <th className="p-4 font-medium text-right">Win Rate</th>
                        <th className="p-4 font-medium text-right">Trades</th>
                        <th className="p-4 font-medium text-center">Actions</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                    {runs.map((run) => (
                        <tr key={run.run_id} className="hover:bg-[var(--bg-secondary)] transition-colors">
                            <td className="p-4 text-sm text-[var(--text-primary)]">
                                {format(new Date(run.created_at), 'MMM d, HH:mm')}
                            </td>
                            <td className="p-4 text-sm font-medium text-[var(--accent)]">
                                {run.strategy_name.replace(/_/g, ' ')}
                            </td>
                            <td className="p-4 text-sm text-[var(--text-secondary)]">
                                {run.symbol} <span className="text-xs text-[var(--text-muted)]">({run.timeframe})</span>
                            </td>
                            <td className={`p-4 text-sm text-right font-bold ${
                                run.net_profit_pct >= 0 ? 'text-[var(--success)]' : 'text-[var(--error)]'
                            }`}>
                                {run.net_profit_pct > 0 ? '+' : ''}{run.net_profit_pct.toFixed(2)}%
                            </td>
                            <td className="p-4 text-sm text-right text-[var(--text-primary)]">
                                {run.win_rate ? (run.win_rate * 100).toFixed(1) + '%' : '-'}
                            </td>
                            <td className="p-4 text-sm text-right text-[var(--text-secondary)]">
                                {run.total_trades}
                            </td>
                            <td className="p-4 text-center">
                                <button 
                                    onClick={() => fetchRunDetails(run.run_id)}
                                    className="p-2 hover:bg-[var(--bg-surface)] rounded-full text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
                                    title="View Details"
                                >
                                    <Eye className="w-4 h-4" />
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

export default RunHistoryTable;
