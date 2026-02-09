import React, { useState } from 'react';
import { Trade } from '../../types/pywebview';
import { ArrowUpDown, Download } from 'lucide-react';
import { cn } from '../../lib/utils';

interface TradesTableProps {
  trades: Trade[];
}

export const TradesTable: React.FC<TradesTableProps> = ({ trades }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const totalPages = Math.ceil(trades.length / itemsPerPage);
  const currentTrades = trades.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h3 className="font-semibold text-text">Trade History</h3>
        <button className="p-2 text-text-muted hover:text-text hover:bg-surface-hover rounded-lg transition-colors">
          <Download size={18} />
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-hover text-text-muted font-medium">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3 cursor-pointer hover:text-text flex items-center gap-1">
                Time <ArrowUpDown size={14} />
              </th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">P&L</th>
              <th className="px-4 py-3">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {currentTrades.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text-muted">
                  No trades available.
                </td>
              </tr>
            ) : (
              currentTrades.map((trade, i) => (
                <tr key={trade.id} className="hover:bg-surface-hover transition-colors">
                  <td className="px-4 py-3 text-text-muted">{(currentPage - 1) * itemsPerPage + i + 1}</td>
                  <td className="px-4 py-3 text-text">
                    {new Date(trade.entry_time).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      "px-2 py-1 rounded text-xs font-medium uppercase",
                      trade.side.toLowerCase() === 'long' ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
                    )}>
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text">${parseFloat(trade.entry_price).toFixed(2)}</td>
                  <td className={cn(
                    "px-4 py-3 font-medium",
                    parseFloat(trade.pnl) >= 0 ? "text-success" : "text-danger"
                  )}>
                    {parseFloat(trade.pnl) > 0 ? '+' : ''}{parseFloat(trade.pnl).toFixed(2)} ({trade.pnl_pct.toFixed(2)}%)
                  </td>
                  <td className="px-4 py-3 text-text-muted uppercase text-xs">
                    {trade.exit_reason}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="p-3 border-t border-border flex justify-center gap-2">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            className="px-3 py-1 text-sm bg-surface hover:bg-surface-hover disabled:opacity-50 rounded border border-border text-text"
          >
            Prev
          </button>
          <span className="text-sm text-text-muted self-center">
            Page {currentPage} of {totalPages}
          </span>
          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            className="px-3 py-1 text-sm bg-surface hover:bg-surface-hover disabled:opacity-50 rounded border border-border text-text"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
