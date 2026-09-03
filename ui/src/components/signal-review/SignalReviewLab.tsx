import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CalendarRange,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Database,
  FileText,
  HelpCircle,
  MinusCircle,
  Play,
  RefreshCw,
  Save,
  Target,
  TrendingDown,
  Trophy,
  XCircle,
} from "lucide-react";
import { SignalChart } from "./SignalChart";
import {
  REVIEW_SIGNAL_PAGE_SIZE,
} from "../../lib/signal-review";
import { useSignalReviewStore } from "../../stores/signalReviewStore";
import type { SignalReviewUpdate } from "../../types/generated";

function displayDate(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    timeZone: "Asia/Bangkok",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function displayDateOnly(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    timeZone: "Asia/Bangkok",
    dateStyle: "medium",
  });
}

function price(value?: string | null): string {
  if (!value) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : value;
}

function pct(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function duration(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value < 60) return `${value}m`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

const EXIT_REASON_LABELS: Record<string, string> = {
  TAKE_PROFIT: "Take-profit touched",
  STOP_LOSS: "Stop-loss touched",
  BOTH_SAME_CANDLE: "Both levels touched in one candle",
  OPEN: "Neither level touched",
  NO_DATA: "Could not evaluate",
};

const ACTIVE_QUALITY_CLASSES: Record<string, string> = {
  emerald: "border-emerald-400/60 bg-emerald-400/20 text-emerald-200",
  rose: "border-rose-400/60 bg-rose-400/20 text-rose-200",
  amber: "border-amber-400/60 bg-amber-400/20 text-amber-200",
};

function qualityClasses(active: boolean, color: string): string {
  return active
    ? ACTIVE_QUALITY_CLASSES[color]
    : "border-border-main bg-bg-elevated/40 text-text-secondary hover:text-text-primary";
}

const RUN_PHASE_LABELS: Record<string, string> = {
  starting: "Starting replay",
  load: "Loading market data",
  signals: "Finding qualifying signals",
  metrics: "Preparing forward observations",
  saving: "Saving the review dataset",
  complete: "Dataset ready",
};

function ReplayLauncher() {
  const startReplay = useSignalReviewStore((state) => state.startReplay);
  const availability = useSignalReviewStore((state) => state.availability);
  const loadAvailability = useSignalReviewStore((state) => state.loadAvailability);
  const isLoadingAvailability = useSignalReviewStore((state) => state.isLoadingAvailability);
  const runs = useSignalReviewStore((state) => state.runs);
  const isRunning = useSignalReviewStore((state) => state.isRunning);
  const runProgress = useSignalReviewStore((state) => state.runProgress);
  const runPhase = useSignalReviewStore((state) => state.runPhase);
  const error = useSignalReviewStore((state) => state.error);
  const [scope, setScope] = useState<"all" | "30d" | "90d" | "365d">("all");
  const latestCompleted = runs.find((run) => run.status === "completed");
  const ready = availability?.ready === true;
  const phaseLabel = RUN_PHASE_LABELS[runPhase] ?? "Building review dataset";

  return (
    <section className="rounded-xl border border-border-main bg-bg-primary/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Database size={16} className="text-accent-main" />
            <h2 className="font-semibold text-text-primary">Review dataset</h2>
          </div>
          <p className="mt-1 text-xs text-text-muted">
            The replay is constrained to the aligned local M5, M15, H1, and H4 coverage.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadAvailability()}
          disabled={isLoadingAvailability || isRunning}
          className="inline-flex items-center gap-1.5 rounded-md border border-border-main px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary disabled:opacity-50"
        >
          <RefreshCw size={13} className={isLoadingAvailability ? "animate-spin" : ""} />
          Check coverage
        </button>
      </div>
      <div className={`mt-4 rounded-lg border px-3 py-3 ${ready ? "border-emerald-400/25 bg-emerald-400/5" : "border-amber-400/25 bg-amber-400/5"}`}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
          {ready ? <CheckCircle2 size={15} className="text-emerald-300" /> : <CircleAlert size={15} className="text-amber-300" />}
          <span className={ready ? "text-emerald-200" : "text-amber-200"}>
            {ready ? "All four sources are ready" : "Replay data needs attention"}
          </span>
          {ready && (
            <span className="inline-flex items-center gap-1.5 text-text-secondary">
              <CalendarRange size={13} />
              {displayDate(availability?.common_start_at)} – {displayDate(availability?.common_end_at)} (UTC+7)
            </span>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {availability?.sources.map((source) => (
            <span
              key={source.timeframe}
              title={source.error ?? `${displayDateOnly(source.available_start)} – ${displayDateOnly(source.available_end)}`}
              className={`rounded-md border px-2 py-1 text-[11px] ${source.available ? "border-border-main bg-bg-elevated/60 text-text-secondary" : "border-rose-400/30 bg-rose-400/10 text-rose-200"}`}
            >
              {source.timeframe.toUpperCase()} · {source.available ? source.row_count.toLocaleString() : "missing"}
            </span>
          ))}
        </div>
        {!ready && availability?.sources.some((source) => source.error) && (
          <p className="mt-2 text-[11px] text-amber-200">
            {availability.sources.filter((source) => source.error).map((source) => source.error).join(" · ")}
          </p>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-text-secondary">
          Replay scope
          <select
            value={scope}
            onChange={(event) => setScope(event.target.value as typeof scope)}
            disabled={!ready || isRunning}
            className="mt-1 block rounded-md border border-border-main bg-input px-3 py-2 text-sm text-text-primary disabled:opacity-50"
          >
            <option value="all">All available data</option>
            <option value="30d">Latest 30 days</option>
            <option value="90d">Latest 90 days</option>
            <option value="365d">Latest 1 year</option>
          </select>
        </label>
        <button
          type="button"
          disabled={isRunning || !ready}
          onClick={() => void startReplay(scope)}
          className="inline-flex items-center gap-2 rounded-md bg-accent-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          <Play size={14} />
          {isRunning ? `${phaseLabel} · ${Math.round(runProgress)}%` : latestCompleted ? "Rebuild review dataset" : "Build review dataset"}
        </button>
      </div>
      {isRunning && (
        <div className="mt-3 space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-text-muted">
            <span className="inline-flex items-center gap-1.5"><Clock3 size={12} />{phaseLabel}</span>
            <span>{Math.round(runProgress)}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-bg-elevated">
            <div className="h-full bg-accent-main transition-all" style={{ width: `${runProgress}%` }} />
          </div>
        </div>
      )}
      {error && <p className="mt-3 text-xs text-danger">{error}</p>}
      <p className="mt-3 text-xs text-text-muted">
        Rebuilding creates a new immutable dataset. Existing human reviews remain attached to their original replay run.
      </p>
    </section>
  );
}

function SignalList() {
  const signals = useSignalReviewStore((state) => state.signals);
  const total = useSignalReviewStore((state) => state.total);
  const page = useSignalReviewStore((state) => state.page);
  const pages = useSignalReviewStore((state) => state.pages);
  const isLoading = useSignalReviewStore((state) => state.isLoading);
  const timeframe = useSignalReviewStore((state) => state.timeframe);
  const qualityFilter = useSignalReviewStore((state) => state.qualityFilter);
  const outcomeFilter = useSignalReviewStore((state) => state.outcomeFilter);
  const runs = useSignalReviewStore((state) => state.runs);
  const selectedRunId = useSignalReviewStore((state) => state.selectedRunId);
  const setTimeframe = useSignalReviewStore((state) => state.setTimeframe);
  const setQualityFilter = useSignalReviewStore((state) => state.setQualityFilter);
  const setOutcomeFilter = useSignalReviewStore((state) => state.setOutcomeFilter);
  const setSelectedRunId = useSignalReviewStore((state) => state.setSelectedRunId);
  const loadSignals = useSignalReviewStore((state) => state.loadSignals);
  const loadSignal = useSignalReviewStore((state) => state.loadSignal);

  return (
    <section className="rounded-xl border border-border-main bg-bg-primary/50 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-main p-3">
        <select
          value={selectedRunId ?? ""}
          onChange={(event) => setSelectedRunId(Number(event.target.value))}
          disabled={runs.every((run) => run.status !== "completed")}
          className="max-w-[260px] rounded-md border border-border-main bg-input px-2.5 py-1.5 text-xs text-text-secondary disabled:opacity-50"
          aria-label="Replay dataset"
        >
          {runs.filter((run) => run.status === "completed").map((run) => (
            <option key={run.id} value={run.id}>
              Run #{run.id} · {displayDateOnly(run.created_at)} · {run.signal_count} signals
            </option>
          ))}
        </select>
        <span className="h-5 w-px bg-border-main mx-1" />
        {(["5m", "15m"] as const).map((tf) => (
          <button
            type="button"
            key={tf}
            onClick={() => setTimeframe(tf)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold ${timeframe === tf ? "bg-accent-main text-white" : "bg-bg-elevated text-text-secondary"}`}
          >
            {tf.toUpperCase()} signals
          </button>
        ))}
        <span className="h-5 w-px bg-border-main mx-1" />
        <select
          value={qualityFilter}
          onChange={(event) => setQualityFilter(event.target.value)}
          className="rounded-md border border-border-main bg-input px-2.5 py-1.5 text-xs text-text-secondary"
        >
          <option value="UNREVIEWED">Needs review</option>
          <option value="">All quality labels</option>
          <option value="GOOD">Good signals</option>
          <option value="BAD">Bad signals</option>
          <option value="UNCERTAIN">Uncertain signals</option>
        </select>
        <select
          value={outcomeFilter}
          onChange={(event) => setOutcomeFilter(event.target.value)}
          className="rounded-md border border-border-main bg-input px-2.5 py-1.5 text-xs text-text-secondary"
        >
          <option value="">All outcomes</option>
          <option value="WIN">Human WIN</option>
          <option value="LOSS">Human LOSS</option>
          <option value="SKIP">Human SKIP</option>
          <option value="UNSET">Outcome unset</option>
        </select>
        <button
          type="button"
          onClick={() => void loadSignals(page)}
          className="ml-auto rounded-md p-2 text-text-secondary hover:text-text-primary"
          title="Refresh signals"
        >
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-bg-elevated/50 text-xs uppercase tracking-wide text-text-muted">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">TF</th>
              <th className="px-4 py-3">Trigger close</th>
              <th className="px-4 py-3">Quality</th>
              <th className="px-4 py-3">Outcome</th>
              <th className="px-4 py-3">Note</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-main">
            {signals.map((signal) => (
              <tr
                key={signal.id}
                onClick={() => void loadSignal(signal.id)}
                className="cursor-pointer hover:bg-bg-elevated/40 transition-colors"
              >
                <td className="px-4 py-3 whitespace-nowrap text-text-primary">{displayDate(signal.trigger_close_at)}</td>
                <td className="px-4 py-3 font-mono text-accent-main">{signal.timeframe.toUpperCase()}</td>
                <td className="px-4 py-3 font-mono text-text-primary">{price(signal.trigger_close_price)}</td>
                <td className="px-4 py-3">
                  <span className={`rounded px-2 py-1 text-[10px] font-semibold ${signal.quality === "GOOD" ? "bg-emerald-400/15 text-emerald-300" : signal.quality === "BAD" ? "bg-rose-400/15 text-rose-300" : "bg-bg-elevated text-text-muted"}`}>
                    {signal.quality}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-text-secondary">{signal.human_outcome}</td>
                <td className="px-4 py-3 text-text-muted">{signal.note_present ? <FileText size={15} /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && signals.length === 0 && (
          <div className="p-10 text-center text-sm text-text-muted">No signals match this dataset and filter. Change the filter or build a new dataset.</div>
        )}
        {isLoading && <div className="p-10 text-center text-sm text-text-muted">Loading signal records…</div>}
      </div>
      <div className="flex items-center justify-between border-t border-border-main px-4 py-3 text-xs text-text-muted">
        <span>{total} signals</span>
        <div className="flex items-center gap-2">
          <button type="button" disabled={page <= 1} onClick={() => void loadSignals(page - 1)} className="rounded p-1 disabled:opacity-30"><ChevronLeft size={16} /></button>
          <span>{page} / {pages}</span>
          <button type="button" disabled={page >= pages} onClick={() => void loadSignals(page + 1)} className="rounded p-1 disabled:opacity-30"><ChevronRight size={16} /></button>
        </div>
      </div>
    </section>
  );
}

function ReviewerDecisionBar() {
  const selected = useSignalReviewStore((state) => state.selected);
  const chart = useSignalReviewStore((state) => state.chart);
  const saveReview = useSignalReviewStore((state) => state.saveReview);
  const reviewSaveState = useSignalReviewStore((state) => state.reviewSaveState);
  const [note, setNote] = useState("");
  const review = selected?.review;
  const futureUnlocked = review?.quality !== "UNREVIEWED";
  const chartRows = (chart?.candles ?? []) as Array<{ is_trigger?: boolean }>;
  const triggerIndex = chartRows.findIndex((row) => row.is_trigger);
  const futureCandlesLoaded = triggerIndex >= 0
    ? chartRows.length - triggerIndex - 1
    : 0;

  useEffect(() => {
    setNote(review?.note ?? "");
  }, [selected?.id]);

  useEffect(() => {
    if (
      !selected
      || reviewSaveState === "saving"
      || note === (selected.review.note ?? "")
    ) return undefined;
    const timer = window.setTimeout(() => void saveReview({ note }), 600);
    return () => window.clearTimeout(timer);
  }, [note, reviewSaveState, selected?.id, selected?.review.note, saveReview]);

  if (!selected || !review) return null;

  const qualityOptions = [
    { value: "GOOD", label: "Good entry", helper: "Setup is valid", color: "emerald", icon: CheckCircle2 },
    { value: "BAD", label: "Bad entry", helper: "Setup is invalid", color: "rose", icon: XCircle },
    { value: "UNCERTAIN", label: "Uncertain", helper: "Needs another look", color: "amber", icon: HelpCircle },
  ];
  const outcomes = [
    { value: "WIN", label: "WIN", helper: "Strategy worked", icon: Trophy, active: "border-emerald-400/60 bg-emerald-400/20 text-emerald-200" },
    { value: "LOSS", label: "LOSS", helper: "Strategy failed", icon: TrendingDown, active: "border-rose-400/60 bg-rose-400/20 text-rose-200" },
    { value: "SKIP", label: "SKIP", helper: "Cannot confirm", icon: MinusCircle, active: "border-slate-400/60 bg-slate-400/20 text-slate-200" },
  ];
  const saveLabel = reviewSaveState === "saving"
    ? "Saving review…"
    : reviewSaveState === "saved"
      ? "Review saved"
      : reviewSaveState === "error"
        ? "Review could not be saved"
        : "Autosave ready";
  const futureLabel = !futureUnlocked
    ? "Future chart locked until quality review"
    : chart?.future_allowed && futureCandlesLoaded > 0
      ? `${futureCandlesLoaded.toLocaleString()} future candles loaded`
      : "Loading future candles…";

  return (
    <section className="rounded-xl border border-accent-main/30 bg-bg-primary/95 p-4 shadow-xl shadow-black/10 backdrop-blur-md">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 rounded-lg bg-accent-main/15 p-2 text-accent-main">
            <Save size={16} />
          </div>
          <div>
            <h2 className="font-semibold text-text-primary">Human review</h2>
            <p className="mt-0.5 text-xs text-text-muted">Set optional TP/SL levels first, then judge the chart and inspect the revealed future.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className={`rounded-full border px-2.5 py-1 ${futureUnlocked ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : "border-amber-400/30 bg-amber-400/10 text-amber-200"}`}>
            {futureLabel}
          </span>
          <span aria-live="polite" className={`rounded-full border px-2.5 py-1 ${reviewSaveState === "error" ? "border-rose-400/30 text-rose-200" : "border-border-main text-text-muted"}`}>
            {saveLabel}
          </span>
        </div>
      </div>
      <div className="grid gap-3 xl:grid-cols-[1fr_1fr_minmax(260px,0.8fr)]">
        <div className="rounded-lg border border-border-main bg-bg-elevated/35 p-3">
          <div className="mb-2.5 flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-main text-xs font-bold text-white">1</span>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Entry quality</h3>
              <p className="text-[11px] text-text-muted">Use only information available at the signal.</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {qualityOptions.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  type="button"
                  key={option.value}
                  disabled={reviewSaveState === "saving"}
                  aria-pressed={review.quality === option.value}
                  onClick={() => void saveReview({ quality: option.value } as SignalReviewUpdate)}
                  className={`min-h-12 rounded-lg border px-2.5 py-2 text-left transition-colors disabled:cursor-wait disabled:opacity-50 ${qualityClasses(review.quality === option.value, option.color)}`}
                >
                  <span className="flex items-center gap-1.5 text-xs font-semibold"><Icon size={14} />{option.label}</span>
                  <span className="mt-0.5 block text-[10px] opacity-75">{option.helper}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className={`rounded-lg border p-3 transition-colors ${futureUnlocked ? "border-violet-400/25 bg-violet-400/5" : "border-border-main bg-bg-elevated/20"}`}>
          <div className="mb-2.5 flex items-center gap-2">
            <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${futureUnlocked ? "bg-violet-500 text-white" : "bg-bg-elevated text-text-muted"}`}>2</span>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">Manual outcome</h3>
              <p className="text-[11px] text-text-muted">{futureUnlocked ? "Optional human label; TP/SL results stay separate." : "Choose a label when ready to reveal future candles."}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {outcomes.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  type="button"
                  key={option.value}
                  disabled={!futureUnlocked || reviewSaveState === "saving"}
                  aria-pressed={review.human_outcome === option.value}
                  onClick={() => void saveReview({ human_outcome: option.value } as SignalReviewUpdate)}
                  className={`min-h-12 rounded-lg border px-2.5 py-2 text-left transition-colors ${review.human_outcome === option.value ? option.active : "border-border-main bg-bg-elevated/40 text-text-secondary hover:text-text-primary"} disabled:cursor-not-allowed disabled:opacity-35`}
                >
                  <span className="flex items-center gap-1.5 text-xs font-bold"><Icon size={14} />{option.label}</span>
                  <span className="mt-0.5 block text-[10px] opacity-75">{option.helper}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="rounded-lg border border-border-main bg-bg-elevated/25 p-3">
          <label htmlFor={`review-note-${selected.id}`} className="text-sm font-semibold text-text-primary">Reviewer note</label>
          <p className="mt-0.5 text-[11px] text-text-muted">Capture the reason for your labels.</p>
          <textarea
            id={`review-note-${selected.id}`}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onBlur={() => {
              if (note !== (selected.review.note ?? "")) void saveReview({ note });
            }}
            rows={3}
            placeholder="What made this entry good, bad, or uncertain?"
            className="mt-2 w-full resize-y rounded-md border border-border-main bg-input px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:border-accent-main focus:outline-none"
          />
          <p className={`mt-1.5 text-[10px] ${reviewSaveState === "error" ? "text-danger" : "text-text-muted"}`}>
            Autosaves after you pause typing{review.updated_at ? ` · Updated ${displayDate(review.updated_at)}` : ""}
          </p>
        </div>
      </div>
    </section>
  );
}

function TradePlanPanel() {
  const selected = useSignalReviewStore((state) => state.selected);
  const saveReview = useSignalReviewStore((state) => state.saveReview);
  const reviewSaveState = useSignalReviewStore((state) => state.reviewSaveState);
  const [takeProfit, setTakeProfit] = useState("");
  const [stopLoss, setStopLoss] = useState("");

  const review = selected?.review;
  useEffect(() => {
    setTakeProfit(review?.take_profit_price ?? "");
    setStopLoss(review?.stop_loss_price ?? "");
  }, [selected?.id, review?.take_profit_price, review?.stop_loss_price]);

  if (!selected || !review) return null;

  const hasOnePrice = Boolean(takeProfit.trim()) !== Boolean(stopLoss.trim());
  const existingTakeProfit = review.take_profit_price ?? "";
  const existingStopLoss = review.stop_loss_price ?? "";
  const isDirty = takeProfit.trim() !== existingTakeProfit || stopLoss.trim() !== existingStopLoss;
  const isSaving = reviewSaveState === "saving";
  const hasPlan = Boolean(existingTakeProfit && existingStopLoss);
  const resultLabel = review.exit_reason
    ? EXIT_REASON_LABELS[review.exit_reason] ?? review.exit_reason
    : hasPlan
      ? review.quality === "UNREVIEWED" ? "Waiting for quality review" : "Not evaluated"
      : "No TP/SL plan saved";

  return (
    <section className="rounded-xl border border-accent-main/25 bg-bg-primary/50 p-4">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 rounded-lg bg-accent-main/15 p-2 text-accent-main"><Target size={16} /></div>
        <div>
          <h3 className="font-semibold text-text-primary">TP/SL trade plan</h3>
          <p className="mt-0.5 text-[11px] text-text-muted">Set this before deciding whether the chart is good, bad, or uncertain.</p>
        </div>
      </div>
      <form
        className="mt-3 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (isSaving || hasOnePrice || !isDirty) return;
          void saveReview({
            take_profit_price: takeProfit.trim() || null,
            stop_loss_price: stopLoss.trim() || null,
          });
        }}
      >
        <div className="space-y-3">
          <label className="block text-[11px] text-text-muted">
            <span className="flex items-center justify-between gap-2">
              <span>Signal entry</span>
              <span className="text-[10px] text-text-secondary">Fixed</span>
            </span>
            <input
              aria-label="Signal entry"
              value={selected.trigger_close_price}
              readOnly
              className="mt-1 w-full rounded-md border border-border-main bg-bg-elevated/60 px-3 py-2.5 font-mono text-sm text-text-secondary"
            />
          </label>
          <label className="block text-[11px] text-emerald-300">
            <span className="flex items-center justify-between gap-2">
              <span>Take profit</span>
              <span className="text-[10px] text-text-muted">Long target</span>
            </span>
            <input
              aria-label="Take profit"
              inputMode="decimal"
              value={takeProfit}
              onChange={(event) => setTakeProfit(event.target.value)}
              disabled={isSaving}
              placeholder="e.g. 65000"
              className="mt-1 w-full rounded-md border border-emerald-400/35 bg-input px-3 py-2.5 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-emerald-300 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
          </label>
          <label className="block text-[11px] text-rose-300">
            <span className="flex items-center justify-between gap-2">
              <span>Stop loss</span>
              <span className="text-[10px] text-text-muted">Long protection</span>
            </span>
            <input
              aria-label="Stop loss"
              inputMode="decimal"
              value={stopLoss}
              onChange={(event) => setStopLoss(event.target.value)}
              disabled={isSaving}
              placeholder="e.g. 63000"
              className="mt-1 w-full rounded-md border border-rose-400/35 bg-input px-3 py-2.5 font-mono text-sm text-text-primary placeholder:text-text-muted focus:border-rose-300 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
          </label>
        </div>
        {review.quality === "UNREVIEWED" && <p className="text-[11px] text-amber-300">Save both levels now. Future candles stay hidden until you select the chart quality.</p>}
        {review.quality !== "UNREVIEWED" && <p className="text-[11px] text-text-muted">The saved plan is evaluated against future candles from the signal timeframe.</p>}
        {hasOnePrice && <p className="text-[11px] text-rose-300">Enter both TP and SL, or clear both to remove the plan.</p>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="submit"
            disabled={isSaving || hasOnePrice || !isDirty}
            className="inline-flex min-h-10 items-center gap-2 rounded-md bg-accent-main px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Save size={14} />{hasPlan ? "Update TP/SL" : "Save TP/SL"}
          </button>
          {hasPlan && <span className="text-[10px] text-text-muted">Saved with the signal review</span>}
        </div>
      </form>
      <div className="mt-4 rounded-lg border border-border-main bg-bg-elevated/35 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-text-primary">Candle result</span>
          <span className={`text-xs font-semibold ${review.exit_reason === "TAKE_PROFIT" ? "text-emerald-300" : review.exit_reason === "STOP_LOSS" ? "text-rose-300" : "text-text-secondary"}`}>{resultLabel}</span>
        </div>
        {review.exit_at && <p className="mt-1 text-[11px] text-text-muted">Exit candle: {displayDate(review.exit_at)} · Time to exit: {duration(review.duration_minutes)}</p>}
        {review.evaluation_warning && <p className="mt-1 text-[11px] text-amber-300">{review.evaluation_warning}</p>}
        <p className="mt-2 text-[10px] text-text-muted">This reports the first level touched from native {selected.timeframe.toUpperCase()} candles. It does not calculate 1R, PnL, or a WIN/LOSS label.</p>
      </div>
    </section>
  );
}

function SignalDetail() {
  const selected = useSignalReviewStore((state) => state.selected);
  const chart = useSignalReviewStore((state) => state.chart);
  const chartTimeframe = useSignalReviewStore((state) => state.chartTimeframe);
  const isLoading = useSignalReviewStore((state) => state.isLoadingDetail);
  const isLoadingChart = useSignalReviewStore((state) => state.isLoadingChart);
  const signals = useSignalReviewStore((state) => state.signals);
  const total = useSignalReviewStore((state) => state.total);
  const page = useSignalReviewStore((state) => state.page);
  const pages = useSignalReviewStore((state) => state.pages);
  const clearSelection = useSignalReviewStore((state) => state.clearSelection);
  const loadAdjacentSignal = useSignalReviewStore((state) => state.loadAdjacentSignal);
  const loadMoreChart = useSignalReviewStore((state) => state.loadMoreChart);
  const setChartTimeframe = useSignalReviewStore((state) => state.setChartTimeframe);
  if (!selected) return null;
  const currentMetric = selected.forward_metrics;
  const currentIndex = signals.findIndex((signal) => signal.id === selected.id);
  const reviewPosition = currentIndex >= 0
    ? (page - 1) * REVIEW_SIGNAL_PAGE_SIZE + currentIndex + 1
    : null;
  const hasPrevious = currentIndex > 0 || page > 1;
  const hasNext = (currentIndex >= 0 && currentIndex < signals.length - 1) || page < pages;
  const outcomeRecorded = selected.review.human_outcome !== "UNSET";

  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={clearSelection} className="inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary">
            <ArrowLeft size={16} /> Back to signals
          </button>
          <div className="border-l border-border-main pl-3">
            <p className="text-sm font-medium text-text-primary">{reviewPosition ? `Signal ${reviewPosition.toLocaleString()} of ${total.toLocaleString()}` : "Signal review"}</p>
            <p className="font-mono text-[11px] text-text-muted">#{String(selected.sequence).padStart(4, "0")} · {selected.timeframe.toUpperCase()} · {displayDate(selected.trigger_close_at)}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" disabled={!hasPrevious} onClick={() => void loadAdjacentSignal(-1)} className="inline-flex min-h-10 items-center gap-1 rounded-md border border-border-main px-3 py-2 text-xs text-text-secondary hover:border-accent-main hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-35">
            <ChevronLeft size={14} /> Previous
          </button>
          <button type="button" disabled={!hasNext} onClick={() => void loadAdjacentSignal(1)} className={`inline-flex min-h-10 items-center gap-1 rounded-md border px-3 py-2 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-35 ${outcomeRecorded ? "border-accent-main bg-accent-main text-white hover:bg-accent-hover" : "border-border-main text-text-secondary hover:border-accent-main hover:text-text-primary"}`}>
            Next signal <ChevronRight size={14} />
          </button>
        </div>
      </div>
      {isLoading && <div className="text-sm text-text-muted">Loading signal…</div>}
      <ReviewerDecisionBar />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-12">
        <div className="min-w-0 space-y-4 lg:col-span-8">
          <SignalChart
            chart={chart ?? {
              signal_id: selected.id,
              timeframe: chartTimeframe,
              candles: [],
              available_start: null,
              available_end: null,
              requested_start: null,
              requested_end: null,
              has_before: false,
              has_after: false,
              future_allowed: false,
              signal_time: selected.trigger_close_at,
              anchor_time: null,
              warning: "Loading chart…",
            }}
            triggerClosePrice={Number(selected.trigger_close_price)}
            takeProfitPrice={selected.review.take_profit_price ? Number(selected.review.take_profit_price) : null}
            stopLossPrice={selected.review.stop_loss_price ? Number(selected.review.stop_loss_price) : null}
            onLoadMore={loadMoreChart}
            onTimeframeChange={setChartTimeframe}
            isLoading={isLoadingChart}
          />
          <section className="rounded-xl border border-border-main bg-bg-primary/50 p-4">
            <div className="flex items-center gap-2 mb-3"><Database size={16} className="text-accent-main" /><h3 className="font-semibold text-text-primary">Forward market observations</h3></div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
              {currentMetric.map((metric) => (
                <div key={metric.horizon_minutes} className="rounded-lg bg-bg-elevated/60 p-3">
                  <p className="text-[11px] text-text-muted">+{metric.horizon_minutes / 60}h return</p>
                  <p className={`mt-1 font-mono text-sm ${metric.return_pct != null && metric.return_pct >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{pct(metric.return_pct)}</p>
                  <p className="mt-1 text-[10px] text-text-muted">MFE {pct(metric.mfe_pct)} · MAE {pct(metric.mae_pct)}</p>
                  {!metric.complete && <p className="mt-1 text-[10px] text-amber-300">Partial data</p>}
                </div>
              ))}
            </div>
          </section>
        </div>
        <div className="min-w-0 space-y-4 lg:col-span-4">
          <TradePlanPanel />
          <section className="rounded-xl border border-border-main bg-bg-primary/50 p-4">
            <div className="flex items-center justify-between mb-3"><h3 className="font-semibold text-text-primary">Telegram alert snapshot</h3><span className="text-[10px] text-text-muted">{displayDate(selected.trigger_close_at)}</span></div>
            <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-lg bg-black/20 p-3 font-mono text-xs leading-5 text-text-secondary">{selected.telegram_card}</pre>
          </section>
          <section className="rounded-xl border border-border-main bg-bg-primary/50 p-4">
            <h3 className="mb-3 font-semibold text-text-primary">Structured confirmation</h3>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <span className="text-text-muted">Trigger close</span><span className="font-mono text-text-primary">{price(selected.trigger_close_price)}</span>
              <span className="text-text-muted">Trigger EMA21</span><span className="font-mono text-text-primary">{price(selected.trigger_price_ema21)}</span>
              <span className="text-text-muted">RSI21</span><span className="font-mono text-text-primary">{selected.rsi21.toFixed(2)}</span>
              <span className="text-text-muted">EMA9 / WMA45</span><span className="font-mono text-text-primary">{selected.rsi_ema9.toFixed(2)} / {selected.rsi_wma45.toFixed(2)}</span>
              <span className="text-text-muted">RSI spread</span><span className="font-mono text-text-primary">{selected.rsi_spread.toFixed(2)}</span>
              <span className="text-text-muted">H4 close / EMA21</span><span className="font-mono text-text-primary">{price(selected.h4_close_price)} / {price(selected.h4_price_ema21)}</span>
              <span className="text-text-muted">Decision</span><span className="font-mono text-[10px] text-accent-main break-all">{selected.decision_reason}</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export function SignalReviewLab() {
  const selected = useSignalReviewStore((state) => state.selected);
  const initialize = useSignalReviewStore((state) => state.initialize);
  const total = useSignalReviewStore((state) => state.total);
  const runs = useSignalReviewStore((state) => state.runs);
  const latestRun = runs.find((run) => run.status === "completed") ?? runs[0];

  useEffect(() => {
    void initialize();
  }, [initialize]);

  if (selected) return <SignalDetail />;
  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
      <header>
        <div className="flex items-center gap-3"><CircleAlert size={22} className="text-accent-main" /><h1 className="text-xl font-semibold text-text-primary">BTC Signal Review Lab</h1></div>
        <p className="mt-1 text-sm text-text-secondary">Work through one replay dataset at a time, set optional TP/SL first, then label chart quality and inspect the future outcome.</p>
      </header>
      <ReplayLauncher />
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
        <span>{total} stored signals in the current view</span>
        {latestRun && <span>Latest replay: {displayDate(latestRun.created_at)} · {latestRun.signal_count} signals · {latestRun.status}</span>}
      </div>
      <SignalList />
    </div>
  );
}
