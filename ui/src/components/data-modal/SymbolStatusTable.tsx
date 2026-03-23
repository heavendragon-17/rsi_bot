import React from "react";
import { CheckCircle, AlertTriangle, XCircle, RefreshCw, AlertCircle } from "lucide-react";
import { SymbolDataStatus } from "../../stores/dataPrepStore";
import { cn } from "../../lib/utils";

interface SymbolStatusTableProps {
  symbols: SymbolDataStatus[];
  onAction: (symbol: string, action: "skip" | "partial" | "retry") => void;
}

export const SymbolStatusTable: React.FC<SymbolStatusTableProps> = ({ symbols, onAction }) => {
  return (
    <div className="w-full border border-border-main rounded-lg overflow-hidden bg-bg-surface/50">
      {/* Sticky Header */}
      <div className="grid grid-cols-12 gap-2 px-4 py-2 bg-bg-elevated border-b border-border-main text-xs font-semibold text-text-secondary uppercase tracking-wider sticky top-0 z-10">
        <div className="col-span-4">Symbol</div>
        <div className="col-span-3">Status</div>
        <div className="col-span-2 text-right">Size</div>
        <div className="col-span-3 text-right">Action</div>
      </div>

      {/* Scrollable Body */}
      <div className="max-h-[200px] overflow-y-auto custom-scrollbar">
        {symbols.map((item, index) => (
          <div
            key={item.symbol}
            className={cn(
                "grid grid-cols-12 gap-2 px-4 py-2.5 items-center border-b border-border-main/50 last:border-0 text-sm transition-colors hover:bg-bg-elevated/30",
                index % 2 === 0 ? "bg-transparent" : "bg-bg-elevated/10" // Zebra striping
            )}
          >
            {/* Symbol */}
            <div className="col-span-4 font-medium text-text-primary truncate" title={item.symbol}>
                {item.symbol}
            </div>

            {/* Status */}
            <div className="col-span-3 flex items-center gap-1.5">
                {item.status === "fresh" && (
                    <>
                        <CheckCircle size={14} className="text-success" />
                        <span className="text-xs text-text-secondary">Fresh</span>
                    </>
                )}
                {item.status === "outdated" && (
                    <>
                        <AlertTriangle size={14} className="text-warning" />
                        <span className="text-xs text-text-secondary">Outdated</span>
                    </>
                )}
                {item.status === "missing" && (
                    <>
                        <XCircle size={14} className="text-danger" />
                        <span className="text-xs text-text-secondary">Missing</span>
                    </>
                )}
                {item.status === "downloading" && (
                    <>
                        <RefreshCw size={14} className="text-accent-main animate-spin" />
                        <span className="text-xs text-accent-main font-medium">Syncing...</span>
                    </>
                )}
                {item.status === "error" && (
                    <>
                        <AlertCircle size={14} className="text-danger" />
                        <span className="text-xs text-danger">Failed</span>
                    </>
                )}
            </div>

            {/* Size */}
            <div className="col-span-2 text-right text-xs font-mono text-text-muted">
                {item.sizeBytes ? `${(item.sizeBytes / 1024 / 1024).toFixed(1)} MB` : "—"}
            </div>

            {/* Action */}
            <div className="col-span-3 flex justify-end">
                 {item.status === "fresh" && (
                     <button onClick={() => onAction(item.symbol, "skip")} className="text-xs text-text-muted hover:text-text-primary">
                        Skip
                     </button>
                 )}
                 {item.status === "outdated" && (
                     <button
                        onClick={() => onAction(item.symbol, "partial")}
                        className="px-2 py-0.5 rounded border border-warning/30 bg-warning/10 text-warning hover:bg-warning/20 text-[10px] font-medium transition-colors"
                     >
                        Run Partial
                     </button>
                 )}
                 {item.status === "missing" && (
                    <span className="text-[10px] text-text-muted italic">Queued</span>
                 )}
                 {item.status === "error" && (
                     <button onClick={() => onAction(item.symbol, "retry")} className="text-xs text-accent-main hover:underline">
                        Retry
                     </button>
                 )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
