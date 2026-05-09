# app/trading/strategy/rsi_no_retest_fade/entry.py
"""
Layer 2: Core Logic - RSI No Retest FADE Strategy — Entry Logic
===============================================================

Same trigger as ``rsi_no_retest`` (the LONG parent). Same lookback,
same reclaim detection, same bullish RSI spread filter. Only the
emitted action differs: we open a SHORT instead of a LONG.

The detection helpers are IMPORTED from the parent rather than copied.
That coupling is deliberate: if the parent's reclaim/pullback logic
ever changes, the fade should change with it — they are by definition
the same trigger.

SL / TP math uses ``SLTPCalculator`` with ``side=SIDE_SELL`` so the
levels land on the short side of entry. ``TradeState`` carries
position state through ``ContextSnapshot.meta`` (same convention as
``rsi_no_retest_short``).
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import structlog

from app.core.actions import SIDE_SELL, DoNothing, OpenPosition
from app.core.analysis_result import AnalysisResult
from app.core.constants import SL_TRIGGER_CANDLE_CLOSE, SL_TRIGGER_TOUCH
from app.core.context import CONFIRMING, SCANNING
from app.core.snapshots import ContextSnapshot
from app.data.indicators import Indicators
from app.trading.sl_tp_calculator import SLTPCalculator

# Trigger detection is REUSED from the LONG parent — identical bars by
# construction. Don't copy; the experiment requires they stay locked.
from app.trading.strategy.rsi_no_retest.entry import (
    detect_reclaim,
    pullback_filter,
)
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations
from app.trading.strategy.utils.trade_state import TradeState

logger = structlog.get_logger()


def compute_entry_sl(
    df_ind: pd.DataFrame,
    sl_mode: str,
    lookback: int,
    sl_buffer_pct: float,
) -> tuple[Decimal | None, str]:
    """SHORT-direction soft SL: sits ABOVE entry.

    Modes:
    - ``"highest_close"`` (default): max close of the last ``lookback`` candles
    - ``"highest_wick"``: max high (wick) of the last ``lookback`` candles

    Falls back to ``highest_wick`` if the close-based mode returns None.
    """
    used_mode = sl_mode
    sl = _raw_sl(df_ind, sl_mode, lookback)

    if sl is None:
        sl = _raw_sl(df_ind, "highest_wick", lookback)
        used_mode = "highest_wick"

    if sl is None:
        return None, used_mode

    if sl_buffer_pct and sl_buffer_pct > 0:
        # Buffer pushes SL further AWAY from entry — higher for SHORT.
        sl = sl * Decimal(str(1 + sl_buffer_pct))
    return sl, used_mode


def _raw_sl(df_ind: pd.DataFrame, sl_mode: str, lookback: int) -> Decimal | None:
    if sl_mode == "highest_wick":
        return SLTPCalculator.compute_soft_sl(df_ind, side=SIDE_SELL, lookback=lookback, mode="swing")
    return SLTPCalculator.compute_soft_sl(df_ind, side=SIDE_SELL, lookback=lookback, mode="close")


def check_entry(
    *,
    symbol: str,
    df_ind: pd.DataFrame,
    context: ContextSnapshot,
    close: Decimal,
    ema21: Decimal,
    rsi_ema9,
    rsi_wma45,
    # strategy params
    lookback: int,
    max_above_ema21: int,
    rsi_spread_min: float,
    sl_mode: str,
    sl_buffer_pct: float,
    disaster_sl_multiplier: float,
    sl_trigger_mode: str = SL_TRIGGER_CANDLE_CLOSE,
    tp1_rr: Decimal,
    tp2_rr: Decimal,
    tp3_rr: Decimal,
    tp_count: int,
    tp1_close_pct: float,
    tp2_close_pct: float,
    move_sl_rr: Decimal,
    lock_profit_rr: Decimal,
    taker_fee: Decimal,
    maker_fee: Decimal,
    indicators: Indicators,
    debug_enabled: bool,
    debug_rows: list[dict],
    df_ind_index_last,
) -> AnalysisResult:
    """SCANNING/CONFIRMING state machine for FADE entries.

    Identical control-flow to the LONG parent: detect reclaim, run
    pullback filter, require bullish RSI spread. The only divergence
    is the emitted action: ``OpenPosition(side=SIDE_SELL)`` with SHORT
    SL/TP geometry.
    """
    _noop = AnalysisResult(actions=[DoNothing()], new_context=context)
    current_state = context.state

    _ts = str(df_ind_index_last) if df_ind_index_last is not None else None
    _debug_row: dict = {
        "timestamp": _ts,
        "symbol": symbol,
        "close": float(close),
        "ema21": float(ema21),
        "rsi_ema9": float(rsi_ema9) if rsi_ema9 is not None else None,
        "rsi_wma45": float(rsi_wma45) if rsi_wma45 is not None else None,
        "spread": None,
        "above_count": None,
        "max_above_ema21": max_above_ema21,
        "rsi_spread_min": rsi_spread_min,
        "reclaim_detected": False,
        "pullback_ok": False,
        "spread_ok": False,
        "signal": "NONE",
    }

    # --- SCANNING ---
    if current_state == SCANNING:
        if not detect_reclaim(df_ind, debug_enabled=debug_enabled):
            if debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Reclaim not detected.")
            debug_rows.append(_debug_row)
            return _noop

        _debug_row["reclaim_detected"] = True
        pullback_ok, above_count = pullback_filter(df_ind, lookback, max_above_ema21)
        _debug_row["above_count"] = above_count
        _debug_row["pullback_ok"] = pullback_ok

        if not pullback_ok:
            if debug_enabled:
                logger.debug(
                    f"[{symbol}] DEBUG: Reclaim detected but failed Pullback Filter "
                    f"(above={above_count} > max_above_ema21={max_above_ema21})."
                )
            debug_rows.append(_debug_row)
            return _noop

        if debug_enabled:
            logger.debug(
                f"[{symbol}] DEBUG: Transition to CONFIRMING "
                f"(Reclaim OK, above={above_count}/{max_above_ema21})"
            )
        current_state = CONFIRMING

    # --- CONFIRMING ---
    if current_state == CONFIRMING:
        if rsi_ema9 is None or rsi_wma45 is None:
            new_ctx = ContextSnapshot(state=CONFIRMING, meta=dict(context.meta or {}))
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

        # Bullish spread: same as parent (EMA9 above WMA45).
        spread = float(rsi_ema9) - float(rsi_wma45)
        _debug_row["spread"] = spread
        if spread < rsi_spread_min:
            if debug_enabled:
                logger.debug(
                    f"[{symbol}] DEBUG: Failed Confirmation - "
                    f"RSI_EMA9={float(rsi_ema9):.2f}, RSI_WMA45={float(rsi_wma45):.2f}, "
                    f"Spread={spread:.2f} < rsi_spread_min={rsi_spread_min} - Reset to SCANNING"
                )
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

        _debug_row["spread_ok"] = True

        sl_price, _used_mode = compute_entry_sl(df_ind, sl_mode, lookback, sl_buffer_pct)
        if sl_price is None or sl_price <= close:
            if debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - No valid SHORT SL - Reset to SCANNING")
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

        entry_price = close

        tp1_price = SLTPCalculator.compute_tp_price(
            entry_price=entry_price, sl_price=sl_price, side=SIDE_SELL,
            rr_ratio=tp1_rr, taker_fee=taker_fee, exit_fee=maker_fee,
        )
        tp2_price = SLTPCalculator.compute_tp_price(
            entry_price=entry_price, sl_price=sl_price, side=SIDE_SELL,
            rr_ratio=tp2_rr, taker_fee=taker_fee, exit_fee=maker_fee,
        )
        tp3_price = SLTPCalculator.compute_tp_price(
            entry_price=entry_price, sl_price=sl_price, side=SIDE_SELL,
            rr_ratio=tp3_rr, taker_fee=taker_fee, exit_fee=maker_fee,
        )

        tp2_pct = tp2_close_pct if tp2_close_pct < 1.0 else 0.5
        tp_allocations = build_tp_allocations(tp_count, tp1_close_pct, tp2_pct)
        if tp_count == 1:
            tp2_price = None
            tp3_price = None
        elif tp_count == 2:
            tp3_price = None

        if tp1_price is None:
            if debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - Invalid TP - Reset to SCANNING")
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

        soft_sl_price = sl_price
        if sl_trigger_mode == SL_TRIGGER_TOUCH:
            disaster_sl_price = soft_sl_price
        else:
            disaster_sl_price = SLTPCalculator.compute_disaster_sl(
                entry_price=entry_price,
                soft_sl_price=soft_sl_price,
                side=SIDE_SELL,
                multiplier=Decimal(str(disaster_sl_multiplier)),
            )

        lock_profit_price = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry_price,
            soft_sl_price=soft_sl_price,
            side=SIDE_SELL,
            lock_profit_rr=lock_profit_rr,
            taker_fee=taker_fee,
        )

        move_trigger = SLTPCalculator.compute_tp_price(
            entry_price=entry_price,
            sl_price=soft_sl_price,
            side=SIDE_SELL,
            rr_ratio=move_sl_rr,
            taker_fee=taker_fee,
            exit_fee=maker_fee,
        )

        tp_prices = [p for p in [tp1_price, tp2_price, tp3_price] if p is not None]
        new_ts = TradeState(
            entry_price=entry_price,
            sl_price=soft_sl_price,
            soft_sl_price=soft_sl_price,
            original_soft_sl=soft_sl_price,
            disaster_sl_price=disaster_sl_price,
            lock_profit_price=lock_profit_price,
            move_trigger=move_trigger,
            tp_allocations=tp_allocations,
        )
        new_ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl_price, meta=new_ts.to_meta())

        logger.info(
            f"[{symbol}] DEBUG: SELL (FADE) SIGNAL GENERATED @ {entry_price} "
            f"(SL={disaster_sl_price}, RSI_EMA9={float(rsi_ema9):.2f}, "
            f"RSI_WMA45={float(rsi_wma45):.2f}, Spread={spread:.2f})"
        )

        _debug_row["signal"] = "SELL"
        debug_rows.append(_debug_row)

        _, above_count = pullback_filter(df_ind, lookback, max_above_ema21)
        _indicators = {
            "rsi_ema9": float(rsi_ema9),
            "rsi_wma45": float(rsi_wma45),
            "spread": spread,
            "above_ema21": above_count,
        }

        return AnalysisResult(
            actions=[
                OpenPosition(
                    symbol=symbol,
                    side=SIDE_SELL,
                    entry_price=entry_price,
                    sl_price=disaster_sl_price,
                    soft_sl_price=soft_sl_price,
                    tp_prices=tp_prices,
                    tp_allocations=tp_allocations,
                    lock_profit_price=lock_profit_price,
                    signal_class=2,
                    reason=f"NO-RETEST FADE (spread={spread:.2f} >= {rsi_spread_min})",
                    indicators=_indicators,
                )
            ],
            new_context=new_ctx,
        )

    return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))
