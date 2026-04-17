import React from "react";
import {
  X,
  TrendingUp,
  TrendingDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  ArrowRight,
} from "lucide-react";
import type { DeepDiveTrade } from "./TradeDeepDive";
import type { MaeMfe } from "./chart-utils";
import { formatDuration, formatPrice } from "./chart-utils";

interface TradeDeepDiveHeaderProps {
  trade: DeepDiveTrade;
  maeMfe: MaeMfe | null;
  trades?: DeepDiveTrade[];
  onClose: () => void;
  onNavigate?: (trade: DeepDiveTrade) => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: "Asia/Bangkok", // UTC+7
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
      className={`px-2 py-0.5 rounded text-xs font-semibold tracking-wide ${
        isProfit
          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
          : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
      }`}
    >
      {reason}
    </span>
  );
}

/** A labelled stat pill */
function StatPill({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-slate-500 leading-none">
        {label}
      </span>
      <span className="text-xs text-slate-200 font-mono leading-none whitespace-nowrap">
        {children}
      </span>
    </div>
  );
}

/** Thin vertical rule between stat groups */
function Rule() {
  return <div className="w-px h-7 bg-white/10 shrink-0" />;
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
  const Icon = isWin ? TrendingUp : TrendingDown;

  return (
    <div className="border-b border-white/10 bg-slate-900/60">
      {/* ── Row 1: identity + P&L + nav + close ── */}
      <div className="flex items-center gap-3 px-6 sm:px-8 pt-5 pb-4">
        {/* Icon */}
        <div
          className={`shrink-0 p-2 rounded-lg ${
            isWin ? "bg-emerald-500/15" : "bg-rose-500/15"
          }`}
        >
          <Icon
            className={`w-4 h-4 ${isWin ? "text-emerald-400" : "text-rose-400"}`}
          />
        </div>

        {/* Title */}
        <div className="flex items-baseline gap-2 min-w-0">
          <h2 className="text-base font-bold text-white tracking-tight">
            Trade #{trade.id}
          </h2>
          <span
            className={`shrink-0 px-2 py-0.5 rounded text-xs font-semibold ${
              trade.side === "LONG"
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-rose-500/15 text-rose-400"
            }`}
          >
            {trade.side}
          </span>
          <span className="text-sm font-medium text-slate-400">
            {trade.symbol}
          </span>
        </div>

        {/* P&L */}
        <div
          className={`ml-1 font-mono text-base font-bold ${
            isWin ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {isWin ? "+" : ""}${trade.pnl.toFixed(2)}
          <span className="ml-1.5 text-xs font-normal opacity-70">
            ({isWin ? "+" : ""}{trade.pnlPct.toFixed(2)}%)
          </span>
        </div>

        <div className="flex-1" />

        {/* Prev / Next */}
        {trades && trades.length > 1 && onNavigate && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => hasPrev && onNavigate(trades[currentIdx - 1])}
              disabled={!hasPrev}
              className="p-1.5 rounded-md bg-slate-700/50 hover:bg-slate-700 text-slate-300 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
              title="Previous trade (←)"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-[11px] text-slate-500 font-mono px-1.5 tabular-nums">
              {currentIdx + 1}&thinsp;/&thinsp;{trades.length}
            </span>
            <button
              onClick={() => hasNext && onNavigate(trades[currentIdx + 1])}
              disabled={!hasNext}
              className="p-1.5 rounded-md bg-slate-700/50 hover:bg-slate-700 text-slate-300 disabled:opacity-25 disabled:cursor-not-allowed transition-colors"
              title="Next trade (→)"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Close */}
        <button
          onClick={onClose}
          className="p-1.5 bg-slate-700/50 hover:bg-slate-700 text-slate-400 hover:text-white rounded-md transition-colors"
          title="Close (Esc)"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Rows 2-3: stat grid (2 rows × 2 groups) ── */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-6 sm:px-8 pb-5">
        {/* Row 1, col 1 — Time */}
        <div className="flex items-center gap-4 bg-white/[0.04] rounded-lg px-4 py-2.5">
          <StatPill label="Entry">{formatTime(trade.entryTime)}</StatPill>
          <ArrowRight className="w-3 h-3 text-slate-600 shrink-0" />
          <StatPill label="Exit">
            {trade.exitTime ? formatTime(trade.exitTime) : "—"}
          </StatPill>
          <Rule />
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-slate-500 shrink-0" />
            <span className="text-xs font-mono text-slate-300">{duration}</span>
          </div>
        </div>

        {/* Row 1, col 2 — Prices */}
        <div className="flex items-center gap-4 bg-white/[0.04] rounded-lg px-4 py-2.5">
          <StatPill label="Entry price">
            {formatPrice(trade.entryPrice)}
          </StatPill>
          <ArrowRight className="w-3 h-3 text-slate-600 shrink-0" />
          <StatPill label="Exit price">
            {formatPrice(trade.exitPrice)}
          </StatPill>
        </div>

        {/* Row 2, col 1 — Exit reason */}
        <div className="flex items-center gap-3 bg-white/[0.04] rounded-lg px-4 py-2.5">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            Reason
          </span>
          <ExitReasonBadge reason={trade.exitReason} />
        </div>

        {/* Row 2, col 2 — MAE / MFE */}
        {maeMfe ? (
          <div className="flex items-center gap-4 bg-white/[0.04] rounded-lg px-4 py-2.5">
            <StatPill label="MAE">
              <span className="text-rose-400">
                {(maeMfe.mae * 100).toFixed(2)}%
              </span>
            </StatPill>
            <Rule />
            <StatPill label="MFE">
              <span className="text-emerald-400">
                +{(maeMfe.mfe * 100).toFixed(2)}%
              </span>
            </StatPill>
          </div>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}
