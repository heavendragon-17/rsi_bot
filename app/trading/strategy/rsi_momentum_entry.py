# app/trading/strategy/rsi_momentum_entry.py
"""
Entry logic for RsiMomentumStrategy (SHORT entries only).

Extracted from RsiMomentumStrategy._check_entry() as a module-level function.

Entry conditions (all must hold simultaneously):
  S1: EMA9 crossed below WMA45 on this candle *OR* alignment still holds
      from a previous crossover candle (flexible persistence).
  S2: RSI < EMA9
  S3: EMA9 < WMA45
  S4: (WMA45 - EMA9) > spread_threshold  (default 2.5)
  S5: Bearish RSI divergence in last 30 candles
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
import structlog

from app.core.actions import (
    SIDE_SELL,
    DoNothing,
    OpenPosition,
)
from app.core.analysis_result import AnalysisResult
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot
from app.core.utils import to_decimal_or_none
from app.data.indicators import Indicators
from app.trading.sl_tp_calculator import SLTPCalculator
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations
from app.trading.strategy.utils.trade_state import TradeState

if TYPE_CHECKING:
    from app.trading.strategy.rsi_momentum import RsiMomentumConfig

logger = structlog.get_logger()


def check_entry(
    symbol: str,
    df_ind: pd.DataFrame,
    context: ContextSnapshot,
    *,
    cfg: RsiMomentumConfig,
    indicators: Indicators,
    taker_fee: Decimal,
    maker_fee: Decimal,
    current_index: int | None = None,
) -> AnalysisResult:
    """Check SHORT entry conditions S1-S5 and return an AnalysisResult.

    Parameters
    ----------
    symbol : str
        Trading pair symbol.
    df_ind : pd.DataFrame
        DataFrame with computed indicators.
    context : ContextSnapshot
        Current context with trade state metadata.
    cfg : RsiMomentumConfig
        Strategy configuration dataclass.
    indicators : Indicators
        Indicators instance for alignment/crossover/divergence checks.
    taker_fee : Decimal
        Taker fee rate.
    maker_fee : Decimal
        Maker fee rate.
    """
    ts = TradeState.from_meta(context.meta)
    _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

    # -- S2 + S3: Alignment check
    if not indicators.check_alignment(df_ind, direction="bearish", current_index=current_index):
        # Alignment broken -> reset crossover flag
        if ts.crossover_detected:
            ts.crossover_detected = False
            return AnalysisResult(
                actions=[DoNothing()],
                new_context=ContextSnapshot(state=SCANNING, meta=ts.to_meta()),
            )
        return _noop

    # -- S1: Crossover or persistent alignment
    crossover_now = indicators.detect_crossover(df_ind, direction="bearish", current_index=current_index)
    crossover_before = ts.crossover_detected

    if not crossover_now and not crossover_before:
        return _noop

    # -- S4: Spread constraint
    _idx = current_index if current_index is not None else -1
    ema = df_ind["rsi_ema9"].values[_idx]
    wma = df_ind["rsi_wma45"].values[_idx]
    if pd.isna(ema) or pd.isna(wma):
        return _noop

    spread = float(wma) - float(ema)
    if spread <= cfg.spread_threshold:
        return _noop

    # -- S5: Bearish RSI divergence
    if not indicators.detect_bearish_divergence(
        df_ind,
        lookback=cfg.divergence_lookback,
        pivot_strength=cfg.pivot_strength,
        current_index=current_index,
    ):
        # Preserve crossover flag so persistence still works
        ts.crossover_detected = crossover_now or crossover_before
        return AnalysisResult(
            actions=[DoNothing()],
            new_context=ContextSnapshot(state=SCANNING, meta=ts.to_meta()),
        )

    # -- All conditions met -- compute SL/TP
    close = to_decimal_or_none(df_ind["close"].values[_idx])
    if close is None:
        return _noop

    entry_price = close

    # Soft SL: highest high of last sl_lookback candles
    soft_sl = SLTPCalculator.compute_soft_sl(df_ind, side=SIDE_SELL, lookback=cfg.sl_lookback, current_index=current_index)
    if soft_sl is None:
        logger.warning("rsi_momentum.no_soft_sl", symbol=symbol)
        return _noop

    # Zero risk distance -> skip
    if soft_sl <= entry_price:
        logger.info(
            "rsi_momentum.zero_risk_distance",
            symbol=symbol,
            entry=str(entry_price),
            soft_sl=str(soft_sl),
        )
        return _noop

    # Disaster SL
    disaster_sl = SLTPCalculator.compute_disaster_sl(
        entry_price=entry_price,
        soft_sl_price=soft_sl,
        side=SIDE_SELL,
        multiplier=Decimal(str(cfg.disaster_sl_multiplier)),
    )

    # TP prices (limit orders -> maker fee for exit)
    tp_rrs = [cfg.tp1_rr, cfg.tp2_rr, cfg.tp3_rr]
    tp_prices_all = []
    for rr in tp_rrs[: cfg.tp_count]:
        tp = SLTPCalculator.compute_tp_price(
            entry_price=entry_price,
            sl_price=soft_sl,
            side=SIDE_SELL,
            rr_ratio=Decimal(str(rr)),
            taker_fee=taker_fee,
            exit_fee=maker_fee,
        )
        if tp is not None:
            tp_prices_all.append(tp)

    if not tp_prices_all:
        return _noop

    # TP allocations
    tp_allocations = build_tp_allocations(cfg.tp_count, cfg.tp1_close_pct, cfg.tp2_close_pct)

    # Lock-profit price (stop_market -> taker fee)
    lock_profit_price = SLTPCalculator.compute_lock_profit_price(
        entry_price=entry_price,
        soft_sl_price=soft_sl,
        side=SIDE_SELL,
        lock_profit_rr=Decimal(str(cfg.lock_profit_rr)),
        taker_fee=taker_fee,
    )

    # Pre-compute move_trigger so manage_exit doesn't recompute every candle
    move_trigger = SLTPCalculator.compute_tp_price(
        entry_price=entry_price,
        sl_price=soft_sl,
        side=SIDE_SELL,
        rr_ratio=Decimal(str(cfg.move_sl_rr)),
        taker_fee=taker_fee,
        exit_fee=maker_fee,
    )

    # Build new context for the trade
    new_ts = TradeState(
        entry_price=entry_price,
        sl_price=soft_sl,
        soft_sl_price=soft_sl,
        original_soft_sl=soft_sl,
        disaster_sl_price=disaster_sl,
        lock_profit_price=lock_profit_price,
        move_trigger=move_trigger,
        tp_allocations=tp_allocations,
    )
    new_ctx = ContextSnapshot(
        state=SCANNING,
        soft_sl_price=soft_sl,
        meta=new_ts.to_meta(),
    )

    logger.info(
        "rsi_momentum.short_signal",
        symbol=symbol,
        entry=str(entry_price),
        soft_sl=str(soft_sl),
        disaster_sl=str(disaster_sl),
        tp1=str(tp_prices_all[0]) if tp_prices_all else None,
        spread=round(spread, 3),
    )

    _indicators = {
        "rsi_ema9": float(ema),
        "rsi_wma45": float(wma),
        "spread": spread,
    }

    return AnalysisResult(
        actions=[
            OpenPosition(
                symbol=symbol,
                side=SIDE_SELL,
                entry_price=entry_price,
                sl_price=disaster_sl,
                soft_sl_price=soft_sl,
                tp_prices=tp_prices_all,
                tp_allocations=tp_allocations,
                lock_profit_price=lock_profit_price,
                signal_class=1,
                reason=f"RSI_MOMENTUM SHORT (spread={spread:.2f} > {cfg.spread_threshold})",
                indicators=_indicators,
            )
        ],
        new_context=new_ctx,
    )
