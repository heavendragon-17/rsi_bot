"""Mechanical SL/TP/age monitor for virtual positions.

The monitor is **pure**: it takes a VP and the just-closed candle and returns
the exit events that should fire. The caller (slice-6 ``StrategyWorker``)
applies the resulting state transitions on the store and dispatches the
formatted messages.

Precedence per spec §7:
    1. SL first — if triggered, nothing else fires for this candle.
    2. TP wick-touch events accumulate. The last TP carries ``closes_vp``.
    3. Age expiry only if no SL and no closing-TP fired on this candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

from app.core.constants import SIGNAL_MAX_VP_AGE_CANDLES, TIMEFRAME_SECONDS
from app.core.events import Candle
from app.signal.virtual_position import VirtualPosition

logger = structlog.get_logger()

# Tracks (strategy, symbol, timeframe) triples already warned-about so a
# misconfigured timeframe doesn't spam a warning on every candle close.
_warned_unknown_timeframe: set[tuple[str, str, str]] = set()


@dataclass(frozen=True)
class SLHit:
    vp: VirtualPosition
    candle: Candle


@dataclass(frozen=True)
class TPHit:
    vp: VirtualPosition
    tp_index: int
    tp_price: Decimal
    candle: Candle
    closes_vp: bool


@dataclass(frozen=True)
class Expired:
    vp: VirtualPosition
    candle: Candle
    age_candles: int


ExitEvent = SLHit | TPHit | Expired


def _candle_ts_ms(candle: Candle) -> int:
    """Convert a Candle's timestamp to unix milliseconds.

    ``DataNormalizer`` applies a ``+7h`` shift when building candles. Because
    both the VP's ``opened_at_candle_ts`` and the current candle go through
    this same helper, the offset cancels out in any elapsed-time subtraction.
    """
    return int(candle.timestamp.timestamp() * 1000)


def _sl_triggered(vp: VirtualPosition, close: Decimal) -> bool:
    if vp.side == "LONG":
        return close < vp.sl_price
    return close > vp.sl_price


def _tp_wick_touches(
    vp: VirtualPosition, candle: Candle, tp_price: Decimal
) -> bool:
    if vp.side == "LONG":
        return candle.high >= tp_price
    return candle.low <= tp_price


def check(
    vp: VirtualPosition,
    candle: Candle,
    *,
    max_age_candles: int = SIGNAL_MAX_VP_AGE_CANDLES,
) -> list[ExitEvent]:
    """Evaluate SL, TP, and age rules against the closed candle.

    Returns a list of 0+ exit events. SL wins over TP (spec §7). Age expiry
    is skipped when the timeframe isn't in ``TIMEFRAME_SECONDS`` so a typo
    in config never causes a never-expire-or-always-expire bug.
    """
    close_price = candle.close

    if _sl_triggered(vp, close_price):
        return [SLHit(vp=vp, candle=candle)]

    events: list[ExitEvent] = []
    already_hit = vp.tp_hits
    newly_hit = set(already_hit)

    for idx, tp_price in enumerate(vp.tp_levels):
        if idx in already_hit:
            continue
        if _tp_wick_touches(vp, candle, tp_price):
            newly_hit.add(idx)
            closes_vp = len(newly_hit) == len(vp.tp_levels)
            events.append(
                TPHit(
                    vp=vp,
                    tp_index=idx,
                    tp_price=tp_price,
                    candle=candle,
                    closes_vp=closes_vp,
                )
            )

    closing_tp = any(
        isinstance(e, TPHit) and e.closes_vp for e in events
    )
    if closing_tp:
        return events

    expired = _age_expiry(vp, candle, max_age_candles)
    if expired is not None:
        events.append(expired)
    return events


def _age_expiry(
    vp: VirtualPosition, candle: Candle, max_age_candles: int
) -> Expired | None:
    tf_seconds = TIMEFRAME_SECONDS.get(vp.timeframe)
    if tf_seconds is None:
        key = (vp.strategy_name, vp.symbol, vp.timeframe)
        if key not in _warned_unknown_timeframe:
            _warned_unknown_timeframe.add(key)
            logger.warning(
                "exit_monitor_unknown_timeframe",
                strategy=vp.strategy_name,
                symbol=vp.symbol,
                timeframe=vp.timeframe,
            )
        return None

    elapsed_ms = _candle_ts_ms(candle) - vp.opened_at_candle_ts
    if elapsed_ms <= 0:
        return None
    age_candles = elapsed_ms // (tf_seconds * 1000)
    if age_candles <= max_age_candles:
        return None
    return Expired(vp=vp, candle=candle, age_candles=int(age_candles))
