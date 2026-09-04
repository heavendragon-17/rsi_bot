"""Shared helpers for database-backed BTC signal review replays.

Time parsing, response serializers, and trade-plan evaluation used by
SignalReplayService and the signal-replay API routes. Split out of
signal_replay_service.py to keep that module under the 600-line
architecture limit.
"""

from __future__ import annotations

import shutil

# Only used for the fixed-argv git revision probe below (no user input).
import subprocess  # nosec B404
from datetime import UTC, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.backtest.signal_replay_analysis import (
    TRADE_EXIT_NO_DATA,
    TradeExitEvaluation,
    evaluate_long_trade,
)
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.repository.backtest.models import (
    SignalForwardMetric,
    SignalReplayRun,
    SignalReplaySignal,
    SignalReview,
)

UTC_PLUS_7 = timezone(timedelta(hours=7), name="UTC+7")


def parse_boundary(raw: str | None, *, is_end: bool) -> datetime | None:
    """Parse a date or timestamp, interpreting naive values as UTC+7."""

    if raw is None or raw == "":
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            "date boundaries must be YYYY-MM-DD or an ISO timestamp"
        ) from exc
    if len(raw) == 10:
        parsed = datetime.combine(parsed.date(), time.min)
        if is_end:
            parsed += timedelta(days=1) - timedelta(microseconds=1)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC_PLUS_7)
    return parsed.astimezone(UTC)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def api_datetime(value: datetime | None) -> str | None:
    """Serialize DB's UTC-naive timestamps as explicit UTC ISO strings."""

    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _availability_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def current_git_hash() -> str | None:
    """Capture the code revision when the API is running from a Git checkout."""

    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    try:
        # Fixed argv, absolute executable path, no untrusted input.
        completed = subprocess.run(  # nosec B603
            [git_executable, "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _review_values(
    review: SignalReview | None,
    *,
    entry_price: str | None = None,
) -> dict[str, Any]:
    if review is None:
        return {
            "entry_price": entry_price,
            "take_profit_price": None,
            "stop_loss_price": None,
            "exit_reason": None,
            "exit_at": None,
            "duration_minutes": None,
            "evaluation_warning": None,
            "evaluated_at": None,
            "quality": "UNREVIEWED",
            "human_outcome": "UNSET",
            "note": None,
            "reviewed_at": None,
            "updated_at": None,
            "future_unlocked_at": None,
        }
    return {
        "entry_price": entry_price,
        "take_profit_price": review.take_profit_price,
        "stop_loss_price": review.stop_loss_price,
        "exit_reason": review.exit_reason,
        "exit_at": api_datetime(review.exit_at),
        "duration_minutes": review.duration_minutes,
        "evaluation_warning": review.evaluation_warning,
        "evaluated_at": api_datetime(review.evaluated_at),
        "quality": review.quality,
        "human_outcome": review.human_outcome,
        "note": review.note,
        "reviewed_at": api_datetime(review.reviewed_at),
        "updated_at": api_datetime(review.updated_at),
        "future_unlocked_at": api_datetime(review.future_unlocked_at),
    }


def _metric_values(metric: SignalForwardMetric) -> dict[str, Any]:
    return {
        "horizon_minutes": metric.horizon_minutes,
        "price_at_observation": metric.price_at_observation,
        "return_pct": metric.return_pct,
        "mfe_pct": metric.mfe_pct,
        "mae_pct": metric.mae_pct,
        "observed_at": api_datetime(metric.observed_at),
        "complete": metric.complete,
        "warning": metric.warning,
    }


def run_summary(run: SignalReplayRun, db) -> dict[str, Any]:
    signals = db.query(SignalReplaySignal).filter_by(replay_run_id=run.id)
    m5_count = signals.filter_by(timeframe="5m").count()
    m15_count = signals.filter_by(timeframe="15m").count()
    return {
        "id": run.id,
        "status": run.status,
        "strategy_name": run.strategy_name,
        "definition_version": run.definition_version,
        "git_hash": run.git_hash,
        "symbol": run.symbol,
        "requested_start_at": api_datetime(run.requested_start_at),
        "requested_end_at": api_datetime(run.requested_end_at),
        "created_at": api_datetime(run.created_at),
        "started_at": api_datetime(run.started_at),
        "completed_at": api_datetime(run.completed_at),
        "signal_count": m5_count + m15_count,
        "m5_count": m5_count,
        "m15_count": m15_count,
        "error_message": run.error_message,
    }


def signal_summary(signal: SignalReplaySignal) -> dict[str, Any]:
    review = _review_values(signal.review, entry_price=signal.trigger_close_price)
    return {
        "id": signal.id,
        "replay_run_id": signal.replay_run_id,
        "event_id": signal.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "trigger_close_at": api_datetime(signal.trigger_close_at),
        "trigger_close_price": signal.trigger_close_price,
        "decision_reason": signal.decision_reason,
        "quality": review["quality"],
        "human_outcome": review["human_outcome"],
        "note_present": bool(review["note"]),
    }


def signal_detail(signal: SignalReplaySignal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "replay_run_id": signal.replay_run_id,
        "event_id": signal.event_id,
        "sequence": signal.sequence,
        "timeframe": signal.timeframe,
        "definition_version": signal.definition_version,
        "trigger_open_at": api_datetime(signal.trigger_open_at),
        "trigger_close_at": api_datetime(signal.trigger_close_at),
        "trigger_close_price": signal.trigger_close_price,
        "trigger_price_ema21": signal.trigger_price_ema21,
        "rsi21": signal.rsi21,
        "rsi_ema9": signal.rsi_ema9,
        "rsi_wma45": signal.rsi_wma45,
        "rsi_spread": signal.rsi_spread,
        "previous_rsi_ema9": signal.previous_rsi_ema9,
        "previous_rsi_wma45": signal.previous_rsi_wma45,
        "h4_close_price": signal.h4_close_price,
        "h4_price_ema21": signal.h4_price_ema21,
        "h4_close_at": api_datetime(signal.h4_close_at),
        "decision_reason": signal.decision_reason,
        "telegram_card": signal.telegram_card,
        "snapshot": signal.snapshot,
        "review": _review_values(
            signal.review,
            entry_price=signal.trigger_close_price,
        ),
        "forward_metrics": [_metric_values(metric) for metric in signal.forward_metrics],
    }


def _parse_trade_price(raw: str | None, label: str) -> Decimal:
    """Parse a positive reviewer-entered exchange-style price."""

    if raw is None or not raw.strip():
        raise ValueError(f"{label} is required")
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a valid price") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{label} must be a positive finite price")
    return value


def _evaluate_trade_plan(
    signal: SignalReplaySignal,
    run: SignalReplayRun,
    *,
    take_profit_price: Decimal,
    stop_loss_price: Decimal,
) -> TradeExitEvaluation:
    """Evaluate a plan against the signal's native replay source."""

    metadata = (run.source_metadata or {}).get(signal.timeframe, {})
    csv_path_raw = metadata.get("path")
    csv_path = Path(csv_path_raw) if csv_path_raw else None
    if csv_path is None or not csv_path.is_file():
        return TradeExitEvaluation(
            exit_reason=TRADE_EXIT_NO_DATA,
            exit_at=None,
            duration_minutes=None,
            warning=(
                f"{signal.timeframe.upper()} replay source is unavailable "
                "for this dataset."
            ),
        )
    try:
        frame = load_ohlcv_csv(csv_path, signal.timeframe)
    except (OSError, ValueError) as exc:
        return TradeExitEvaluation(
            exit_reason=TRADE_EXIT_NO_DATA,
            exit_at=None,
            duration_minutes=None,
            warning=f"Could not evaluate the replay source: {exc}",
        )
    return evaluate_long_trade(
        frame,
        signal.timeframe,
        trigger_close=signal.trigger_close_at.replace(tzinfo=UTC),
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
    )
