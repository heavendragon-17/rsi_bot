"""Tests for the RSI No Retest FADE strategy.

Verifies the fade behaves correctly:
- Loader registration.
- SELL signal on the LONG (parent) setup — same trigger, opposite bet.
- No signal on the SHORT (break-down) setup — parent's reclaim doesn't match.
- Architecture: ``check_entry`` imports ``detect_reclaim`` from the parent
  rather than re-implementing it. If a future contributor copies the
  detection logic into the fade module, this test fails and forces them
  to think about why the fade should diverge.
- Lock-profit move when low touches entry - move_sl_rr * R.
- Max-holding-period force-close uses the shared utility.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.core.actions import (
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
from app.trading.strategy.rsi_no_retest_fade import RsiNoRetestFadeStrategy
from app.trading.strategy.utils.trade_state import TradeState

CONFIG = {
    "strategy_params": {
        "use_active_trades": True,
        "nr_tp_count": 1,
        "tp1_close_pct": 1.0,
        "max_holding_enabled": True,
        "max_holding_bars": 96,
        # On a LONG (parent) setup, historical closes sit BELOW the
        # trigger close — so highest_close lands at entry and the
        # SL>entry guard rejects. Use highest_wick (max high) which
        # gives a SL strictly above entry. This is also a more realistic
        # SHORT-SL placement when fading at a reclaim.
        "nr_sl_mode": "highest_wick",
    },
    "risk": {"leverage": 1, "taker_fee": 0.0, "maker_fee": 0.0},
    "bot": {"timeframe": "15m"},
    "backtest": {"initial_balance": 1000},
    "symbols": ["BTC/USDT"],
}


# ── helpers ────────────────────────────────────────────────────────────────


def _make_long_setup_df(n: int = 220, ema21: float = 100.0) -> pd.DataFrame:
    """DataFrame where the last `nr_lookback`+ bars closed BELOW EMA21 and
    the confirmed-close bar (-2) reclaimed — the LONG (parent) setup that
    the fade should fire on with SELL."""
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
            "rsi_14": 50.0, "rsi_ema9": 53.0, "rsi_wma45": 50.0,  # bullish spread
            "ema21": ema21, "ema200": ema21, "closed": True,
        })
    return pd.DataFrame(rows, index=timestamps)


def _make_short_setup_df(n: int = 220, ema21: float = 100.0) -> pd.DataFrame:
    """DataFrame where the last `nr_lookback`+ bars closed ABOVE EMA21 and
    the confirmed-close bar (-2) broke down — the SHORT-mirror setup. The
    fade should NOT fire here (parent's reclaim trigger doesn't match)."""
    timestamps = [pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=15 * i) for i in range(n)]
    rows = []
    for i in range(n):
        close = 102.0
        if i == n - 2:
            close = 99.0  # break-down
        if i == n - 1:
            close = 98.0
        rows.append({
            "open": close, "high": close + 0.1, "low": close - 0.1, "close": close,
            "rsi_14": 50.0, "rsi_ema9": 47.0, "rsi_wma45": 50.0,  # bearish spread
            "ema21": ema21, "ema200": ema21, "closed": True,
        })
    return pd.DataFrame(rows, index=timestamps)


@pytest.fixture
def strategy() -> RsiNoRetestFadeStrategy:
    return RsiNoRetestFadeStrategy(CONFIG)


# ── 1: loader registration ─────────────────────────────────────────────────


def test_strategy_registers_in_loader() -> None:
    cls = load_strategy({"strategy": "rsi_no_retest_fade"})
    assert cls is RsiNoRetestFadeStrategy


# ── 2: SELL on the parent's BUY setup ──────────────────────────────────────


def test_entry_emits_SELL_on_parent_BUY_setup(strategy, monkeypatch) -> None:
    """The fade fires on the same bars as the LONG parent — but SELL."""
    df = _make_long_setup_df()
    last = {
        "close": 102.0, "high": 102.1, "low": 101.9, "open": 102.0,
        "ema21": 100.0, "rsi_ema9": 53.0, "rsi_wma45": 50.0,  # bullish spread = +3
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


# ── 3: no signal on the SHORT-mirror (break-down) setup ────────────────────


def test_entry_does_NOT_emit_on_breakdown_setup(strategy, monkeypatch) -> None:
    """The fade uses the parent's RECLAIM trigger. A break-down setup —
    which the SHORT mirror would fire on — must produce DoNothing here."""
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
    assert isinstance(result.actions[0], DoNothing)


# ── 4: architecture preservation — uses parent's detection helpers ─────────


def test_entry_uses_parent_detection_helpers() -> None:
    """The fade module must import ``detect_reclaim`` and ``pullback_filter``
    from ``rsi_no_retest.entry`` (the parent), not re-implement them.

    This is an architecture-preservation test: if a future contributor
    copies the detection helpers into the fade module, this test fails
    and forces them to articulate why the fade should diverge from the
    parent's trigger.
    """
    from app.trading.strategy.rsi_no_retest.entry import (
        detect_reclaim as parent_detect_reclaim,
    )
    from app.trading.strategy.rsi_no_retest.entry import (
        pullback_filter as parent_pullback_filter,
    )
    from app.trading.strategy.rsi_no_retest_fade import entry as fade_entry

    # Identity check — the names in the fade module must point at the
    # parent's function objects, not at copies.
    assert fade_entry.detect_reclaim is parent_detect_reclaim
    assert fade_entry.pullback_filter is parent_pullback_filter


# ── 5: lock-profit move when low touches entry - move_sl_rr * R ────────────


def test_lock_profit_fires_on_low_below_minus_half_R(strategy, monkeypatch) -> None:
    """Position: entry=100, soft_sl=102 → R=2. With move_sl_rr=0.5 the
    move-trigger sits at entry - 0.5R = 99 (zero fees). A bar with low=99
    must fire MoveSL to lock_profit_price = entry - 0.2R = 99.6."""
    entry = Decimal("100")
    soft_sl = Decimal("102")
    lock_profit = Decimal("99.6")  # entry - 0.2 * 2 = 99.6
    move_trigger = Decimal("99")   # entry - 0.5 * 2 = 99.0

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

    df = _make_long_setup_df()
    last = {"close": 99.5, "high": 100.5, "low": 99.0, "open": 99.5, "ema21": 100.0,
            "rsi_ema9": 53.0, "rsi_wma45": 50.0}
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


# ── 6: max-holding via shared utility ──────────────────────────────────────


def test_max_holding_uses_shared_utility(strategy, monkeypatch) -> None:
    """bars_held=95, max_bars=96 → next analyze() lifts to 96 and force-closes."""
    entry = Decimal("100")
    # Soft SL well above so STEP 2 (close >= soft_sl) does NOT fire.
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

    df = _make_long_setup_df()
    last = {"close": 99.0, "high": 99.5, "low": 98.5, "open": 99.0,
            "ema21": 100.0, "rsi_ema9": 53.0, "rsi_wma45": 50.0}
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
