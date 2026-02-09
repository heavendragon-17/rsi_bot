import { useState } from 'react';
import { Download, ChevronLeft, ChevronRight } from 'lucide-react';
import { useToast } from '../common/index';

interface Trade {
  id: number;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  direction: 'LONG' | 'SHORT';
  exit_reason: string;
}

interface TradesTableProps {
  trades: Trade[];
  runId?: number;
  pageSize?: number;
}

export function TradesTable({ trades, runId, pageSize = 10 }: TradesTableProps) {
  const { addToast } = useToast();
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<keyof Trade>('entry_time');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (!runId) return;
    setExporting(true);
    try {
        if (window.pywebview) {
            const res = await window.pywebview.api.export_run(runId, 'csv');
            if (res.success) {
                // Trigger download
                const blob = new Blob([res.data], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `run_${runId}_trades.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                addToast('success', 'Trades exported successfully');
            } else {
                addToast('error', `Export failed: ${res.error}`);
            }
        }
    } catch (e) {
        addToast('error', 'Export error');
    } finally {
        setExporting(false);
    }
  };

  // Sorting
  const sortedTrades = [...trades].sort((a, b) => {
    if (a[sortField] < b[sortField]) return sortDirection === 'asc' ? -1 : 1;
    if (a[sortField] > b[sortField]) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  // Pagination
  const totalPages = Math.ceil(trades.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const paginatedTrades = sortedTrades.slice(startIndex, startIndex + pageSize);

  const handleSort = (field: keyof Trade) => {
    if (field === sortField) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  if (trades.length === 0) {
    return <div className="text-center p-4 text-[var(--color-text-muted)]">No trades recorded.</div>;
  }

  return (
    <div className="w-full">
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-sm text-left">
          <thead className="bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
            <tr>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('entry_time')}>
                Entry Date {sortField === 'entry_time' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('direction')}>Type</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('entry_price')}>Entry</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('exit_price')}>Exit</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('pnl_pct')}>PnL %</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('pnl')}>PnL $</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => handleSort('exit_reason')}>Reason</th>
            </tr>
          </thead>
          <tbody>
            {paginatedTrades.map((trade) => (
              <tr key={trade.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                <td className="px-4 py-3">{new Date(trade.entry_time).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${trade.direction === 'LONG' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                    {trade.direction}
                  </span>
                </td>
                <td className="px-4 py-3">{trade.entry_price.toFixed(5)}</td>
                <td className="px-4 py-3">{trade.exit_price.toFixed(5)}</td>
                <td className={`px-4 py-3 font-medium ${trade.pnl_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {trade.pnl_pct > 0 ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
                </td>
                <td className={`px-4 py-3 ${trade.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">{trade.exit_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <div className="flex items-center justify-between mt-4">
        <div className="flex items-center gap-4">
            <span className="text-sm text-[var(--color-text-muted)]">
            Page {currentPage} of {totalPages}
            </span>
            {runId && (
                <button
                    onClick={handleExport}
                    disabled={exporting}
                    className="flex items-center gap-1 text-xs px-2 py-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded hover:bg-[var(--color-surface-hover)] transition-colors text-[var(--color-text)]"
                >
                    <Download size={14} />
                    {exporting ? 'Exporting...' : 'Export CSV'}
                </button>
            )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-1 rounded hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
          >
            <ChevronLeft size={20} />
          </button>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="p-1 rounded hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
