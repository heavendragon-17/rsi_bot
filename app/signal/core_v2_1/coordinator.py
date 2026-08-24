"""Restart-safe Core V2.1 signal-only coordinator."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Protocol, TypeVar

import structlog

from app.signal.core_v2_1.buffer import (
    BundleNotReady,
    ClosedCandleBuffer,
    MarketDataIntegrityError,
    PointInTimeBundleBuilder,
)
from app.signal.core_v2_1.formatter import format_core_v2_1_event
from app.signal.core_v2_1.market_data import CompositeMarketDataRouter
from app.signal.core_v2_1.models import (
    AdvisoryEvent,
    AsOfBundle,
    ClosedCandle,
    MarketKey,
    MarketPlan,
    MarketSeries,
    ensure_utc,
    timeframe_delta,
)
from app.signal.core_v2_1.state_store import (
    CommitStatus,
    CoreV21StateStore,
    TransitionCommit,
)
from app.trading.strategy.core_v2_1.feature_anchor import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    assert_feature_anchor_available,
    first_fully_covered_close,
)

logger = structlog.get_logger(__name__)

StateT = TypeVar("StateT")


@dataclass(frozen=True)
class RuntimeEvaluation(Generic[StateT]):
    """Evaluator-neutral transition persisted by the coordinator."""

    next_state: StateT
    decision_kind: str
    event: AdvisoryEvent | None = None
    decision_payload: Mapping[str, Any] = field(default_factory=dict)


class RuntimeEvaluator(Protocol[StateT]):
    """Adapter contract implemented for the pure Core V2.1 evaluator."""

    def initial_state(self) -> StateT: ...

    def evaluate(
        self,
        bundle: AsOfBundle,
        strategy_symbol: str,
        state: StateT,
    ) -> RuntimeEvaluation[StateT]: ...

    def dump_state(self, state: StateT) -> Mapping[str, Any]: ...

    def load_state(self, payload: Mapping[str, Any]) -> StateT: ...


@dataclass(frozen=True)
class ProcessReport:
    trigger_key: MarketKey
    considered: int = 0
    evaluated: int = 0
    events_committed: int = 0
    duplicate_commits: int = 0
    blocked_reason: str | None = None


@dataclass(frozen=True)
class BootstrapStatus:
    """Readiness evidence returned before any live candle is accepted."""

    ready: bool
    reports: tuple[ProcessReport, ...]
    missing_or_blocked: tuple[str, ...] = ()

    def __iter__(self):
        return iter(self.reports)

    def __getitem__(self, index: int) -> ProcessReport:
        return self.reports[index]


class CoreV21SignalCoordinator(Generic[StateT]):
    """Drive one pure evaluator through point-in-time M15 closes.

    New installations replay available history silently to initialize the
    state machine.  A restart with an existing cursor replays every missed M15
    close chronologically and enqueues its advisories.  No method in this class
    has access to an exchange order API.
    """

    def __init__(
        self,
        *,
        strategy_version: str,
        market_plan: MarketPlan,
        buffer: ClosedCandleBuffer,
        store: CoreV21StateStore,
        evaluator: RuntimeEvaluator[StateT],
        topic_by_symbol: Mapping[str, int | None] | None = None,
    ) -> None:
        strategy_version = strategy_version.strip()
        if not strategy_version:
            raise ValueError("strategy_version cannot be blank")
        self._strategy_version = strategy_version
        self._plan = market_plan
        self._buffer = buffer
        self._builder = PointInTimeBundleBuilder(buffer)
        self._store = store
        self._evaluator = evaluator
        self._topics = {
            key.strip().upper().replace("/", ""): value
            for key, value in (topic_by_symbol or {}).items()
        }
        self._locks = {key: threading.RLock() for key in market_plan.trigger_keys}
        self._bootstrapped = False
        self._prepared_evaluator_ready = False
        self._bootstrap_suppress_through: dict[MarketKey, datetime | None] | None = None

    @property
    def market_plan(self) -> MarketPlan:
        return self._plan

    @property
    def is_ready(self) -> bool:
        return self._bootstrapped

    def build_as_of_bundle(
        self,
        trigger_key: MarketKey,
        as_of: datetime,
    ) -> AsOfBundle:
        """Expose the immutable evaluator input boundary for parity audits."""

        return self._builder.build(
            self._plan.for_trigger(trigger_key),
            ensure_utc(as_of, field_name="as_of"),
        )

    def hydrate(
        self,
        router: CompositeMarketDataRouter,
        *,
        through: datetime,
        safety_candles: int = 4,
    ) -> int:
        """Fetch enough public history for every unique dependency.

        The source itself excludes forming candles.  Hydration only populates
        the buffer; call :meth:`bootstrap` afterwards to process it.
        """

        if safety_candles < 0:
            raise ValueError("safety_candles cannot be negative")
        through_utc = ensure_utc(through, field_name="through")
        assert_feature_anchor_available(through_utc)
        cached_by_key: dict[MarketKey, tuple[ClosedCandle, ...]] = {}
        for key in self._plan.all_keys:
            cached = self._store.load_market_candles(key)
            expected_anchor_close = first_fully_covered_close(key.timeframe)
            if cached and cached[0].close_time != expected_anchor_close:
                raise MarketDataIntegrityError(
                    f"Feature anchor mismatch for {key.storage_id}: expected first "
                    f"close {expected_anchor_close.isoformat()}, got "
                    f"{cached[0].close_time.isoformat()}; explicit re-anchor migration "
                    "required"
                )
            if cached:
                _assert_exact_candle_range(
                    key,
                    cached,
                    expected_start=expected_anchor_close,
                    expected_end=cached[-1].close_time,
                    label="persisted feature history",
                )
            if cached and cached[-1].close_time > through_utc:
                raise MarketDataIntegrityError(
                    f"Persisted candle cache for {key.storage_id} extends beyond "
                    f"startup time {through_utc.isoformat()}"
                )
            cached_by_key[key] = cached
            self._buffer.add_many(cached)

        start_by_key: dict[MarketKey, datetime] = {}
        requires_existing_anchor: set[MarketKey] = set()
        for trigger_plan in self._plan.triggers:
            cursor = self._load_cursor(trigger_plan.trigger)
            first_anchor = (
                cursor.last_processed_at
                + timeframe_delta(trigger_plan.trigger.timeframe)
                if cursor is not None
                else through_utc
            )
            for requirement in trigger_plan.requirements:
                if cursor is not None:
                    requires_existing_anchor.add(requirement.key)
                duration = timeframe_delta(requirement.key.timeframe)
                candidate_start = first_anchor - duration * (
                    requirement.minimum_candles + safety_candles
                )
                if cursor is None:
                    # Every venue/timeframe starts from the same locked source
                    # window.  Slower native buckets that straddle the M15
                    # open anchor are excluded by first_fully_covered_close().
                    candidate_start = first_fully_covered_close(
                        requirement.key.timeframe
                    )
                previous = start_by_key.get(requirement.key)
                if previous is None or candidate_start < previous:
                    start_by_key[requirement.key] = candidate_start
        added = 0
        for key in sorted(start_by_key):
            cached = cached_by_key[key]
            if cached:
                # Inclusive overlap verifies that the venue has not rewritten
                # the cache boundary, then appends every missed close.
                fetch_start = cached[-1].close_time
            else:
                if key in requires_existing_anchor:
                    raise MarketDataIntegrityError(
                        f"Stable indicator anchor is missing for {key.storage_id}; "
                        "refusing restart with a moving seed"
                    )
                fetch_start = start_by_key[key]
            candles = router.fetch_closed(key, fetch_start, through_utc)
            expected_latest = _floor_utc_close(through_utc, key.timeframe)
            _assert_exact_candle_range(
                key,
                candles,
                expected_start=fetch_start,
                expected_end=expected_latest,
                label="venue hydration response",
            )
            self._store.persist_market_candles(candles)
            added += self._buffer.add_many(candles)

            stored = self._store.load_market_candles(key)
            if not stored or stored[-1].close_time != expected_latest:
                actual_latest = stored[-1].close_time.isoformat() if stored else "no candles"
                raise MarketDataIntegrityError(
                    f"Startup history tail is incomplete for {key.storage_id}: expected "
                    f"latest close {expected_latest.isoformat()}, got {actual_latest}"
                )
        return added

    def bootstrap(self, *, through: datetime | None = None) -> BootstrapStatus:
        """Initialize or recover all symbols before live polling starts.

        If no persisted cursor exists, all historical evaluator events are
        recorded as suppressed and no Telegram outbox rows are created.  If a
        cursor does exist, missed candles are ordinary restart catch-up and
        their events remain deliverable.
        """

        through_utc = ensure_utc(through, field_name="through") if through else None
        if self._bootstrap_suppress_through is None:
            suppress_through: dict[MarketKey, datetime | None] = {}
            for trigger in self._plan.triggers:
                existing = self._load_cursor(trigger.trigger)
                latest = self._buffer.latest_close(trigger.trigger)
                proposed_watermark: datetime | None
                if existing is not None or latest is None:
                    proposed_watermark = None
                elif through_utc is None:
                    proposed_watermark = latest
                else:
                    proposed_watermark = min(latest, through_utc)
                bootstrap_record = self._store.ensure_bootstrap_record(
                    self._strategy_version,
                    trigger.trigger,
                    suppression_watermark=proposed_watermark,
                    completed=existing is not None,
                )
                suppress_through[trigger.trigger] = (
                    None
                    if bootstrap_record.completed
                    else bootstrap_record.suppression_watermark
                )
            self._bootstrap_suppress_through = suppress_through

        self._prepared_evaluator_ready = self._prepare_evaluator_history(through_utc)

        reports = tuple(
            self.process_available(
                trigger.trigger,
                through=through_utc,
                suppress_through=self._bootstrap_suppress_through[trigger.trigger],
            )
            for trigger in self._plan.triggers
        )
        problems: list[str] = []
        for report in reports:
            if report.blocked_reason:
                problems.append(f"{report.trigger_key.storage_id}: {report.blocked_reason}")
                continue
            cursor = self._load_cursor(report.trigger_key)
            watermark = self._bootstrap_suppress_through[report.trigger_key]
            if cursor is None:
                problems.append(f"{report.trigger_key.storage_id}: no durable cursor")
                continue
            if watermark is not None and cursor.last_processed_at < watermark:
                problems.append(
                    f"{report.trigger_key.storage_id}: cursor "
                    f"{cursor.last_processed_at.isoformat()} has not reached bootstrap "
                    f"watermark {watermark.isoformat()}"
                )
                continue
            latest = self._buffer.latest_close(report.trigger_key)
            if latest is None:
                problems.append(f"{report.trigger_key.storage_id}: no trigger history loaded")
                continue
            if latest != cursor.last_processed_at:
                problems.append(
                    f"{report.trigger_key.storage_id}: loaded trigger watermark "
                    f"{latest.isoformat()} differs from cursor "
                    f"{cursor.last_processed_at.isoformat()}"
                )
                continue
            try:
                prepared_check = getattr(
                    self._evaluator,
                    "assert_prepared_ready",
                    None,
                )
                if self._prepared_evaluator_ready and callable(prepared_check):
                    prepared_check(self._plan.for_trigger(report.trigger_key), latest)
                else:
                    self._builder.build(self._plan.for_trigger(report.trigger_key), latest)
            except (BundleNotReady, MarketDataIntegrityError) as exc:
                problems.append(f"{report.trigger_key.storage_id}: {exc}")
        self._bootstrapped = not problems
        if self._bootstrapped:
            for trigger in self._plan.triggers:
                self._store.mark_bootstrap_complete(
                    self._strategy_version,
                    trigger.trigger,
                )
                self._bootstrap_suppress_through[trigger.trigger] = None
        return BootstrapStatus(
            ready=self._bootstrapped,
            reports=reports,
            missing_or_blocked=tuple(problems),
        )

    def on_closed_candle(self, candle: ClosedCandle) -> tuple[ProcessReport, ...]:
        """Ingest a live close and retry every affected pending trigger."""

        if not self._bootstrapped:
            raise RuntimeError("bootstrap must complete before live candles are accepted")
        self._store.persist_market_candles((candle,))
        self._buffer.add(candle)
        if self._prepared_evaluator_ready:
            update_history = getattr(self._evaluator, "update_history", None)
            if not callable(update_history):
                raise RuntimeError("prepared evaluator cannot accept live history")
            update_history(candle)
        # Dependencies are shared, and a co-closing H1/H4 may make multiple
        # pending M15 anchors ready.  Retrying all 25 triggers is cheap at a
        # 15-minute cadence and prevents callback-order data loss.
        return tuple(
            self.process_available(trigger.trigger, silent_if_new=False)
            for trigger in self._plan.triggers
            if candle.key in {requirement.key for requirement in trigger.requirements}
        )

    def process_available(
        self,
        trigger_key: MarketKey,
        *,
        through: datetime | None = None,
        silent_if_new: bool = False,
        suppress_through: datetime | None = None,
    ) -> ProcessReport:
        """Evaluate all ready trigger closes after the durable cursor."""

        trigger_plan = self._plan.for_trigger(trigger_key)
        through_utc = ensure_utc(through, field_name="through") if through else None
        suppress_until = (
            ensure_utc(suppress_through, field_name="suppress_through")
            if suppress_through is not None
            else None
        )
        with self._locks[trigger_key]:
            cursor = self._load_cursor(trigger_key)
            new_installation = cursor is None
            state = (
                self._evaluator.initial_state()
                if cursor is None
                else self._evaluator.load_state(cursor.state_payload)
            )
            last_processed = cursor.last_processed_at if cursor is not None else None
            candidates = self._buffer.close_times_after(
                trigger_key,
                last_processed,
                through=through_utc,
            )
            considered = 0
            evaluated = 0
            events = 0
            duplicates = 0
            pending: list[TransitionCommit] = []
            expected_before_batch = last_processed
            blocked_reason: str | None = None

            if last_processed is not None and candidates:
                expected_next = last_processed + timeframe_delta(trigger_key.timeframe)
                if candidates[0] != expected_next:
                    return ProcessReport(
                        trigger_key=trigger_key,
                        considered=0,
                        evaluated=0,
                        events_committed=0,
                        duplicate_commits=0,
                        blocked_reason=(
                            f"chronological catch-up gap: expected "
                            f"{expected_next.isoformat()}, got {candidates[0].isoformat()}"
                        ),
                    )

            for closed_at in candidates:
                considered += 1
                try:
                    evaluate_prepared = getattr(
                        self._evaluator,
                        "evaluate_prepared",
                        None,
                    )
                    if self._prepared_evaluator_ready and callable(evaluate_prepared):
                        result = evaluate_prepared(trigger_plan, closed_at, state)
                    else:
                        bundle = self._builder.build(trigger_plan, closed_at)
                        result = self._evaluator.evaluate(
                            bundle,
                            trigger_plan.strategy_symbol,
                            state,
                        )
                except BundleNotReady as exc:
                    if new_installation and last_processed is None:
                        # Warm-up closes before the minimum lookback are not
                        # decisions and do not belong in the durable cursor.
                        continue
                    blocked_reason = str(exc)
                    break
                except MarketDataIntegrityError as exc:
                    logger.error(
                        "core_v2_evaluation_fail_closed",
                        market=trigger_key.storage_id,
                        closed_at=closed_at.isoformat(),
                        reason=str(exc),
                    )
                    blocked_reason = str(exc)
                    break
                if result.event is not None:
                    if result.event.symbol != trigger_plan.strategy_symbol:
                        raise ValueError("evaluator event symbol does not match trigger plan")
                    if result.event.venue is not trigger_key.venue:
                        raise ValueError("evaluator event venue does not match trigger plan")
                suppress = bool(
                    (silent_if_new and new_installation)
                    or (suppress_until is not None and closed_at <= suppress_until)
                )
                message = (
                    format_core_v2_1_event(result.event)
                    if result.event is not None
                    else None
                )
                pending.append(
                    TransitionCommit(
                        processed_at=closed_at,
                        state_payload=self._evaluator.dump_state(result.next_state),
                        decision_kind=result.decision_kind,
                        decision_payload=result.decision_payload,
                        event=result.event,
                        message=message,
                        topic_id=self._topics.get(trigger_plan.strategy_symbol),
                        suppress_notification=suppress,
                    )
                )
                state = result.next_state
                last_processed = closed_at

            if pending:
                statuses = self._store.commit_transition_batch(
                    strategy_id=self._strategy_version,
                    trigger_key=trigger_key,
                    expected_last_processed_at=expected_before_batch,
                    transitions=pending,
                )
                committed = sum(status is CommitStatus.COMMITTED for status in statuses)
                already_processed = sum(
                    status is CommitStatus.ALREADY_PROCESSED for status in statuses
                )
                if committed and already_processed:
                    raise RuntimeError("transition batch returned mixed commit statuses")
                if already_processed:
                    duplicates += already_processed
                    refreshed = self._load_cursor(trigger_key)
                    if refreshed is None:
                        raise RuntimeError("cursor disappeared after duplicate commit")
                else:
                    evaluated += committed
                    events += sum(
                        int(item.event is not None)
                        for item, status in zip(pending, statuses, strict=True)
                        if status is CommitStatus.COMMITTED
                    )

            return ProcessReport(
                trigger_key=trigger_key,
                considered=considered,
                evaluated=evaluated,
                events_committed=events,
                duplicate_commits=duplicates,
                blocked_reason=blocked_reason,
            )

    def _prepare_evaluator_history(self, through: datetime | None) -> bool:
        prepare_history = getattr(self._evaluator, "prepare_history", None)
        evaluate_prepared = getattr(self._evaluator, "evaluate_prepared", None)
        if not callable(prepare_history) or not callable(evaluate_prepared):
            return False
        histories: list[MarketSeries] = []
        for key in sorted(self._plan.all_keys):
            latest = self._buffer.latest_close(key)
            if latest is None:
                return False
            boundary = min(latest, through) if through is not None else latest
            try:
                histories.append(
                    self._buffer.series_as_of(
                        key,
                        boundary,
                        minimum_candles=1,
                    )
                )
            except BundleNotReady:
                return False
        prepare_history(tuple(histories))
        return True

    def _load_cursor(self, trigger_key: MarketKey):
        cursor = self._store.load_cursor(self._strategy_version, trigger_key)
        if cursor is not None and (
            cursor.feature_anchor_version != FEATURE_ANCHOR_VERSION
            or cursor.feature_anchor_open != FEATURE_ANCHOR_M15_OPEN
        ):
            raise MarketDataIntegrityError(
                f"Persisted feature anchor for {trigger_key.storage_id} does not match "
                f"{FEATURE_ANCHOR_VERSION}; explicit strategy-version/re-anchor "
                "migration required"
            )
        return cursor


def _floor_utc_close(value: datetime, timeframe: str) -> datetime:
    boundary = ensure_utc(value, field_name="boundary")
    seconds = int(timeframe_delta(timeframe).total_seconds())
    return datetime.fromtimestamp(
        (int(boundary.timestamp()) // seconds) * seconds,
        tz=boundary.tzinfo,
    )


def _assert_exact_candle_range(
    key: MarketKey,
    candles: tuple[ClosedCandle, ...],
    *,
    expected_start: datetime,
    expected_end: datetime,
    label: str,
) -> None:
    start = ensure_utc(expected_start, field_name="expected_start")
    end = ensure_utc(expected_end, field_name="expected_end")
    if end < start:
        raise MarketDataIntegrityError(
            f"{label} for {key.storage_id} cannot reach its first complete "
            f"anchor close {start.isoformat()} by {end.isoformat()}"
        )
    duration = timeframe_delta(key.timeframe)
    expected_count = int((end - start) / duration) + 1
    if len(candles) != expected_count:
        raise MarketDataIntegrityError(
            f"{label} is incomplete for {key.storage_id}: expected "
            f"{expected_count} candles from {start.isoformat()} through "
            f"{end.isoformat()}, got {len(candles)}"
        )
    for index, candle in enumerate(candles):
        expected_close = start + duration * index
        if candle.key != key or candle.close_time != expected_close:
            actual = (
                candle.close_time.isoformat()
                if candle.key == key
                else candle.key.storage_id
            )
            raise MarketDataIntegrityError(
                f"{label} has a cadence/routing gap for {key.storage_id} at "
                f"index {index}: expected {expected_close.isoformat()}, got {actual}"
            )
