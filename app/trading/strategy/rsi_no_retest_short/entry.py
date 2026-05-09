# app/trading/strategy/rsi_no_retest_short/entry.py
"""
Layer 2: Core Logic - RSI No Retest SHORT Strategy — Entry Logic
================================================================

Module-level functions for the SHORT entry state machine. Pure
inversion of ``rsi_no_retest/entry.py`` — same trigger structure with
direction flipped:

- Detect "break-down": confirmed candle (-2) closed BELOW EMA21 while
  the prior candle (-3) closed AT or ABOVE EMA21.
- Pullback filter: most of the lookback window closed ABOVE EMA21 (i.e.
  prolonged rise), with at most ``nr_max_below_ema21`` bars below.
- RSI confirmation: bearish spread (RSI_WMA45 - RSI_EMA9) >= rsi_spread_min.
- Open SHORT at close; soft SL above entry (highest close of lookback).

Uses ``SLTPCalculator`` (already direction-aware) for all SL/TP math
instead of the ad-hoc helpers in the LONG variant. Uses the typed
``TradeState`` pattern for meta read/write.
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
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations
from app.trading.strategy.utils.trade_state import TradeState

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Break-down & pullback detection (mirror of detect_reclaim / pullback_filter)
# ---------------------------------------------------------------------------


def detect_breakdown(df_ind: pd.DataFrame, *, debug_enabled: bool = False) -> bool:
    """Confirmed candle (-2) closed BELOW EMA21 while prior (-3) was AT/ABOVE.

    Mirrors ``detect_reclaim`` from the LONG variant with the inequality
    flipped: prior >= EMA21 then current < EMA21.
    """
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

    if debug_enabled:
        ts_prior = prior_candle.name if hasattr(prior_candle, "name") else "N/A"
        ts_closed = confirmed_close_candle.name if hasattr(confirmed_close_candle, "name") else "N/A"
        logger.debug(
            f"DEBUG BREAKDOWN: Prior(-3)={prior_close}/{prior_ema21} (TS={ts_prior}) "
            f"| Closed(-2)={curr_close}/{curr_ema21} (TS={ts_closed})"
        )

    return (prior_close >= prior_ema21) and (curr_close < curr_ema21)


def pullback_filter(
    df_ind: pd.DataFrame,
    lookback: int,
    max_below_ema21: int,
) -> tuple[bool, int]:
    """Check that the lookback window had a prolonged rise.

    Returns ``(passed, below_count)`` where *passed* is True when the
    number of candles closing BELOW EMA21 is within the allowed limit.
    Mirror of LONG's ``pullback_filter`` with the inequality flipped.
    """
    if len(df_ind) < lookback + 2:
        return False, 0
    window = df_ind.iloc[-(lookback + 1) : -1]
    closes = window["close"]
    ema21s = window["ema21"]
    below = int((closes < ema21s).sum())
    return below <= max_below_ema21, below


# ---------------------------------------------------------------------------
# SL helpers — direction-aware via SLTPCalculator
# ---------------------------------------------------------------------------


def compute_entry_sl(
    df_ind: pd.DataFrame,
    sl_mode: str,
    lookback: int,
    sl_buffer_pct: float,
) -> tuple[Decimal | None, str]:
    """Compute the soft SL price for a SHORT entry.

    For SHORT the SL sits ABOVE entry. Modes:
    - ``"highest_close"`` (default): max close of the last ``lookback`` candles
    - ``"highest_wick"``: max high (wick) of the last ``lookback`` candles

    Falls back from ``highest_close`` to ``highest_wick`` if the close
    column is missing (parallels the LONG fallback semantics).

    Returns ``(sl_price, sl_mode_used)``.
    """
    used_mode = sl_mode
    sl = _raw_sl(df_ind, sl_mode, lookback)

    if sl is None:
        sl = _raw_sl(df_ind, "highest_wick", lookback)
        used_mode = "highest_wick"

    if sl is None:
        return None, used_mode

    if sl_buffer_pct and sl_buffer_pct > 0:
        # Buffer pushes SL further AWAY from entry (i.e. higher for SHORT).
        sl = sl * Decimal(str(1 + sl_buffer_pct))
    return sl, used_mode


def _raw_sl(df_ind: pd.DataFrame, sl_mode: str, lookback: int) -> Decimal | None:
    """Raw (unbuffered) SHORT SL via SLTPCalculator.compute_soft_sl."""
    if sl_mode == "highest_wick":
        return SLTPCalculator.compute_soft_sl(df_ind, side=SIDE_SELL, lookback=lookback, mode="swing")
    # Default: highest_close
    return SLTPCalculator.compute_soft_sl(df_ind, side=SIDE_SELL, lookback=lookback, mode="close")


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
    max_below_ema21: int,
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
    """SCANNING/CONFIRMING state machine for SHORT entries.

    Returns ``OpenPosition(side=SIDE_SELL)`` when all conditions clear,
    else ``DoNothing``.
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
        "below_count": None,
        "max_below_ema21": max_below_ema21,
        "rsi_spread_min": rsi_spread_min,
        "breakdown_detected": False,
        "pullback_ok": False,
        "spread_ok": False,
        "signal": "NONE",
    }

    # --- SCANNING ---
    if current_state == SCANNING:
        if not detect_breakdown(df_ind, debug_enabled=debug_enabled):
            if debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Breakdown not detected.")
            debug_rows.append(_debug_row)
            return _noop

        _debug_row["breakdown_detected"] = True
        pullback_ok, below_count = pullback_filter(df_ind, lookback, max_below_ema21)
        _debug_row["below_count"] = below_count
        _debug_row["pullback_ok"] = pullback_ok

        if not pullback_ok:
            if debug_enabled:
                logger.debug(
                    f"[{symbol}] DEBUG: Breakdown detected but failed Pullback Filter "
                    f"(below={below_count} > max_below_ema21={max_below_ema21})."
                )
            debug_rows.append(_debug_row)
            return _noop

        if debug_enabled:
            logger.debug(
                f"[{symbol}] DEBUG: Transition to CONFIRMING "
                f"(Breakdown OK, below={below_count}/{max_below_ema21})"
            )
        current_state = CONFIRMING

    # --- CONFIRMING ---
    if current_state == CONFIRMING:
        if rsi_ema9 is None or rsi_wma45 is None:
            new_ctx = ContextSnapshot(state=CONFIRMING, meta=dict(context.meta or {}))
            debug_rows.append(_debug_row)
            return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

        # Bearish spread: WMA45 sits ABOVE EMA9
        spread = float(rsi_wma45) - float(rsi_ema9)
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

        # TP prices via SLTPCalculator (direction-aware). TPs are limit orders -> maker fee on exit.
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

        # Dual SL: disaster sits FURTHER ABOVE entry; in touch mode it collapses onto soft SL.
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

        # Lock-profit price: SL moves BELOW entry by lock_profit_rr * R. stop_market -> taker fee.
        lock_profit_price = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry_price,
            soft_sl_price=soft_sl_price,
            side=SIDE_SELL,
            lock_profit_rr=lock_profit_rr,
            taker_fee=taker_fee,
        )

        # Pre-compute move_trigger so manage_exit doesn't recompute every bar.
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
            f"[{symbol}] DEBUG: SELL SIGNAL GENERATED @ {entry_price} "
            f"(SL={disaster_sl_price}, RSI_EMA9={float(rsi_ema9):.2f}, "
            f"RSI_WMA45={float(rsi_wma45):.2f}, Spread={spread:.2f})"
        )

        _debug_row["signal"] = "SELL"
        debug_rows.append(_debug_row)

        _, below_count = pullback_filter(df_ind, lookback, max_below_ema21)
        _indicators = {
            "rsi_ema9": float(rsi_ema9),
            "rsi_wma45": float(rsi_wma45),
            "spread": spread,
            "below_ema21": below_count,
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
                    reason=f"NO-RETEST SHORT (spread={spread:.2f} >= {rsi_spread_min})",
                    indicators=_indicators,
                )
            ],
            new_context=new_ctx,
        )

    return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))
