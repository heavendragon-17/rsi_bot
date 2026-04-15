import React from "react";
import {
  X,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import type { DeepDiveTrade } from "./TradeDeepDive";
import type { MaeMfe } from "./chart-utils";
import { formatDuration } from "./chart-utils";

interface TradeDeepDiveHeaderProps {
  trade: DeepDiveTrade;
  maeMfe: MaeMfe | null;
  trades?: DeepDiveTrade[];
  onClose: () => void;
  onNavigate?: (trade: DeepDiveTrade) => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const isProfit =
    reason === "TP1" ||
    reason === "TP2" ||
    reason === "TP3" ||
    reason === "LOCK_PROFIT";
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium ${
        isProfit
          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
          : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
      }`}
    >
      {reason}
    </span>
  );
}

/** A single `Label · Value` chip in the info strip */
function Chip({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200 font-mono">{value}</span>
    </span>
  );
}

/** Vertical divider between chips */
function Sep() {
  return <span className="text-slate-700 select-none">|</span>;
}

export function TradeDeepDiveHeader({
  trade,
  maeMfe,
  trades,
  onClose,
  onNavigate,
}: TradeDeepDiveHeaderProps) {
  const isWin = trade.pnl > 0;
  const currentIdx = trades?.findIndex((t) => t.id === trade.id) ?? -1;
  const hasPrev = currentIdx > 0;
  const hasNext = trades !== undefined && currentIdx < trades.length - 1;
  const duration = formatDuration(trade.entryTime, trade.exitTime);

  return (
    <div className="border-b border-white/10 bg-slate-900/50 px-5 py-3 flex items-center gap-4 flex-wrap">
      {/* Identity icon */}
      <div
        className={`shrink-0 p-2 rounded-lg ${
          isWin ? "bg-emerald-500/20" : "bg-rose-500/20"
        }`}
      >
        <TrendingUp
          className={`w-4 h-4 ${isWin ? "text-emerald-400" : "text-rose-400"}`}
        />
      </div>

      {/* Title block */}
      <div className="flex items-baseline gap-2 shrink-0">
        <span className="text-lg font-bold text-white">
          Trade #{trade.id}
        </span>
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${
            trade.side === "LONG"
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-rose-500/20 text-rose-400"
          }`}
        >
          {trade.side}
        </span>
        <span className="text-sm font-semibold text-slate-300">
          {trade.symbol}
        </span>
        <span
          className={`text-base font-mono font-bold ${
            isWin ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {isWin ? "+" : ""}${trade.pnl.toFixed(2)}{" "}
          <span className="text-sm font-normal opacity-80">
            ({isWin ? "+" : ""}{trade.pnlPct.toFixed(2)}%)
          </span>
        </span>
      </div>

      {/* Compact info strip */}
      <div className="flex items-center gap-2 flex-wrap text-xs min-w-0">
        <Sep />
        <Chip label="Entry" value={formatTime(trade.entryTime)} />
        <Sep />
        <Chip
          label="Exit"
          value={trade.exitTime ? formatTime(trade.exitTime) : "—"}
        />
        <Sep />
        <Chip label="Duration" value={duration} />
        <Sep />
        <Chip label="Entry $" value={`$${trade.entryPrice.toFixed(2)}`} />
        <Chip label="→" value={`$${trade.exitPrice.toFixed(2)}`} />
        <Sep />
        <span className="flex items-center gap-1 text-xs">
          <span className="text-slate-500">Reason</span>
          <ExitReasonBadge reason={trade.exitReason} />
        </span>
        {maeMfe && (
          <>
            <Sep />
            <span className="font-mono text-rose-400 text-xs">
              MAE {(maeMfe.mae * 100).toFixed(2)}%
            </span>
            <span className="font-mono text-emerald-400 text-xs">
              MFE +{(maeMfe.mfe * 100).toFixed(2)}%
            </span>
          </>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Prev/Next navigation */}
      {trades && trades.length > 1 && onNavigate && (
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => hasPrev && onNavigate(trades[currentIdx - 1])}
            disabled={!hasPrev}
            className="p-1.5 rounded-lg bg-slate-700/50 hover:bg-slate-700 text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            title="Previous trade (←)"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-400 px-1.5 font-mono">
            {currentIdx + 1} / {trades.length}
          </span>
          <button
            onClick={() => hasNext && onNavigate(trades[currentIdx + 1])}
            disabled={!hasNext}
            className="p-1.5 rounded-lg bg-slate-700/50 hover:bg-slate-700 text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            title="Next trade (→)"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Close */}
      <button
        onClick={onClose}
        className="shrink-0 p-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg transition-all"
        title="Close (Esc)"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
