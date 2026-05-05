# app/trading/strategy/rsi_no_retest_entry.py
"""
Layer 2: Core Logic - RSI No Retest Strategy — Entry Logic
==========================================================

Module-level functions for the entry state machine:
SCANNING -> CONFIRMING -> OpenPosition (or reset to SCANNING).

All functions receive explicit parameters instead of accessing `self`.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import structlog

from app.core.actions import DoNothing, OpenPosition
from app.core.analysis_result import AnalysisResult
from app.core.constants import SL_TRIGGER_CANDLE_CLOSE, SL_TRIGGER_TOUCH
from app.core.context import CONFIRMING, SCANNING
from app.core.snapshots import ContextSnapshot
from app.core.utils import to_decimal_or_none
from app.data.indicators import Indicators
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Reclaim & pullback detection
# ---------------------------------------------------------------------------


def detect_reclaim(df_ind: pd.DataFrame, *, debug_enabled: bool = False) -> bool:
    """Return True if the confirmed candle (-2) closed above EMA21
    while the prior candle (-3) closed at or below EMA21."""
    if len(df_ind) < 3:
        return False

    confirmed_close_candle = df_ind.iloc[-2]
    prior_candle = df_ind.iloc[-3]

    curr_close = confirmed_close_candle.get("close")
    curr_ema21 = confirmed_close_candle.get("ema21")
    prior_close = prior_candle.get("close")
    prior_ema21 = prior_candle.get("ema21")

    if curr_close is None or curr_ema21 is None or prior_close is None or prior_ema21 is None:
        return False

    ts_prior = prior_candle.name if hasattr(prior_candle, "name") else "N/A"
    ts_closed = confirmed_close_candle.name if hasattr(confirmed_close_candle, "name") else "N/A"
    if debug_enabled:
        logger.debug(
            f"DEBUG RECLAIM: Prior(-3)={prior_close}/{prior_ema21} (TS={ts_prior}) "
            f"| Closed(-2)={curr_close}/{curr_ema21} (TS={ts_closed})"
        )

    return (prior_close <= prior_ema21) and (curr_close > curr_ema21)


def pullback_filter(
    df_ind: pd.DataFrame,
    lookback: int,
    max_above_ema21: int,
) -> tuple[bool, int]:
    """Check that the lookback window had a prolonged decline.

    Returns ``(passed, above_count)`` where *passed* is True when the
    number of candles closing above EMA21 is within the allowed limit.
    """
    if len(df_ind) < lookback + 2:
        return False, 0
    window = df_ind.iloc[-(lookback + 1) : -1]
    closes = window["close"]
    ema21s = window["ema21"]
    above = int((closes > ema21s).sum())
    return above <= max_above_ema21, above


# ---------------------------------------------------------------------------
# SL / TP computation helpers (entry-time)
# ---------------------------------------------------------------------------


def compute_entry_sl(
    df_ind: pd.DataFrame,
    sl_mode: str,
    lookback: int,
    sl_buffer_pct: float,
    indicators: Indicators,
) -> tuple[Decimal | None, str]:
    """Compute the soft SL price for a new entry.

    Returns ``(sl_price, sl_mode_used)`` — *sl_mode_used* may differ from
    *sl_mode* when the primary mode fails and we fall back to ``lowest_wick``.
    """
    sl = _raw_sl(df_ind, sl_mode, lookback, indicators)
    used_mode = sl_mode

    if sl is None:
        sl = _raw_sl(df_ind, "lowest_wick", lookback, indicators)
        used_mode = "lowest_wick"

    if sl is None:
        return None, used_mode

    if sl_buffer_pct and sl_buffer_pct > 0:
        sl = sl * Decimal(str(1 - sl_buffer_pct))
    return sl, used_mode


def _raw_sl(
    df_ind: pd.DataFrame,
    sl_mode: str,
    lookback: int,
    indicators: Indicators,
) -> Decimal | None:
    """Compute raw (unbuffered) SL for the given *sl_mode*."""
    if sl_mode == "lowest_wick":
        window = df_ind.iloc[-(lookback + 1) : -1]
        if "low" not in window.columns:
            return None
        return to_decimal_or_none(window["low"].min())

    if sl_mode == "lowest_close":
        window = df_ind.iloc[-(lookback + 1) : -1]
        if "close" not in window.columns:
            return None
        return to_decimal_or_none(window["close"].min())

    # Default: rsi_ema9
    last = Indicators.last(df_ind)
    if not last:
        return None
    rsi_ema9 = last.get("rsi_ema9")
    if rsi_ema9 is None:
        return None
    return indicators.calculate_price_at_rsi(df_ind, float(rsi_ema9))


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
# Main entry check — called from analyze()
# ---------------------------------------------------------------------------


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
    """Run the SCANNING/CONFIRMING state machine for entries.

    Returns an ``AnalysisResult`` — either ``OpenPosition`` or ``DoNothing``.
    """
    _noop = AnalysisResult(actions=[DoNothing()], new_context=context)
    current_state = context.state

    # --- debug row ---
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
                f"[{symbol}] DEBUG: Transition to CONFIRMING " f"(Reclaim OK, above={above_count}/{max_above_ema21})"
            )
        current_state = CONFIRMING

    # --- CONFIRMING ---
    if current_state == CONFIRMING:
        if rsi_ema9 is None or rsi_wma45 is None:
            new_ctx = ContextSnapshot(state=CONFIRMING, meta=dict(context.meta or {}))
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

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

        # Compute SL
        sl_price, _used_mode = compute_entry_sl(df_ind, sl_mode, lookback, sl_buffer_pct, indicators)

        if sl_price is None:
            if debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - No SL computed - Reset to SCANNING")
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

        entry_price = close

        tp1_price = compute_price_at_rr(entry_price, sl_price, tp1_rr, taker_fee, maker_fee, is_taker_exit=False)
        tp2_price = compute_price_at_rr(entry_price, sl_price, tp2_rr, taker_fee, maker_fee, is_taker_exit=False)
        tp3_price = compute_price_at_rr(entry_price, sl_price, tp3_rr, taker_fee, maker_fee, is_taker_exit=False)

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

        # Dual SL system
        soft_sl_price = sl_price
        disaster_sl_price = None
        if soft_sl_price is not None:
            if sl_trigger_mode == SL_TRIGGER_TOUCH:
                # Exchange stop sits at the soft-SL level and fires on touch.
                disaster_sl_price = soft_sl_price
            else:
                soft_sl_distance = entry_price - soft_sl_price
                disaster_sl_price = entry_price - (soft_sl_distance * Decimal(str(disaster_sl_multiplier)))
                # Floor at 1% of entry — a stop loss price must never be zero or negative
                min_sl = entry_price * Decimal("0.01")
                if disaster_sl_price < min_sl:
                    disaster_sl_price = min_sl

        lock_profit_price = compute_price_at_rr(
            entry_price,
            soft_sl_price,
            lock_profit_rr,
            taker_fee,
            maker_fee,
            is_taker_exit=True,
        )

        tp_prices = [p for p in [tp1_price, tp2_price, tp3_price] if p is not None]
        new_meta = {
            "entry_price": entry_price,
            "sl_price": soft_sl_price,
            "soft_sl_price": soft_sl_price,
            "original_soft_sl": soft_sl_price,
            "disaster_sl_price": disaster_sl_price,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "tp3_price": tp3_price,
            "lock_profit_price": lock_profit_price,
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
            "rsi_spread": spread,
            "sl_mode": _used_mode,
            "tp_allocations": tp_allocations,
        }
        new_ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl_price, meta=new_meta)

        logger.info(
            f"[{symbol}] DEBUG: BUY SIGNAL GENERATED @ {entry_price} "
            f"(SL={disaster_sl_price}, RSI_EMA9={float(rsi_ema9):.2f}, "
            f"RSI_WMA45={float(rsi_wma45):.2f}, Spread={spread:.2f})"
        )

        _debug_row["signal"] = "BUY"
        debug_rows.append(_debug_row)

        # Build indicator snapshot for notification
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
                    side="BUY",
                    entry_price=entry_price,
                    sl_price=disaster_sl_price,
                    soft_sl_price=soft_sl_price,
                    tp_prices=tp_prices,
                    tp_allocations=tp_allocations,
                    lock_profit_price=lock_profit_price,
                    signal_class=2,
                    reason=f"NO-RETEST BUY (spread={spread:.2f} >= {rsi_spread_min})",
                    indicators=_indicators,
                )
            ],
            new_context=new_ctx,
        )

    return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))
