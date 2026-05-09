# app/trading/strategy/rsi_no_retest/exit.py
"""
Layer 2: Core Logic - RSI No Retest Strategy — Exit Management
==============================================================

Module-level functions for managing open positions:
- Pending candle SL (close at next candle open)
- Lock-profit SL trigger (move SL when high >= +0.5R)
- Candle-close SL flag (close < soft SL)
- Max-holding-period force-close (last-resort exit)

All functions receive explicit parameters instead of accessing ``self``.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.actions import ClosePosition, DoNothing, MoveSL
from app.core.analysis_result import AnalysisResult
from app.core.constants import SL_TRIGGER_CANDLE_CLOSE, SL_TRIGGER_TOUCH
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot
from app.core.utils import to_decimal_or_none
from app.trading.strategy.utils.bars_held import (
    increment_bars_held,
    maybe_force_close_max_holding,
)
from app.trading.strategy.utils.trade_state import TradeState

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Fee-aware price-at-RR (shared with entry, but kept here for exit calcs)
# ---------------------------------------------------------------------------


def compute_price_at_rr(
    entry: Decimal,
    sl: Decimal,
    rr: Decimal,
    taker_fee: Decimal,
    maker_fee: Decimal,
    is_taker_exit: bool = False,
) -> Decimal | None:
    """Target price to achieve exactly ``rr * R`` net of fees.

    R = entry - sl.  Entry is always a taker order; exit fee depends on
    *is_taker_exit*.
    """
    risk = entry - sl
    if risk <= Decimal("0"):
        return None

    target_net_profit = rr * risk
    exit_fee_rate = taker_fee if is_taker_exit else maker_fee

    target_price = (entry * (Decimal("1") + taker_fee) + target_net_profit) / (Decimal("1") - exit_fee_rate)
    return target_price


# ---------------------------------------------------------------------------
# Main exit / management check — called from analyze()
# ---------------------------------------------------------------------------


def manage_exit(
    *,
    symbol: str,
    context: ContextSnapshot,
    close: Decimal | None,
    high: Decimal | None,
    open_price: Decimal | None,
    # strategy params
    move_sl_rr: Decimal,
    lock_profit_rr: Decimal,
    taker_fee: Decimal,
    maker_fee: Decimal,
    sl_trigger_mode: str = SL_TRIGGER_CANDLE_CLOSE,
    max_holding_bars: int = 0,
) -> AnalysisResult:
    """Run exit management for an open position.

    Returns an ``AnalysisResult`` with one of:
    - ``ClosePosition`` (pending candle SL fires, or max-holding force-close)
    - ``MoveSL`` (lock profit trigger)
    - ``DoNothing`` (candle-close SL flag set, or nothing to do)

    When *sl_trigger_mode* is ``"touch"`` the exchange-level stop fires on
    touch, so the candle-close detection in STEP 2 is skipped.
    """
    ts = TradeState.from_meta(context.meta)

    entry_price = to_decimal_or_none(ts.entry_price)
    if entry_price is None:
        return AnalysisResult(actions=[DoNothing()], new_context=context)

    # Increment bars-held counter once per call and rebuild context so all
    # downstream return paths (which copy from meta) carry the new value.
    bars_held = increment_bars_held(ts)
    context = ContextSnapshot(
        state=context.state,
        soft_sl_price=context.soft_sl_price,
        meta=ts.to_meta(),
    )
    _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

    # Soft SL: prefer ContextSnapshot direct field, fall back to ts
    soft_sl = context.soft_sl_price or to_decimal_or_none(ts.soft_sl_price)
    original_soft_sl = to_decimal_or_none(ts.original_soft_sl) or soft_sl

    moved_sl = ts.moved_sl_to_entry
    pending_candle_sl = ts.pending_candle_sl

    # Lock profit price: precompute from original SL (never changes)
    lock_profit_price = to_decimal_or_none(ts.lock_profit_price)
    if lock_profit_price is None and original_soft_sl and entry_price:
        lock_profit_price = compute_price_at_rr(
            entry_price,
            original_soft_sl,
            lock_profit_rr,
            taker_fee,
            maker_fee,
            is_taker_exit=True,
        )

    # -------------------------------------------------
    # STEP 0: pending candle SL — exit at THIS candle's open
    # -------------------------------------------------
    if pending_candle_sl and open_price is not None:
        new_ctx = ContextSnapshot(state=SCANNING)
        return AnalysisResult(
            actions=[ClosePosition(symbol=symbol, reason="CLOSE_BY_CANDLE_SL", price=open_price)],
            new_context=new_ctx,
        )

    # -------------------------------------------------
    # STEP 1: Move SL to lock profit when high reaches +move_sl_rr * R
    # TP targets are handled entirely by the exchange as limit orders.
    # -------------------------------------------------
    if (not moved_sl) and high is not None and soft_sl is not None and original_soft_sl is not None:
        move_trigger = compute_price_at_rr(
            entry_price,
            original_soft_sl,
            move_sl_rr,
            taker_fee,
            maker_fee,
            is_taker_exit=False,
        )
        if move_trigger is not None and high >= move_trigger and lock_profit_price is not None:
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
                            f"MOVE_SL_LOCK_PROFIT (high={high} >= {move_trigger} = +{move_sl_rr}R, "
                            f"new_sl={lock_profit_price} = +{lock_profit_rr}R)"
                        ),
                    )
                ],
                new_context=new_ctx,
            )

    # -------------------------------------------------
    # STEP 2: Candle-close SL — set flag, exit next candle's open
    # Skipped in "touch" mode: exchange-level stop handles it on touch.
    # -------------------------------------------------
    if (
        sl_trigger_mode != SL_TRIGGER_TOUCH
        and soft_sl is not None
        and close is not None
        and close <= soft_sl
    ):
        new_ts = TradeState.from_meta(context.meta)
        new_ts.pending_candle_sl = True
        new_ctx = ContextSnapshot(state=context.state, soft_sl_price=soft_sl, meta=new_ts.to_meta())
        return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

    # -------------------------------------------------
    # STEP 3: Max holding period — force-close stale positions at market.
    # Fires LAST so any specific exit above takes priority on the same bar.
    # -------------------------------------------------
    max_holding_result = maybe_force_close_max_holding(
        symbol=symbol,
        bars_held=bars_held,
        max_bars=max_holding_bars,
        close_price=close,
    )
    if max_holding_result is not None:
        return max_holding_result

    return _noop
