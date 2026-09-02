"""SQLite persistence for Core V2.1 state, dedupe, and notification outbox."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

from app.signal.core_v2_1.models import (
    AdvisoryEvent,
    ClosedCandle,
    MarketKey,
    ensure_utc,
    timeframe_delta,
)
from app.trading.strategy.core_v2_1.feature_anchor import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
)


class ConcurrentTransitionError(RuntimeError):
    """The persisted cursor changed after an evaluation started."""


class CandleCacheConflictError(RuntimeError):
    """A venue rewrote a candle already used by the deterministic runtime."""


class FeatureAnchorMigrationRequired(RuntimeError):
    """Persisted runtime state predates the locked feature-anchor contract."""


class OutboxLeaseLostError(RuntimeError):
    """An outbox row was reclaimed after this worker's lease expired."""


class CommitStatus(StrEnum):
    COMMITTED = "committed"
    ALREADY_PROCESSED = "already_processed"


@dataclass(frozen=True)
class RuntimeCursor:
    strategy_id: str
    trigger_key: MarketKey
    state_payload: dict[str, Any]
    last_processed_at: datetime
    feature_anchor_version: str
    feature_anchor_open: datetime


@dataclass(frozen=True)
class OutboxItem:
    outbox_id: int
    event_id: str
    topic_id: int | None
    message: str
    attempts: int
    claim_token: str


@dataclass(frozen=True)
class BootstrapRecord:
    suppression_watermark: datetime | None
    completed: bool


@dataclass(frozen=True)
class TransitionCommit:
    """One chronological transition in an atomic per-symbol commit batch."""

    processed_at: datetime
    state_payload: Mapping[str, Any]
    decision_kind: str
    decision_payload: Mapping[str, Any] | None = None
    event: AdvisoryEvent | None = None
    message: str | None = None
    topic_id: int | None = None
    suppress_notification: bool = False


class CoreV21StateStore:
    """Restart-safe single-file store.

    The state update, transition audit row, deduplicated advisory event, and
    outbox enqueue happen inside one ``BEGIN IMMEDIATE`` transaction.  A crash
    can therefore leave either the whole logical transition or none of it.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def load_cursor(self, strategy_id: str, trigger_key: MarketKey) -> RuntimeCursor | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json, last_processed_at,
                       feature_anchor_version, feature_anchor_open
                FROM core_v2_runtime_state
                WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                """,
                _identity(strategy_id, trigger_key),
            ).fetchone()
        if row is None:
            return None
        if row["feature_anchor_version"] is None or row["feature_anchor_open"] is None:
            raise FeatureAnchorMigrationRequired(
                f"Persisted state for {trigger_key.storage_id} has no feature anchor; "
                "an explicit strategy-version/re-anchor migration is required"
            )
        return RuntimeCursor(
            strategy_id=strategy_id,
            trigger_key=trigger_key,
            state_payload=json.loads(row["state_json"]),
            last_processed_at=_parse_timestamp(row["last_processed_at"]),
            feature_anchor_version=str(row["feature_anchor_version"]),
            feature_anchor_open=_parse_timestamp(row["feature_anchor_open"]),
        )

    def persist_market_candles(
        self,
        candles: tuple[ClosedCandle, ...] | list[ClosedCandle],
    ) -> int:
        """Persist immutable candle history and reject exchange rewrites."""

        if not candles:
            return 0
        key = candles[0].key
        by_close: dict[datetime, ClosedCandle] = {}
        for candle in candles:
            if candle.key != key:
                raise ValueError("persist_market_candles accepts one MarketKey per call")
            existing = by_close.get(candle.close_time)
            if existing is not None and existing != candle:
                raise CandleCacheConflictError(
                    f"Conflicting input candle for {key.storage_id} at {candle.close_time}"
                )
            by_close[candle.close_time] = candle
        ordered = tuple(by_close[closed_at] for closed_at in sorted(by_close))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            changes_before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO core_v2_market_candles (
                    venue, instrument, timeframe, open_time, close_time,
                    open, high, low, close, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        key.venue.value,
                        key.instrument,
                        key.timeframe,
                        candle.open_time.isoformat(),
                        candle.close_time.isoformat(),
                        str(candle.open),
                        str(candle.high),
                        str(candle.low),
                        str(candle.close),
                        str(candle.volume),
                    )
                    for candle in ordered
                ],
            )
            inserted = connection.total_changes - changes_before
            rows = connection.execute(
                """
                SELECT open_time, close_time, open, high, low, close, volume
                FROM core_v2_market_candles
                WHERE venue = ? AND instrument = ? AND timeframe = ?
                  AND close_time >= ? AND close_time <= ?
                ORDER BY close_time
                """,
                (
                    key.venue.value,
                    key.instrument,
                    key.timeframe,
                    ordered[0].close_time.isoformat(),
                    ordered[-1].close_time.isoformat(),
                ),
            ).fetchall()
            persisted = {
                _parse_timestamp(row["close_time"]): _row_to_closed_candle(key, row)
                for row in rows
            }
            for candle in ordered:
                if persisted.get(candle.close_time) != candle:
                    raise CandleCacheConflictError(
                        f"Persisted candle conflict for {key.storage_id} at "
                        f"{candle.close_time.isoformat()}"
                    )
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load_market_candles(self, key: MarketKey) -> tuple[ClosedCandle, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT open_time, close_time, open, high, low, close, volume
                FROM core_v2_market_candles
                WHERE venue = ? AND instrument = ? AND timeframe = ?
                ORDER BY close_time
                """,
                (key.venue.value, key.instrument, key.timeframe),
            ).fetchall()
        return tuple(_row_to_closed_candle(key, row) for row in rows)

    def ensure_bootstrap_record(
        self,
        strategy_id: str,
        trigger_key: MarketKey,
        *,
        suppression_watermark: datetime | None,
        completed: bool,
    ) -> BootstrapRecord:
        """Create the durable first-install suppression marker once.

        An initially empty bootstrap may have a null watermark.  It can be set
        exactly once when history first arrives, but a non-null watermark is
        never extended by later retries.
        """

        watermark = (
            ensure_utc(suppression_watermark, field_name="suppression_watermark")
            if suppression_watermark is not None
            else None
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT suppression_watermark, completed
                FROM core_v2_bootstrap_state
                WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                """,
                _identity(strategy_id, trigger_key),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO core_v2_bootstrap_state (
                        strategy_id, venue, instrument, timeframe,
                        suppression_watermark, completed, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        *_identity(strategy_id, trigger_key),
                        watermark.isoformat() if watermark is not None else None,
                        int(completed),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                record = BootstrapRecord(watermark, completed)
            else:
                stored_watermark = (
                    _parse_timestamp(row["suppression_watermark"])
                    if row["suppression_watermark"] is not None
                    else None
                )
                stored_completed = bool(row["completed"])
                if stored_watermark is None and watermark is not None and not stored_completed:
                    connection.execute(
                        """
                        UPDATE core_v2_bootstrap_state
                        SET suppression_watermark = ?, updated_at = ?
                        WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                        """,
                        (
                            watermark.isoformat(),
                            datetime.now(UTC).isoformat(),
                            *_identity(strategy_id, trigger_key),
                        ),
                    )
                    stored_watermark = watermark
                record = BootstrapRecord(stored_watermark, stored_completed)
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_bootstrap_complete(self, strategy_id: str, trigger_key: MarketKey) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE core_v2_bootstrap_state
                SET completed = 1, updated_at = ?
                WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    *_identity(strategy_id, trigger_key),
                ),
            ).rowcount
            if updated != 1:
                raise KeyError(f"No bootstrap record for {trigger_key.storage_id}")

    def commit_transition(
        self,
        *,
        strategy_id: str,
        trigger_key: MarketKey,
        processed_at: datetime,
        expected_last_processed_at: datetime | None,
        state_payload: Mapping[str, Any],
        decision_kind: str,
        decision_payload: Mapping[str, Any] | None = None,
        event: AdvisoryEvent | None = None,
        message: str | None = None,
        topic_id: int | None = None,
        suppress_notification: bool = False,
        feature_anchor_version: str = FEATURE_ANCHOR_VERSION,
        feature_anchor_open: datetime = FEATURE_ANCHOR_M15_OPEN,
    ) -> CommitStatus:
        statuses = self.commit_transition_batch(
            strategy_id=strategy_id,
            trigger_key=trigger_key,
            expected_last_processed_at=expected_last_processed_at,
            transitions=(
                TransitionCommit(
                    processed_at=processed_at,
                    state_payload=state_payload,
                    decision_kind=decision_kind,
                    decision_payload=decision_payload,
                    event=event,
                    message=message,
                    topic_id=topic_id,
                    suppress_notification=suppress_notification,
                ),
            ),
            feature_anchor_version=feature_anchor_version,
            feature_anchor_open=feature_anchor_open,
        )
        return statuses[0]

    def commit_transition_batch(
        self,
        *,
        strategy_id: str,
        trigger_key: MarketKey,
        expected_last_processed_at: datetime | None,
        transitions: tuple[TransitionCommit, ...] | list[TransitionCommit],
        feature_anchor_version: str = FEATURE_ANCHOR_VERSION,
        feature_anchor_open: datetime = FEATURE_ANCHOR_M15_OPEN,
    ) -> tuple[CommitStatus, ...]:
        """Commit a chronological replay segment in one crash-safe transaction.

        Every decision and advisory keeps its individual immutable audit row;
        only transaction setup and the replaceable current-state write are
        coalesced.  A crash therefore exposes either the complete segment and
        its final cursor or none of it.
        """

        if not transitions:
            return ()
        expected = (
            ensure_utc(expected_last_processed_at, field_name="expected_last_processed_at")
            if expected_last_processed_at is not None
            else None
        )
        anchor_open = ensure_utc(feature_anchor_open, field_name="feature_anchor_open")
        if not feature_anchor_version.strip():
            raise ValueError("feature_anchor_version cannot be blank")
        identity = _identity(strategy_id, trigger_key)
        duration = timeframe_delta(trigger_key.timeframe)
        normalized: list[tuple[TransitionCommit, datetime, str]] = []
        previous: datetime | None = None
        for transition in transitions:
            processed = ensure_utc(transition.processed_at, field_name="processed_at")
            decision_kind = transition.decision_kind.strip()
            if not decision_kind:
                raise ValueError("decision_kind cannot be blank")
            if previous is not None and processed != previous + duration:
                raise ValueError(
                    f"transition batch for {trigger_key.storage_id} is not contiguous: "
                    f"expected {(previous + duration).isoformat()}, got "
                    f"{processed.isoformat()}"
                )
            event = transition.event
            if event is not None and event.closed_at != processed:
                raise ValueError("event.closed_at must match processed_at")
            if event is not None and event.venue is not trigger_key.venue:
                raise ValueError("event venue must match trigger market venue")
            if (
                event is not None
                and not transition.suppress_notification
                and not transition.message
            ):
                raise ValueError("a non-suppressed event requires a rendered message")
            normalized.append((transition, processed, decision_kind))
            previous = processed

        final_processed = normalized[-1][1]
        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                """
                SELECT last_processed_at, feature_anchor_version, feature_anchor_open
                FROM core_v2_runtime_state
                WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                """,
                identity,
            ).fetchone()
            current = (
                _parse_timestamp(current_row["last_processed_at"])
                if current_row is not None
                else None
            )
            if current_row is not None and (
                current_row["feature_anchor_version"] != feature_anchor_version
                or current_row["feature_anchor_open"] is None
                or _parse_timestamp(current_row["feature_anchor_open"]) != anchor_open
            ):
                raise ConcurrentTransitionError(
                    f"Feature anchor mismatch for {trigger_key.storage_id}"
                )
            if current is not None and current >= final_processed:
                connection.rollback()
                return (CommitStatus.ALREADY_PROCESSED,) * len(normalized)
            if current != expected:
                raise ConcurrentTransitionError(
                    f"Cursor changed for {trigger_key.storage_id}: expected "
                    f"{expected}, found {current}"
                )

            now_iso = now.isoformat()
            anchor_open_iso = anchor_open.isoformat()
            transition_rows: list[tuple[Any, ...]] = []
            event_rows: list[
                tuple[TransitionCommit, datetime, AdvisoryEvent, str]
            ] = []
            for transition, processed, decision_kind in normalized:
                event = transition.event
                transition_id = _stable_id(
                    "transition",
                    strategy_id,
                    trigger_key.storage_id,
                    processed.isoformat(),
                )
                event_id = (
                    _stable_id(
                        "event",
                        strategy_id,
                        trigger_key.venue.value,
                        event.symbol,
                        processed.isoformat(),
                        event.event_type.value,
                    )
                    if event is not None
                    else None
                )
                transition_rows.append(
                    (
                        transition_id,
                        *identity,
                        processed.isoformat(),
                        decision_kind,
                        _json_dump(transition.decision_payload or {}),
                        event_id,
                        int(transition.suppress_notification),
                        feature_anchor_version,
                        anchor_open_iso,
                        now_iso,
                    )
                )
                if event is not None and event_id is not None:
                    event_rows.append((transition, processed, event, event_id))

            # ``executemany`` keeps the same all-or-nothing transaction while
            # avoiding one Python/SQLite boundary crossing per historical
            # decision during a 5,000-candle cold bootstrap.
            connection.executemany(
                """
                INSERT INTO core_v2_runtime_transitions (
                    transition_id, strategy_id, venue, instrument, timeframe,
                    processed_at, decision_kind, decision_json, event_id,
                    notification_suppressed, feature_anchor_version,
                    feature_anchor_open, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                transition_rows,
            )

            for transition, processed, event, event_id in event_rows:
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO core_v2_runtime_events (
                        event_id, strategy_id, strategy_symbol, venue,
                        instrument, timeframe, processed_at, event_type,
                        payload_json, notification_suppressed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        strategy_id,
                        event.symbol,
                        trigger_key.venue.value,
                        trigger_key.instrument,
                        trigger_key.timeframe,
                        processed.isoformat(),
                        event.event_type.value,
                        _json_dump(event.to_payload()),
                        int(transition.suppress_notification),
                        now_iso,
                    ),
                ).rowcount
                if inserted and not transition.suppress_notification:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO core_v2_notification_outbox (
                            event_id, topic_id, message, status, attempts,
                            next_attempt_at, created_at
                        ) VALUES (?, ?, ?, 'pending', 0, ?, ?)
                        """,
                        (
                            event_id,
                            transition.topic_id,
                            transition.message,
                            now_iso,
                            now_iso,
                        ),
                    )

            final = normalized[-1][0]
            connection.execute(
                """
                INSERT INTO core_v2_runtime_state (
                    strategy_id, venue, instrument, timeframe,
                    state_json, last_processed_at,
                    feature_anchor_version, feature_anchor_open, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id, venue, instrument, timeframe)
                DO UPDATE SET
                    state_json = excluded.state_json,
                    last_processed_at = excluded.last_processed_at,
                    feature_anchor_version = excluded.feature_anchor_version,
                    feature_anchor_open = excluded.feature_anchor_open,
                    updated_at = excluded.updated_at
                """,
                (
                    *identity,
                    _json_dump(final.state_payload),
                    final_processed.isoformat(),
                    feature_anchor_version,
                    anchor_open_iso,
                    now_iso,
                ),
            )
            connection.commit()
            return (CommitStatus.COMMITTED,) * len(normalized)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_due_outbox(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
        lease_seconds: float = 30.0,
    ) -> tuple[OutboxItem, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = ensure_utc(now or datetime.now(UTC), field_name="now")
        lease_until = current + timedelta(seconds=lease_seconds)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT outbox_id, event_id, topic_id, message, attempts
                FROM core_v2_notification_outbox
                WHERE (
                    status IN ('pending', 'retry') AND next_attempt_at <= ?
                ) OR (
                    status = 'inflight' AND locked_until <= ?
                )
                ORDER BY outbox_id
                LIMIT ?
                """,
                (current.isoformat(), current.isoformat(), limit),
            ).fetchall()
            claim_tokens: dict[int, str] = {}
            for row in rows:
                outbox_id = int(row["outbox_id"])
                claim_token = secrets.token_hex(16)
                connection.execute(
                    """
                    UPDATE core_v2_notification_outbox
                    SET status = 'inflight', locked_until = ?, claim_token = ?
                    WHERE outbox_id = ?
                    """,
                    (lease_until.isoformat(), claim_token, outbox_id),
                )
                claim_tokens[outbox_id] = claim_token
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return tuple(
            OutboxItem(
                outbox_id=int(row["outbox_id"]),
                event_id=str(row["event_id"]),
                topic_id=int(row["topic_id"]) if row["topic_id"] is not None else None,
                message=str(row["message"]),
                attempts=int(row["attempts"]),
                claim_token=claim_tokens[int(row["outbox_id"])],
            )
            for row in rows
        )

    def mark_outbox_sent(
        self,
        outbox_id: int,
        *,
        claim_token: str,
        sent_at: datetime | None = None,
    ) -> None:
        timestamp = ensure_utc(sent_at or datetime.now(UTC), field_name="sent_at")
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE core_v2_notification_outbox
                SET status = 'sent', sent_at = ?, locked_until = NULL,
                    claim_token = NULL, last_error = NULL
                WHERE outbox_id = ? AND status = 'inflight' AND claim_token = ?
                """,
                (timestamp.isoformat(), outbox_id, claim_token),
            ).rowcount
            if updated != 1:
                raise OutboxLeaseLostError(
                    f"Outbox item {outbox_id} is no longer owned by this claim"
                )

    def mark_outbox_failed(
        self,
        outbox_id: int,
        error: str,
        *,
        claim_token: str,
        retry_at: datetime,
    ) -> None:
        retry = ensure_utc(retry_at, field_name="retry_at")
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE core_v2_notification_outbox
                SET status = 'retry', attempts = attempts + 1,
                    next_attempt_at = ?, locked_until = NULL,
                    claim_token = NULL, last_error = ?
                WHERE outbox_id = ? AND status = 'inflight' AND claim_token = ?
                """,
                (retry.isoformat(), error[:2000], outbox_id, claim_token),
            ).rowcount
            if updated != 1:
                raise OutboxLeaseLostError(
                    f"Outbox item {outbox_id} is no longer owned by this claim"
                )

    def outbox_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM core_v2_notification_outbox
                GROUP BY status
                """
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def transition_times(self, strategy_id: str, key: MarketKey) -> tuple[datetime, ...]:
        """Read-only audit helper used by recovery checks and tests."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT processed_at
                FROM core_v2_runtime_transitions
                WHERE strategy_id = ? AND venue = ? AND instrument = ? AND timeframe = ?
                ORDER BY processed_at
                """,
                _identity(strategy_id, key),
            ).fetchall()
        return tuple(_parse_timestamp(row["processed_at"]) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS core_v2_runtime_state (
                    strategy_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    last_processed_at TEXT NOT NULL,
                    feature_anchor_version TEXT NOT NULL,
                    feature_anchor_open TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, venue, instrument, timeframe)
                );

                CREATE TABLE IF NOT EXISTS core_v2_bootstrap_state (
                    strategy_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    suppression_watermark TEXT,
                    completed INTEGER NOT NULL CHECK(completed IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, venue, instrument, timeframe)
                );

                CREATE TABLE IF NOT EXISTS core_v2_market_candles (
                    venue TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    close_time TEXT NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    PRIMARY KEY (venue, instrument, timeframe, close_time)
                );

                CREATE TABLE IF NOT EXISTS core_v2_runtime_transitions (
                    transition_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    decision_kind TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    event_id TEXT,
                    notification_suppressed INTEGER NOT NULL CHECK(notification_suppressed IN (0, 1)),
                    feature_anchor_version TEXT NOT NULL,
                    feature_anchor_open TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(strategy_id, venue, instrument, timeframe, processed_at)
                );

                CREATE TABLE IF NOT EXISTS core_v2_runtime_events (
                    event_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    strategy_symbol TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    notification_suppressed INTEGER NOT NULL CHECK(notification_suppressed IN (0, 1)),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS core_v2_notification_outbox (
                    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    topic_id INTEGER,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'retry', 'inflight', 'sent')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    locked_until TEXT,
                    claim_token TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    FOREIGN KEY(event_id) REFERENCES core_v2_runtime_events(event_id)
                );

                CREATE INDEX IF NOT EXISTS ix_core_v2_outbox_due
                ON core_v2_notification_outbox(status, next_attempt_at, locked_until);
                """
            )
            # Databases created by the pre-anchor runtime must remain readable
            # enough to produce an explicit fail-closed migration error.  We
            # intentionally leave legacy rows NULL instead of falsely blessing
            # their unknown recursive-indicator seed with the current anchor.
            self._add_nullable_column_if_missing(
                connection,
                "core_v2_runtime_state",
                "feature_anchor_version",
                "TEXT",
            )
            self._add_nullable_column_if_missing(
                connection,
                "core_v2_notification_outbox",
                "claim_token",
                "TEXT",
            )
            self._add_nullable_column_if_missing(
                connection,
                "core_v2_runtime_state",
                "feature_anchor_open",
                "TEXT",
            )
            self._add_nullable_column_if_missing(
                connection,
                "core_v2_runtime_transitions",
                "feature_anchor_version",
                "TEXT",
            )
            self._add_nullable_column_if_missing(
                connection,
                "core_v2_runtime_transitions",
                "feature_anchor_open",
                "TEXT",
            )

    @staticmethod
    def _add_nullable_column_if_missing(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        sql_type: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def _identity(strategy_id: str, key: MarketKey) -> tuple[str, str, str, str]:
    clean = strategy_id.strip()
    if not clean:
        raise ValueError("strategy_id cannot be blank")
    return clean, key.venue.value, key.instrument, key.timeframe


def _stable_id(*parts: str) -> str:
    joined = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def _json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return ensure_utc(value, field_name="json timestamp").isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")


def _parse_timestamp(value: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(value), field_name="stored timestamp")


def _row_to_closed_candle(key: MarketKey, row: sqlite3.Row) -> ClosedCandle:
    return ClosedCandle(
        key=key,
        open_time=_parse_timestamp(row["open_time"]),
        close_time=_parse_timestamp(row["close_time"]),
        open=Decimal(row["open"]),
        high=Decimal(row["high"]),
        low=Decimal(row["low"]),
        close=Decimal(row["close"]),
        volume=Decimal(row["volume"]),
    )
