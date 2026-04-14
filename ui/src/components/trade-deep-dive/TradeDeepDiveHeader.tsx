import React from "react";
import {
  X,
  TrendingUp,
  Calendar,
  DollarSign,
  Target,
  Clock,
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
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const isProfit = reason === "TP1" || reason === "TP2" || reason === "TP3" || reason === "LOCK_PROFIT";
  return (
    <span
      className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${
        isProfit
          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
          : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
      }`}
    >
      {reason}
    </span>
  );
}

function StatCell({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-slate-400 flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className="text-sm text-white font-mono">{value}</div>
    </div>
  );
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
    <div className="border-b border-white/10 bg-slate-900/50">
      {/* Top row: identity + nav + close */}
      <div className="p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div
            className={`p-3 rounded-xl ${
              isWin ? "bg-emerald-500/20" : "bg-rose-500/20"
            }`}
          >
            <TrendingUp
              className={`w-6 h-6 ${
                isWin ? "text-emerald-400" : "text-rose-400"
              }`}
            />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold text-white">
                Trade #{trade.id}
              </h2>
              <span
                className={`px-3 py-1 rounded-lg text-sm font-medium ${
                  trade.side === "LONG"
                    ? "bg-emerald-500/20 text-emerald-400"
                    : "bg-rose-500/20 text-rose-400"
                }`}
              >
                {trade.side}
              </span>
              <span className="text-xl font-bold text-white">
                {trade.symbol}
              </span>
            </div>
            <div
              className={`text-lg font-mono mt-1 ${
                isWin ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {isWin ? "+" : ""}${trade.pnl.toFixed(2)} ({isWin ? "+" : ""}
              {trade.pnlPct.toFixed(2)}%)
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Prev/Next navigation */}
          {trades && trades.length > 1 && onNavigate && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => hasPrev && onNavigate(trades[currentIdx - 1])}
                disabled={!hasPrev}
                className="p-1.5 rounded-lg bg-slate-700/50 hover:bg-slate-700 text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                title="Previous trade (←)"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-slate-400 px-2 font-mono">
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
          <button
            onClick={onClose}
            className="p-2 bg-slate-700/50 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg transition-all"
            title="Close (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-6 gap-4 px-6 pb-5">
        <StatCell
          icon={<Calendar className="w-3 h-3" />}
          label="Entry Time"
          value={formatTime(trade.entryTime)}
        />
        <StatCell
          icon={<Calendar className="w-3 h-3" />}
          label="Exit Time"
          value={trade.exitTime ? formatTime(trade.exitTime) : "—"}
        />
        <StatCell
          icon={<Clock className="w-3 h-3" />}
          label="Duration"
          value={duration}
        />
        <StatCell
          icon={<DollarSign className="w-3 h-3" />}
          label="Entry Price"
          value={`$${trade.entryPrice.toFixed(2)}`}
        />
        <StatCell
          icon={<DollarSign className="w-3 h-3" />}
          label="Exit Price"
          value={`$${trade.exitPrice.toFixed(2)}`}
        />
        <StatCell
          icon={<Target className="w-3 h-3" />}
          label="Exit Reason"
          value={<ExitReasonBadge reason={trade.exitReason} />}
        />
      </div>

      {/* MAE / MFE badges */}
      {maeMfe && (
        <div className="flex items-center gap-3 px-6 pb-4">
          <span className="text-xs text-slate-400 font-medium">Excursion:</span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20">
            MAE {(maeMfe.mae * 100).toFixed(2)}%
          </span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            MFE +{(maeMfe.mfe * 100).toFixed(2)}%
          </span>
        </div>
      )}
    </div>
  );
}
