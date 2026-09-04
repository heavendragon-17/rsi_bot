"""Application service for database-backed BTC signal review replays."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.backtest import executor
from app.backtest.signal_replay import _default_paths
from app.backtest.signal_replay_analysis import (
    TradeExitEvaluation,
    chart_window_from_frame,
    source_metadata,
)
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.backtest.signal_replay_persistence import DEFINITION_VERSION
from app.backtest.signal_replay_support import (
    UTC_PLUS_7,
    _availability_datetime,
    _evaluate_trade_plan,
    _now_utc_naive,
    _parse_trade_price,
    _review_values,
    _utc_naive,
    current_git_hash,
    parse_boundary,
    run_summary,
    signal_detail,
    signal_summary,
)
from app.backtest.signal_replay_worker import run_signal_replay_worker
from app.repository.backtest.models import (
    SignalReplayRun,
    SignalReplaySignal,
    SignalReview,
)

REPLAY_SOURCE_TIMEFRAMES = ("5m", "15m", "1h", "4h")


class SignalReplayService:
    """Coordinates replay jobs and exposes review-oriented query operations."""

    def get_availability(self) -> dict[str, Any]:
        """Inspect the canonical replay inputs and return their common range."""

        sources: list[dict[str, Any]] = []
        starts: list[datetime] = []
        ends: list[datetime] = []
        for timeframe, path in zip(
            REPLAY_SOURCE_TIMEFRAMES,
            _default_paths(),
            strict=True,
        ):
            if not path.is_file():
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": False,
                        "row_count": 0,
                        "available_start": None,
                        "available_end": None,
                        "source_modified_at": None,
                        "error": f"Missing {path.name}",
                    }
                )
                continue
            try:
                frame = load_ohlcv_csv(path, timeframe)
                metadata = source_metadata(path, frame, timeframe)
                available_start = _availability_datetime(
                    metadata["available_start"]
                )
                available_end = _availability_datetime(metadata["available_end"])
                if available_start is None or available_end is None:
                    raise ValueError("CSV contains no candles")
                starts.append(available_start)
                ends.append(available_end)
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": True,
                        "row_count": metadata["row_count"],
                        "available_start": metadata["available_start"],
                        "available_end": metadata["available_end"],
                        "source_modified_at": metadata["source_modified_at"],
                        "error": None,
                    }
                )
            except (OSError, ValueError) as exc:
                sources.append(
                    {
                        "timeframe": timeframe,
                        "available": False,
                        "row_count": 0,
                        "available_start": None,
                        "available_end": None,
                        "source_modified_at": None,
                        "error": f"{path.name}: {exc}",
                    }
                )

        ready = len(starts) == len(REPLAY_SOURCE_TIMEFRAMES)
        common_start = max(starts) if ready else None
        common_end = min(ends) if ready else None
        if common_start is not None and common_end is not None:
            ready = common_start <= common_end
        return {
            "ready": ready,
            "common_start_at": (
                common_start.isoformat() if ready and common_start else None
            ),
            "common_end_at": (
                common_end.isoformat() if ready and common_end else None
            ),
            "sources": sources,
        }

    def reconcile_orphaned_runs(self, db) -> None:
        """Fail running DB rows whose in-memory executor job no longer exists."""

        orphaned = (
            db.query(SignalReplayRun)
            .filter_by(status="running")
            .order_by(SignalReplayRun.created_at.asc())
            .all()
        )
        changed = False
        for run in orphaned:
            if executor.get_progress_queue(run.id) is not None:
                continue
            run.status = "failed"
            run.error_message = (
                "Replay was interrupted before completion. Start a new replay."
            )
            run.completed_at = _now_utc_naive()
            changed = True
        if changed:
            db.commit()

    async def start_run(self, start_raw: str | None, end_raw: str | None, db) -> int:
        self.reconcile_orphaned_runs(db)
        active_run = (
            db.query(SignalReplayRun)
            .filter_by(status="running")
            .order_by(SignalReplayRun.created_at.desc())
            .first()
        )
        if active_run is not None:
            raise ValueError(f"Signal replay #{active_run.id} is already running")

        availability = self.get_availability()
        if not availability["ready"]:
            errors = [
                source["error"]
                for source in availability["sources"]
                if source["error"]
            ]
            raise ValueError(
                "Signal replay data is not ready: " + "; ".join(errors)
            )
        available_start = _availability_datetime(availability["common_start_at"])
        available_end = _availability_datetime(availability["common_end_at"])
        if available_start is None or available_end is None:
            raise ValueError("Signal replay data has no common available range")

        start_at = parse_boundary(start_raw, is_end=False) or available_start
        end_at = parse_boundary(end_raw, is_end=True) or available_end
        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("start must be before or equal to end")
        if start_at < available_start or end_at > available_end:
            start_label = available_start.astimezone(UTC_PLUS_7).isoformat()
            end_label = available_end.astimezone(UTC_PLUS_7).isoformat()
            raise ValueError(
                "Replay range must stay inside the available data range "
                f"{start_label} to {end_label}"
            )

        now = _now_utc_naive()
        run = SignalReplayRun(
            status="running",
            strategy_name="btc_rsi_cross_alert",
            definition_version=DEFINITION_VERSION,
            git_hash=current_git_hash(),
            symbol="BTC/USDT",
            requested_start_at=_utc_naive(start_at),
            requested_end_at=_utc_naive(end_at),
            created_at=now,
            started_at=now,
            source_metadata={},
            counters={},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        loop = asyncio.get_running_loop()
        executor.create_progress_queue(run.id)
        progress_cb = executor.make_progress_callback(run.id, loop)
        try:
            executor.submit_backtest(
                run.id,
                run_signal_replay_worker,
                run_id=run.id,
                start_at=start_at,
                end_at=end_at,
                loop=loop,
                progress_cb=progress_cb,
                publish_event_fn=executor.publish_event,
                cleanup_fn=executor.cleanup_job,
            )
        except Exception as exc:
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {exc}"
            run.completed_at = _now_utc_naive()
            db.commit()
            executor.cleanup_job(run.id)
            raise
        return run.id

    async def stream_progress(self, run_id: int, db=None):
        """Reuse the existing SSE queue consumer for replay jobs."""

        if executor.get_progress_queue(run_id) is None:
            run = db.query(SignalReplayRun).filter_by(id=run_id).first() if db is not None else None
            if run is None:
                yield f"event: error\ndata: {json.dumps({'message': 'Signal replay run not found'})}\n\n"
            elif run.status == "failed":
                yield f"event: error\ndata: {json.dumps({'message': run.error_message or 'Signal replay failed'})}\n\n"
            elif run.status == "running":
                yield f"event: error\ndata: {json.dumps({'message': 'Replay was interrupted before completion. Start a new replay.'})}\n\n"
            else:
                yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': run.status})}\n\n"
            return

        from app.backtest.service import BacktestService

        async for event in BacktestService().stream_progress(run_id):
            yield event

    def get_run(self, run_id: int, db) -> dict[str, Any]:
        run = db.query(SignalReplayRun).filter_by(id=run_id).first()
        if run is None:
            raise LookupError("Signal replay run not found")
        return {
            "run": run_summary(run, db),
            "source_metadata": run.source_metadata or {},
            "counters": run.counters or {},
        }

    def list_signals(
        self,
        db,
        *,
        timeframe: str | None,
        replay_run_id: int | None,
        quality: str | None,
        human_outcome: str | None,
        start_raw: str | None,
        end_raw: str | None,
        page: int,
        limit: int,
    ) -> dict[str, Any]:
        start_at = parse_boundary(start_raw, is_end=False)
        end_at = parse_boundary(end_raw, is_end=True)
        query = db.query(SignalReplaySignal)
        if timeframe:
            if timeframe not in {"5m", "15m"}:
                raise ValueError("timeframe must be 5m or 15m")
            query = query.filter(SignalReplaySignal.timeframe == timeframe)
        if replay_run_id is not None:
            query = query.filter(SignalReplaySignal.replay_run_id == replay_run_id)
        if quality or human_outcome:
            query = query.join(SignalReview, isouter=True)
        if quality:
            query = query.filter(SignalReview.quality == quality)
        if human_outcome:
            query = query.filter(SignalReview.human_outcome == human_outcome)
        if start_at:
            query = query.filter(SignalReplaySignal.trigger_close_at >= _utc_naive(start_at))
        if end_at:
            query = query.filter(SignalReplaySignal.trigger_close_at <= _utc_naive(end_at))

        total = query.count()
        pages = max(1, math.ceil(total / limit))
        offset = (page - 1) * limit
        signals = (
            query.order_by(
                SignalReplaySignal.trigger_close_at.desc(),
                SignalReplaySignal.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "signals": [signal_summary(signal) for signal in signals],
            "total": total,
            "page": page,
            "pages": pages,
        }

    def get_signal(self, signal_id: int, db) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        return signal_detail(signal)

    def get_chart(
        self,
        signal_id: int,
        db,
        *,
        chart_timeframe: str | None,
        start_raw: str | None,
        end_raw: str | None,
    ) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        run = db.query(SignalReplayRun).filter_by(id=signal.replay_run_id).first()
        if run is None:
            raise LookupError("Replay run not found")
        requested_timeframe = chart_timeframe or signal.timeframe
        if requested_timeframe not in REPLAY_SOURCE_TIMEFRAMES:
            raise ValueError("chart timeframe must be 5m, 15m, 1h, or 4h")
        metadata = (run.source_metadata or {}).get(requested_timeframe, {})
        csv_path_raw = metadata.get("path")
        csv_path = Path(csv_path_raw) if csv_path_raw else None
        allow_future = signal.review is not None and signal.review.quality != "UNREVIEWED"
        start_at = parse_boundary(start_raw, is_end=False)
        end_at = parse_boundary(end_raw, is_end=True)
        signal_time = signal.trigger_close_at.replace(tzinfo=UTC)
        if csv_path is None or not csv_path.is_file():
            return {
                "signal_id": signal_id,
                "timeframe": requested_timeframe,
                "candles": [],
                "available_start": metadata.get("available_start"),
                "available_end": metadata.get("available_end"),
                "requested_start": start_raw,
                "requested_end": end_raw,
                "has_before": False,
                "has_after": False,
                "future_allowed": allow_future,
                "signal_time": signal_time.isoformat(),
                "anchor_time": None,
                "warning": (
                    f"{requested_timeframe.upper()} replay source is unavailable "
                    "for this dataset."
                ),
            }
        try:
            frame = load_ohlcv_csv(csv_path, requested_timeframe)
            current_source = source_metadata(csv_path, frame, requested_timeframe)
            candles, chart_metadata = chart_window_from_frame(
                frame,
                requested_timeframe,
                trigger_close=signal_time,
                start_at=start_at,
                end_at=end_at,
                allow_future=allow_future,
            )
            source_warnings: list[str] = []
            for key in ("row_count", "available_start", "available_end", "source_modified_at"):
                if metadata.get(key) and metadata.get(key) != current_source.get(key):
                    source_warnings.append(f"Current CSV {key.replace('_', ' ')} differs from the replay source.")
            if source_warnings:
                warnings = [warning for warning in (chart_metadata.get("warning"), *source_warnings) if warning]
                chart_metadata["warning"] = " ".join(dict.fromkeys(warnings))
        except (LookupError, ValueError) as exc:
            return {
                "signal_id": signal_id,
                "timeframe": requested_timeframe,
                "candles": [],
                "available_start": metadata.get("available_start"),
                "available_end": metadata.get("available_end"),
                "requested_start": start_raw,
                "requested_end": end_raw,
                "has_before": False,
                "has_after": False,
                "future_allowed": allow_future,
                "signal_time": signal_time.isoformat(),
                "anchor_time": None,
                "warning": str(exc),
            }
        return {
            "signal_id": signal_id,
            "timeframe": requested_timeframe,
            "candles": candles,
            **chart_metadata,
        }

    def update_review(self, signal_id: int, patch, db) -> dict[str, Any]:
        signal = db.query(SignalReplaySignal).filter_by(id=signal_id).first()
        if signal is None:
            raise LookupError("Signal not found")
        review = signal.review
        fields = patch.model_fields_set
        quality_was_unreviewed = review is None or review.quality == "UNREVIEWED"
        effective_quality = (
            patch.quality.value
            if "quality" in fields and patch.quality is not None
            else (review.quality if review is not None else "UNREVIEWED")
        )
        quality_unlocks_future = (
            "quality" in fields
            and patch.quality is not None
            and patch.quality.value != "UNREVIEWED"
            and quality_was_unreviewed
        )
        plan_touched = "take_profit_price" in fields or "stop_loss_price" in fields
        existing_take_profit = review.take_profit_price if review is not None else None
        existing_stop_loss = review.stop_loss_price if review is not None else None
        proposed_take_profit = (
            patch.take_profit_price
            if "take_profit_price" in fields
            else existing_take_profit
        )
        proposed_stop_loss = (
            patch.stop_loss_price
            if "stop_loss_price" in fields
            else existing_stop_loss
        )
        evaluation: TradeExitEvaluation | None = None
        canonical_take_profit: Decimal | None = None
        canonical_stop_loss: Decimal | None = None
        if plan_touched:
            if proposed_take_profit is None and proposed_stop_loss is None:
                canonical_take_profit = None
                canonical_stop_loss = None
            elif proposed_take_profit is None or proposed_stop_loss is None:
                raise ValueError("Take-profit and stop-loss must be set together")
        if proposed_take_profit is not None and proposed_stop_loss is not None:
            if plan_touched or quality_unlocks_future:
                entry_price = _parse_trade_price(
                    signal.trigger_close_price,
                    "Signal entry price",
                )
                canonical_take_profit = _parse_trade_price(
                    proposed_take_profit,
                    "Take-profit price",
                )
                canonical_stop_loss = _parse_trade_price(
                    proposed_stop_loss,
                    "Stop-loss price",
                )
                if canonical_take_profit <= entry_price:
                    raise ValueError("Take-profit price must be above the signal entry")
                if canonical_stop_loss >= entry_price:
                    raise ValueError("Stop-loss price must be below the signal entry")
                if effective_quality != "UNREVIEWED":
                    run = db.query(SignalReplayRun).filter_by(id=signal.replay_run_id).first()
                    if run is None:
                        raise LookupError("Replay run not found")
                    evaluation = _evaluate_trade_plan(
                        signal,
                        run,
                        take_profit_price=canonical_take_profit,
                        stop_loss_price=canonical_stop_loss,
                    )

        if review is None:
            review = SignalReview(
                signal_id=signal_id,
                quality="UNREVIEWED",
                human_outcome="UNSET",
            )
            db.add(review)
            db.flush()

        if "quality" in fields and patch.quality is not None:
            review.quality = patch.quality.value
            if review.quality == "UNREVIEWED":
                review.human_outcome = "UNSET"
                review.reviewed_at = None
                review.future_unlocked_at = None
                if review.take_profit_price is not None and review.stop_loss_price is not None:
                    review.exit_reason = None
                    review.exit_at = None
                    review.duration_minutes = None
                    review.evaluation_warning = None
                    review.evaluated_at = None
            else:
                reviewed_at = _now_utc_naive()
                review.reviewed_at = reviewed_at
                review.future_unlocked_at = reviewed_at
        if "human_outcome" in fields and patch.human_outcome is not None:
            if patch.human_outcome.value != "UNSET" and review.quality == "UNREVIEWED":
                raise ValueError("Save a quality label before recording a human outcome")
            review.human_outcome = patch.human_outcome.value
        if "note" in fields:
            review.note = patch.note
        if plan_touched:
            review.take_profit_price = (
                str(canonical_take_profit) if canonical_take_profit is not None else None
            )
            review.stop_loss_price = (
                str(canonical_stop_loss) if canonical_stop_loss is not None else None
            )
            if (
                canonical_take_profit is None
                or canonical_stop_loss is None
                or evaluation is None
            ):
                review.exit_reason = None
                review.exit_at = None
                review.duration_minutes = None
                review.evaluation_warning = None
                review.evaluated_at = None
        if evaluation is not None:
            assert canonical_take_profit is not None
            assert canonical_stop_loss is not None
            review.take_profit_price = str(canonical_take_profit)
            review.stop_loss_price = str(canonical_stop_loss)
            review.exit_reason = evaluation.exit_reason
            review.exit_at = (
                evaluation.exit_at.replace(tzinfo=None)
                if evaluation.exit_at is not None
                else None
            )
            review.duration_minutes = evaluation.duration_minutes
            review.evaluation_warning = evaluation.warning
            review.evaluated_at = _now_utc_naive()
        review.updated_at = _now_utc_naive()
        db.commit()
        db.refresh(review)
        return _review_values(review, entry_price=signal.trigger_close_price)
