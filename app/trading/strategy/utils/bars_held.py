"""Shared bars-held counter and max-holding-period exit helpers.

Both `rsi_no_retest` and `rsi_momentum` need to (a) increment a per-bar
counter while a position is open and (b) force-close the position at
market once that counter clears a configured threshold. This module
factors out the two helpers so the strategies' `exit.py` modules don't
need to maintain copies.

Direction-agnostic: the force-close just emits a `ClosePosition` action
at the current bar's `close` price. Long/short specifics (SL ordering,
lock-profit math) live in each strategy.

The bars-held counter lives on the `TradeState` dataclass and is
serialized into `ContextSnapshot.meta` via `ts.to_meta()`. Callers must
mutate `ts` BEFORE rebuilding the context, so all downstream return
paths see the new value.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.actions import EXIT_MAX_HOLDING_PERIOD, ClosePosition
from app.core.analysis_result import AnalysisResult
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot
from app.trading.strategy.utils.trade_state import TradeState


def increment_bars_held(ts: TradeState) -> int:
    """Increment ``ts.bars_held`` in place. Returns the new count.

    Should be called once per ``analyze()`` invocation while a position
    is open, BEFORE any exit-step checks. The mutation happens on the
    ``TradeState`` dataclass; the caller is responsible for round-
    tripping via ``ts.to_meta()`` when rebuilding ``ContextSnapshot``
    so the new value is persisted.
    """
    ts.bars_held = (ts.bars_held or 0) + 1
    return ts.bars_held


def maybe_force_close_max_holding(
    *,
    symbol: str,
    bars_held: int,
    max_bars: int,
    close_price: Decimal | None,
) -> AnalysisResult | None:
    """Return a force-close ``AnalysisResult`` if max-holding triggers.

    Returns ``None`` when:
    - ``max_bars <= 0`` (feature disabled), or
    - ``close_price`` is ``None`` (no current bar close to exit at), or
    - ``bars_held < max_bars`` (still under the threshold).

    Direction-agnostic — the action is a market close at ``close_price``
    regardless of whether the position is long or short.

    Should be called as the LAST exit-step check, so that more specific
    exits (pending candle-close SL, lock-profit move, candle-close flag)
    take priority on the same bar.
    """
    if max_bars <= 0:
        return None
    if close_price is None:
        return None
    if bars_held < max_bars:
        return None
    return AnalysisResult(
        actions=[
            ClosePosition(
                symbol=symbol,
                reason=EXIT_MAX_HOLDING_PERIOD,
                price=close_price,
            )
        ],
        new_context=ContextSnapshot(state=SCANNING),
    )
