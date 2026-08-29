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
  Play,
  RefreshCw,
  Save,
} from "lucide-react";
import { SignalChart } from "./SignalChart";
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

function ReviewPanel() {
  const selected = useSignalReviewStore((state) => state.selected);
  const saveReview = useSignalReviewStore((state) => state.saveReview);
  const reviewSaveState = useSignalReviewStore((state) => state.reviewSaveState);
  const [note, setNote] = useState("");
  const review = selected?.review;
  const futureUnlocked = review?.quality !== "UNREVIEWED";

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

  const qualityOptions: Array<[string, string, string]> = [
    ["GOOD", "Good", "emerald"],
    ["BAD", "Bad", "rose"],
    ["UNCERTAIN", "Uncertain", "amber"],
  ];
  const outcomes: Array<[string, string]> = [["WIN", "WIN"], ["LOSS", "LOSS"], ["SKIP", "SKIP"]];

  return (
    <section className="rounded-xl border border-border-main bg-bg-primary/50 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Save size={16} className="text-accent-main" />
        <h3 className="font-semibold text-text-primary">Human review</h3>
      </div>
      <div>
        <p className="mb-2 text-xs text-text-muted">Chart quality</p>
        <div className="flex flex-wrap gap-2">
          {qualityOptions.map(([value, label, color]) => (
            <button
              type="button"
              key={value}
              disabled={reviewSaveState === "saving"}
              onClick={() => void saveReview({ quality: value } as SignalReviewUpdate)}
              className={`rounded-md border px-3 py-2 text-xs font-medium disabled:cursor-wait disabled:opacity-50 ${qualityClasses(review.quality === value, color)}`}
            >{label}</button>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs text-text-muted">Your market outcome</p>
        <div className="flex flex-wrap gap-2">
          {outcomes.map(([value, label]) => (
            <button
              type="button"
              key={value}
              disabled={!futureUnlocked || reviewSaveState === "saving"}
              onClick={() => void saveReview({ human_outcome: value } as SignalReviewUpdate)}
              className={`rounded-md border px-3 py-2 text-xs font-medium ${review.human_outcome === value ? "border-violet-400/60 bg-violet-400/20 text-violet-200" : "border-border-main bg-bg-elevated/40 text-text-secondary"} disabled:cursor-not-allowed disabled:opacity-40`}
            >{label}</button>
          ))}
        </div>
        {!futureUnlocked && <p className="mt-2 text-[11px] text-amber-300">Choose a quality label before reviewing the future outcome.</p>}
      </div>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={4}
        placeholder="Why is this chart good or bad? What did you notice?"
        className="w-full resize-y rounded-md border border-border-main bg-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-main focus:outline-none"
      />
      <p className={`text-[11px] ${reviewSaveState === "error" ? "text-danger" : "text-text-muted"}`}>
        {reviewSaveState === "saving" ? "Saving review…" : reviewSaveState === "saved" ? "Review saved" : reviewSaveState === "error" ? "Review could not be saved" : "Notes save automatically"}
        {review.updated_at ? ` · Last updated ${displayDate(review.updated_at)}` : ""}
      </p>
    </section>
  );
}

function SignalDetail() {
  const selected = useSignalReviewStore((state) => state.selected);
  const chart = useSignalReviewStore((state) => state.chart);
  const isLoading = useSignalReviewStore((state) => state.isLoadingDetail);
  const clearSelection = useSignalReviewStore((state) => state.clearSelection);
  const loadAdjacentSignal = useSignalReviewStore((state) => state.loadAdjacentSignal);
  const loadMoreChart = useSignalReviewStore((state) => state.loadMoreChart);
  if (!selected) return null;
  const currentMetric = selected.forward_metrics;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={clearSelection} className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
          <ArrowLeft size={16} /> Back to signals
        </button>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void loadAdjacentSignal(-1)} className="inline-flex items-center gap-1 rounded-md border border-border-main px-2 py-1 text-xs text-text-secondary hover:border-accent-main hover:text-text-primary">
            <ChevronLeft size={14} /> Newer
          </button>
          <span className="font-mono text-xs text-text-muted">#{String(selected.sequence).padStart(4, "0")} · {selected.timeframe.toUpperCase()}</span>
          <button type="button" onClick={() => void loadAdjacentSignal(1)} className="inline-flex items-center gap-1 rounded-md border border-border-main px-2 py-1 text-xs text-text-secondary hover:border-accent-main hover:text-text-primary">
            Older <ChevronRight size={14} />
          </button>
        </div>
      </div>
      {isLoading && <div className="text-sm text-text-muted">Loading signal…</div>}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)] gap-4">
        <div className="space-y-4">
          <SignalChart chart={chart ?? { signal_id: selected.id, timeframe: selected.timeframe, candles: [], available_start: null, available_end: null, requested_start: null, requested_end: null, has_before: false, has_after: false, future_allowed: false, warning: "Loading chart…" }} triggerClosePrice={Number(selected.trigger_close_price)} onLoadMore={loadMoreChart} />
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
        <div className="space-y-4">
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
          <ReviewPanel />
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
        <p className="mt-1 text-sm text-text-secondary">Work through one replay dataset at a time, label chart quality first, then inspect the future outcome.</p>
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
