# app/trading/strategy/rsi_no_retest_fade/exit.py
"""
Layer 2: Core Logic - RSI No Retest FADE Strategy — Exit Management
===================================================================

SHORT exit management — copied from ``rsi_no_retest_short/exit.py``.

The fade enters SHORT, so exit geometry is identical to the SHORT
mirror. The file is duplicated rather than imported to keep the two
experimental strategies independently mutable: a tweak made in
response to fade-specific behaviour shouldn't ripple into the SHORT
mirror without explicit thought.

- STEP 0: pending candle SL flag → exit at this candle's open.
- STEP 1: lock-profit move when ``low <= entry - move_sl_rr * R``,
  new SL = entry - lock_profit_rr * R.
- STEP 2: candle-close SL flag set when ``close >= soft_sl``
  (price closed back above the SHORT's stop). Skipped in touch mode.
- STEP 3: max-holding-period force-close (last priority, shared util).
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.actions import (
    EXIT_CLOSE_BY_CANDLE_SL,
    SIDE_SELL,
    ClosePosition,
    DoNothing,
    MoveSL,
)
from app.core.analysis_result import AnalysisResult
from app.core.constants import SL_TRIGGER_CANDLE_CLOSE, SL_TRIGGER_TOUCH
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot
from app.core.utils import to_decimal_or_none
from app.trading.sl_tp_calculator import SLTPCalculator
from app.trading.strategy.utils.bars_held import (
    increment_bars_held,
    maybe_force_close_max_holding,
)
from app.trading.strategy.utils.trade_state import TradeState

logger = structlog.get_logger()


def manage_exit(
    *,
    symbol: str,
    context: ContextSnapshot,
    close: Decimal | None,
    low: Decimal | None,
    open_price: Decimal | None,
    move_sl_rr: Decimal,
    lock_profit_rr: Decimal,
    taker_fee: Decimal,
    maker_fee: Decimal,
    sl_trigger_mode: str = SL_TRIGGER_CANDLE_CLOSE,
    max_holding_bars: int = 0,
) -> AnalysisResult:
    """Run exit management for an open SHORT (fade) position."""
    ts = TradeState.from_meta(context.meta)

    entry_price = to_decimal_or_none(ts.entry_price)
    if entry_price is None:
        return AnalysisResult(actions=[DoNothing()], new_context=context)

    bars_held = increment_bars_held(ts)
    context = ContextSnapshot(
        state=context.state,
        soft_sl_price=context.soft_sl_price,
        meta=ts.to_meta(),
    )
    _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

    soft_sl = context.soft_sl_price or to_decimal_or_none(ts.soft_sl_price)
    original_soft_sl = to_decimal_or_none(ts.original_soft_sl) or soft_sl
    moved_sl = ts.moved_sl_to_entry
    pending_candle_sl = ts.pending_candle_sl

    lock_profit_price = to_decimal_or_none(ts.lock_profit_price)
    if lock_profit_price is None and original_soft_sl and entry_price:
        lock_profit_price = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry_price,
            soft_sl_price=original_soft_sl,
            side=SIDE_SELL,
            lock_profit_rr=lock_profit_rr,
            taker_fee=taker_fee,
        )

    # STEP 0: pending candle SL — exit at THIS candle's open.
    if pending_candle_sl and open_price is not None:
        return AnalysisResult(
            actions=[ClosePosition(symbol=symbol, reason=EXIT_CLOSE_BY_CANDLE_SL, price=open_price)],
            new_context=ContextSnapshot(state=SCANNING),
        )

    # STEP 1: Move SL to lock profit when low reaches entry - move_sl_rr * R.
    if (not moved_sl) and low is not None and soft_sl is not None and original_soft_sl is not None:
        move_trigger = to_decimal_or_none(ts.move_trigger)
        if move_trigger is None:
            move_trigger = SLTPCalculator.compute_tp_price(
                entry_price=entry_price,
                sl_price=original_soft_sl,
                side=SIDE_SELL,
                rr_ratio=move_sl_rr,
                taker_fee=taker_fee,
                exit_fee=maker_fee,
            )
        if move_trigger is not None and low <= move_trigger and lock_profit_price is not None:
            new_ts = TradeState.from_meta(context.meta)
            new_ts.moved_sl_to_entry = True
            new_ts.sl_price = lock_profit_price
            new_ts.soft_sl_price = lock_profit_price
            new_ctx = ContextSnapshot(
                state=context.state,
                soft_sl_price=lock_profit_price,
                meta=new_ts.to_meta(),
            )
            return AnalysisResult(
                actions=[
                    MoveSL(
                        symbol=symbol,
                        new_sl_price=lock_profit_price,
                        reason=(
                            f"MOVE_SL_LOCK_PROFIT (low={low} <= {move_trigger} = -{move_sl_rr}R, "
                            f"new_sl={lock_profit_price} = -{lock_profit_rr}R)"
                        ),
                    )
                ],
                new_context=new_ctx,
            )

    # STEP 2: Candle-close SL — set flag, exit next candle's open.
    # SHORT triggers when close >= soft_sl (price closed back above stop).
    if (
        sl_trigger_mode != SL_TRIGGER_TOUCH
        and soft_sl is not None
        and close is not None
        and close >= soft_sl
    ):
        new_ts = TradeState.from_meta(context.meta)
        new_ts.pending_candle_sl = True
        new_ctx = ContextSnapshot(state=context.state, soft_sl_price=soft_sl, meta=new_ts.to_meta())
        return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

    # STEP 3: Max holding period — force-close last.
    max_holding_result = maybe_force_close_max_holding(
        symbol=symbol,
        bars_held=bars_held,
        max_bars=max_holding_bars,
        close_price=close,
    )
    if max_holding_result is not None:
        return max_holding_result

    return _noop
