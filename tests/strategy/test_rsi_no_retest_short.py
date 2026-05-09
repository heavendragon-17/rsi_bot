"""Tests for the RSI No Retest SHORT strategy.

Verifies the SHORT mirror behaves correctly:
- Loader registration
- SELL signal on break-down setup with bearish RSI spread
- No SELL signal on the LONG (reclaim) setup
- Lock-profit move when low touches entry - move_sl_rr * R
- Candle-close flag when close >= soft_sl, exits at next bar's open
- Max-holding-period force-close uses the shared utility (last priority)
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.core.actions import (
    EXIT_CLOSE_BY_CANDLE_SL,
    EXIT_MAX_HOLDING_PERIOD,
    SIDE_SELL,
    ClosePosition,
    DoNothing,
    MoveSL,
    OpenPosition,
)
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.strategy.loader import load_strategy
from app.trading.strategy.rsi_no_retest_short import RsiNoRetestShortStrategy
from app.trading.strategy.utils.trade_state import TradeState

CONFIG = {
    "strategy_params": {
        "use_active_trades": True,
        "nr_tp_count": 1,
        "tp1_close_pct": 1.0,
        "max_holding_enabled": True,
        "max_holding_bars": 96,
    },
    "risk": {"leverage": 1, "taker_fee": 0.0, "maker_fee": 0.0},
    "bot": {"timeframe": "15m"},
    "backtest": {"initial_balance": 1000},
    "symbols": ["BTC/USDT"],
}


# ── helpers ────────────────────────────────────────────────────────────────


def _make_short_setup_df(n: int = 220, ema21: float = 100.0) -> pd.DataFrame:
    """DataFrame where the last `nr_lookback`+ bars closed ABOVE EMA21
    and the confirmed-close bar (-2) closed below — a SHORT break-down."""
    timestamps = [pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=15 * i) for i in range(n)]
    rows = []
    for i in range(n):
        # All historical bars sit above EMA21 (prolonged rise).
        close = 102.0
        if i == n - 2:
            # Confirmed-close candle (-2): break below EMA21.
            close = 99.0
        if i == n - 1:
            # Current bar (-1): the entry trigger bar — also below EMA21.
            close = 98.0
        rows.append({
            "open": close, "high": close + 0.1, "low": close - 0.1, "close": close,
            "rsi_14": 50.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0,
            "ema21": ema21, "ema200": ema21, "closed": True,
        })
    return pd.DataFrame(rows, index=timestamps)


def _make_long_setup_df(n: int = 220, ema21: float = 100.0) -> pd.DataFrame:
    """DataFrame where the last `nr_lookback`+ bars closed BELOW EMA21
    and the confirmed-close bar (-2) reclaimed — the LONG (parent) setup."""
    timestamps = [pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=15 * i) for i in range(n)]
    rows = []
    for i in range(n):
        close = 98.0
        if i == n - 2:
            close = 101.0  # reclaim
        if i == n - 1:
            close = 102.0
        rows.append({
            "open": close, "high": close + 0.1, "low": close - 0.1, "close": close,
            "rsi_14": 50.0, "rsi_ema9": 53.0, "rsi_wma45": 50.0,
            "ema21": ema21, "ema200": ema21, "closed": True,
        })
    return pd.DataFrame(rows, index=timestamps)


@pytest.fixture
def strategy() -> RsiNoRetestShortStrategy:
    return RsiNoRetestShortStrategy(CONFIG)


# ── 1: loader registration ─────────────────────────────────────────────────


def test_strategy_registers_in_loader() -> None:
    cls = load_strategy({"strategy": "rsi_no_retest_short"})
    assert cls is RsiNoRetestShortStrategy


# ── 2: SELL on break-down setup ────────────────────────────────────────────


def test_entry_emits_sell_on_break_down_setup(strategy, monkeypatch) -> None:
    df = _make_short_setup_df()
    last = {
        "close": 98.0, "high": 98.1, "low": 97.9, "open": 98.0,
        "ema21": 100.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0,
    }
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last))

    ctx = ContextSnapshot(state=SCANNING)
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    assert len(result.actions) == 1
    action = result.actions[0]
    assert isinstance(action, OpenPosition), f"expected OpenPosition, got {type(action).__name__}"
    assert action.side == SIDE_SELL
    # SHORT: soft SL must sit ABOVE entry; TP1 must sit BELOW entry.
    assert action.soft_sl_price is not None and action.soft_sl_price > action.entry_price
    assert action.tp_prices and action.tp_prices[0] < action.entry_price


# ── 3: no SELL on the LONG (reclaim) setup ─────────────────────────────────


def test_entry_does_NOT_emit_when_parent_would_emit_buy(strategy, monkeypatch) -> None:
    """SHORT.analyze() on a LONG-favorable setup must return DoNothing."""
    df = _make_long_setup_df()
    last = {
        "close": 102.0, "high": 102.1, "low": 101.9, "open": 102.0,
        "ema21": 100.0, "rsi_ema9": 53.0, "rsi_wma45": 50.0,  # bullish spread
    }
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last))

    ctx = ContextSnapshot(state=SCANNING)
    result = strategy.analyze("BTC/USDT", df, context=ctx)

    assert len(result.actions) == 1
    assert isinstance(result.actions[0], DoNothing)


# ── 4: lock-profit move when low touches entry - move_sl_rr * R ────────────


def test_lock_profit_fires_on_low_below_minus_half_R(strategy, monkeypatch) -> None:
    """Position: entry=100, soft_sl=102 → R=2. move_sl_rr=0.5 → trigger at 99.

    With zero fees the move-trigger price is exactly entry - 0.5*R = 99.
    Low=99 must fire ``MoveSL`` to lock_profit_price = entry - 0.2*R = 99.6.
    """
    entry = Decimal("100")
    soft_sl = Decimal("102")
    lock_profit = Decimal("99.6")  # entry - 0.2 * R = 100 - 0.4 = 99.6
    move_trigger = Decimal("99")   # entry - 0.5 * R = 100 - 1.0 = 99.0

    ts = TradeState(
        entry_price=entry,
        sl_price=soft_sl,
        soft_sl_price=soft_sl,
        original_soft_sl=soft_sl,
        lock_profit_price=lock_profit,
        move_trigger=move_trigger,
        moved_sl_to_entry=False,
        bars_held=5,
    )
    ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl, meta=ts.to_meta())

    df = _make_short_setup_df()
    last = {"close": 99.5, "high": 100.5, "low": 99.0, "open": 99.5, "ema21": 100.0,
            "rsi_ema9": 47.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last))

    pos = PositionSnapshot(
        has_position=True, symbol="BTC/USDT", side=SIDE_SELL,
        entry_price=entry, current_sl=soft_sl, soft_sl=soft_sl,
    )
    result = strategy.analyze("BTC/USDT", df, position=pos, context=ctx)

    assert len(result.actions) == 1
    action = result.actions[0]
    assert isinstance(action, MoveSL), f"expected MoveSL, got {type(action).__name__}"
    assert action.new_sl_price == lock_profit


# ── 5: candle-close flag set when close >= soft_sl, exits next bar ─────────


def test_candle_close_flag_set_on_close_above_soft_sl(strategy, monkeypatch) -> None:
    """Bar 1: close=102.5 >= soft_sl=102 sets pending_candle_sl, no exit yet.
    Bar 2: pending flag fires → ClosePosition at next bar's open."""
    entry = Decimal("100")
    soft_sl = Decimal("102")

    ts = TradeState(
        entry_price=entry,
        sl_price=soft_sl,
        soft_sl_price=soft_sl,
        original_soft_sl=soft_sl,
        moved_sl_to_entry=False,
        pending_candle_sl=False,
        bars_held=5,
    )
    ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl, meta=ts.to_meta())

    df = _make_short_setup_df()
    last_bar1 = {"close": 102.5, "high": 102.6, "low": 101.0, "open": 101.5,
                 "ema21": 100.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last_bar1))

    pos = PositionSnapshot(
        has_position=True, symbol="BTC/USDT", side=SIDE_SELL,
        entry_price=entry, current_sl=soft_sl, soft_sl=soft_sl,
    )
    result1 = strategy.analyze("BTC/USDT", df, position=pos, context=ctx)
    assert len(result1.actions) == 1
    assert isinstance(result1.actions[0], DoNothing)
    new_ts1 = TradeState.from_meta(result1.new_context.meta)
    assert new_ts1.pending_candle_sl is True

    # Bar 2: pending flag fires; exit at this bar's open price.
    last_bar2 = {"close": 103.0, "high": 103.5, "low": 102.0, "open": 102.7,
                 "ema21": 100.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last_bar2))
    result2 = strategy.analyze("BTC/USDT", df, position=pos, context=result1.new_context)
    assert len(result2.actions) == 1
    action = result2.actions[0]
    assert isinstance(action, ClosePosition)
    assert action.reason == EXIT_CLOSE_BY_CANDLE_SL
    assert action.price == Decimal("102.7")


# ── 6: max-holding via shared utility ──────────────────────────────────────


def test_max_holding_uses_shared_utility(strategy, monkeypatch) -> None:
    """bars_held=95, max_bars=96 → next analyze() lifts to 96 and force-closes."""
    entry = Decimal("100")
    # Soft SL sits well above so STEP 2 (close >= soft_sl) does NOT fire.
    soft_sl = Decimal("110")

    ts = TradeState(
        entry_price=entry,
        sl_price=soft_sl,
        soft_sl_price=soft_sl,
        original_soft_sl=soft_sl,
        moved_sl_to_entry=True,  # also disables STEP 1
        pending_candle_sl=False,
        bars_held=95,
    )
    ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl, meta=ts.to_meta())

    df = _make_short_setup_df()
    last = {"close": 99.0, "high": 99.5, "low": 98.5, "open": 99.0,
            "ema21": 100.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda d: last))

    pos = PositionSnapshot(
        has_position=True, symbol="BTC/USDT", side=SIDE_SELL,
        entry_price=entry, current_sl=soft_sl, soft_sl=soft_sl,
    )
    result = strategy.analyze("BTC/USDT", df, position=pos, context=ctx)

    assert len(result.actions) == 1
    action = result.actions[0]
    assert isinstance(action, ClosePosition), f"expected ClosePosition, got {type(action).__name__}"
    assert action.reason == EXIT_MAX_HOLDING_PERIOD
    assert action.price == Decimal("99.0")
