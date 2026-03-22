# app/trading/strategy/rsi_momentum_exit.py
"""
Exit management logic for RsiMomentumStrategy (SHORT positions).

Extracted from RsiMomentumStrategy._manage_exit() as a module-level function.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.core.actions import (
    EXIT_CLOSE_BY_CANDLE_SL,
    SIDE_SELL,
    ClosePosition,
    DoNothing,
    MoveSL,
)
from app.core.analysis_result import AnalysisResult
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.utils import to_decimal_or_none
from app.trading.sl_tp_calculator import SLTPCalculator
from app.trading.strategy.utils.trade_state import TradeState


def manage_exit(
    symbol: str,
    df_ind: pd.DataFrame,
    position: PositionSnapshot,
    context: ContextSnapshot,
    *,
    move_sl_rr: float,
    lock_profit_rr: float,
    taker_fee: Decimal,
    maker_fee: Decimal,
) -> AnalysisResult:
    """Manage exit for an open SHORT position.

    Parameters
    ----------
    symbol : str
        Trading pair symbol.
    df_ind : pd.DataFrame
        DataFrame with computed indicators.
    position : PositionSnapshot
        Current position snapshot.
    context : ContextSnapshot
        Current context with trade state metadata.
    move_sl_rr : float
        R:R trigger to move SL to lock-profit level.
    lock_profit_rr : float
        R:R level for the locked-profit SL.
    taker_fee : Decimal
        Taker fee rate.
    maker_fee : Decimal
        Maker fee rate.
    """
    ts = TradeState.from_meta(context.meta)

    entry_price = to_decimal_or_none(ts.entry_price)
    if entry_price is None:
        return AnalysisResult(actions=[DoNothing()], new_context=context)

    soft_sl = context.soft_sl_price or to_decimal_or_none(ts.soft_sl_price)
    original_soft_sl = to_decimal_or_none(ts.original_soft_sl) or soft_sl
    moved_sl = ts.moved_sl_to_entry
    pending_candle_sl = ts.pending_candle_sl
    lock_profit_price = to_decimal_or_none(ts.lock_profit_price)

    last = df_ind.iloc[-1]
    close = to_decimal_or_none(last.get("close"))
    low = to_decimal_or_none(last.get("low"))
    open_price = to_decimal_or_none(last.get("open"))

    if lock_profit_price is None and original_soft_sl and entry_price:
        lock_profit_price = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry_price,
            soft_sl_price=original_soft_sl,
            side=SIDE_SELL,
            lock_profit_rr=Decimal(str(lock_profit_rr)),
            taker_fee=taker_fee,
        )

    # -- STEP 0: pending candle SL -- close at this candle's open
    if pending_candle_sl and open_price is not None:
        return AnalysisResult(
            actions=[ClosePosition(symbol=symbol, reason=EXIT_CLOSE_BY_CANDLE_SL, price=open_price)],
            new_context=ContextSnapshot(state=SCANNING),
        )

    # -- STEP 1: Move SL to lock-profit when price drops to trigger
    if not moved_sl and low is not None and soft_sl is not None and original_soft_sl is not None:
        move_trigger = to_decimal_or_none(ts.move_trigger)
        if move_trigger is None:
            move_trigger = SLTPCalculator.compute_tp_price(
                entry_price=entry_price,
                sl_price=original_soft_sl,
                side=SIDE_SELL,
                rr_ratio=Decimal(str(move_sl_rr)),
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
                        reason=f"MOVE_SL_LOCK_PROFIT (low={low} <= {move_trigger} = -{move_sl_rr}R, new_sl={lock_profit_price} = -{lock_profit_rr}R)",
                    )
                ],
                new_context=new_ctx,
            )

    # -- STEP 2: Candle-close SL -- flag exit for next candle
    if soft_sl is not None and close is not None and close >= soft_sl:
        new_ts = TradeState.from_meta(context.meta)
        new_ts.pending_candle_sl = True
        new_ctx = ContextSnapshot(state=context.state, soft_sl_price=soft_sl, meta=new_ts.to_meta())
        return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

    return AnalysisResult(actions=[DoNothing()], new_context=context)
