"""Mapping from pure replay results to signal-review ORM rows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.backtest.signal_replay_analysis import calculate_forward_metrics
from app.backtest.signal_replay_models import ReplayResult, ReplaySignal
from app.repository.backtest.models import (
    SignalForwardMetric,
    SignalReplaySignal,
    SignalReview,
)
from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    TRIGGER_DURATION_BY_TIMEFRAME,
)

DEFINITION_VERSION = "btc-rsi-cross-v1"


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _decimal_text(value: Decimal) -> str:
    return str(Decimal(value))


def _snapshot(signal: ReplaySignal) -> dict[str, Any]:
    data = signal.data
    previous = data.previous_trigger
    current = data.current_trigger
    return {
        "snapshot_version": DEFINITION_VERSION,
        "symbol": data.symbol,
        "trigger_timeframe": data.trigger_timeframe,
        "trigger_close_time": data.trigger_close_time.astimezone(UTC).isoformat(),
        "trigger_close_price": _decimal_text(data.trigger_close_price),
        "trigger_price_ema21": _decimal_text(data.trigger_price_ema21),
        "previous_trigger": {
            "rsi21": previous.rsi21,
            "rsi_ema9": previous.rsi_ema9,
            "rsi_wma45": previous.rsi_wma45,
        },
        "current_trigger": {
            "rsi21": current.rsi21,
            "rsi_ema9": current.rsi_ema9,
            "rsi_wma45": current.rsi_wma45,
        },
        "h1_close_price": _decimal_text(data.h1_close_price),
        "h1_price_ema21": _decimal_text(data.h1_price_ema21),
        "h1_close_time": data.h1_close_time.astimezone(UTC).isoformat(),
        "h4_close_price": _decimal_text(data.h4_close_price),
        "h4_price_ema21": _decimal_text(data.h4_price_ema21),
        "h4_close_time": data.h4_close_time.astimezone(UTC).isoformat(),
        "decision": {
            "event_id": signal.decision.event_id,
            "should_alert": signal.decision.should_alert,
            "reason": signal.decision.reason,
        },
    }


def build_signal_rows(
    result: ReplayResult,
    *,
    replay_run_id: int,
    m5_frame,
    m15_frame,
) -> list[SignalReplaySignal]:
    """Build signal, review, and forward-metric rows without committing them."""

    rows: list[SignalReplaySignal] = []
    frames = {"5m": m5_frame, "15m": m15_frame}
    for signal in result.signals:
        data = signal.data
        trigger_duration = TRIGGER_DURATION_BY_TIMEFRAME[signal.timeframe]
        current = data.current_trigger
        previous = data.previous_trigger
        row = SignalReplaySignal(
            replay_run_id=replay_run_id,
            event_id=signal.decision.event_id,
            sequence=signal.sequence,
            timeframe=signal.timeframe,
            definition_version=DEFINITION_VERSION,
            trigger_open_at=_utc_naive(data.trigger_close_time - trigger_duration),
            trigger_close_at=_utc_naive(data.trigger_close_time),
            trigger_close_price=_decimal_text(data.trigger_close_price),
            trigger_price_ema21=_decimal_text(data.trigger_price_ema21),
            rsi21=current.rsi21,
            rsi_ema9=current.rsi_ema9,
            rsi_wma45=current.rsi_wma45,
            rsi_spread=current.rsi_ema9 - current.rsi_wma45,
            previous_rsi_ema9=previous.rsi_ema9 if signal.timeframe == "15m" else None,
            previous_rsi_wma45=previous.rsi_wma45 if signal.timeframe == "15m" else None,
            h4_close_price=_decimal_text(data.h4_close_price),
            h4_price_ema21=_decimal_text(data.h4_price_ema21),
            h4_close_at=_utc_naive(data.h4_close_time),
            decision_reason=signal.decision.reason,
            telegram_card=signal.telegram_card,
            snapshot=_snapshot(signal),
        )
        row.review = SignalReview(
            quality="UNREVIEWED",
            human_outcome="UNSET",
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
        for metric in calculate_forward_metrics(signal, frames[signal.timeframe]):
            row.forward_metrics.append(
                SignalForwardMetric(
                    horizon_minutes=metric["horizon_minutes"],
                    price_at_observation=metric["price_at_observation"],
                    return_pct=metric["return_pct"],
                    mfe_pct=metric["mfe_pct"],
                    mae_pct=metric["mae_pct"],
                    observed_at=(
                        _utc_naive(metric["observed_at"])
                        if metric["observed_at"] is not None
                        else None
                    ),
                    complete=metric["complete"],
                    warning=metric["warning"],
                )
            )
        rows.append(row)
    return rows
