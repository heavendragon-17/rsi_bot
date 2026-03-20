"""
Tests for the candle-close SL behaviour in RsiNoRetestStrategy.

Specification:
  - A WICK below soft_sl (low < soft_sl, close > soft_sl) → no close action
  - A CLOSE below soft_sl (close <= soft_sl) → sets pending_candle_sl=True
  - NEXT candle with pending_candle_sl=True → ClosePosition at open_price
  - The context is cleanly reset to SCANNING after close

These tests deliberately use simple, controlled DataFrames with
explicitly patched Indicators.last so they run without real data.
"""
import pytest
import pandas as pd
from decimal import Decimal

from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.actions import ClosePosition, DoNothing
from app.data.indicators import Indicators

CONFIG = {
    "strategy_params": {
        "use_active_trades": True,
        "nr_tp_count": 3,
        "nr_move_sl_rr": 10.0,   # set very high so move-SL never fires in these tests
        "nr_lock_profit_rr": 5.0,
    },
    "risk": {"leverage": 1},
    "bot": {"timeframe": "15m"},
    "backtest": {"initial_balance": 1000},
    "symbols": ["BTC/USDT"],
}
SYMBOL = "BTC/USDT"
ENTRY = Decimal("100")
SOFT_SL = Decimal("95")


def _make_df(n: int = 220) -> pd.DataFrame:
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15 * i) for i in range(n)]
    timestamps.reverse()
    rows = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "rsi_14": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
         "ema21": 100.0, "ema200": 100.0, "closed": True}
        for _ in range(n)
    ]
    return pd.DataFrame(rows, index=timestamps)


def _position(tp1_hit=False, tp2_hit=False, tp3_hit=False) -> PositionSnapshot:
    return PositionSnapshot(
        has_position=True, symbol=SYMBOL, side="BUY",
        entry_price=ENTRY, current_sl=SOFT_SL, soft_sl=SOFT_SL,
        tp1_hit=tp1_hit, tp2_hit=tp2_hit, tp3_hit=tp3_hit,
    )


def _ctx(pending: bool = False) -> ContextSnapshot:
    return ContextSnapshot(
        state="SCANNING",
        soft_sl_price=SOFT_SL,
        meta={
            "entry_price": ENTRY,
            "sl_price": SOFT_SL,
            "soft_sl_price": SOFT_SL,
            "original_soft_sl": SOFT_SL,
            "moved_sl_to_entry": False,
            "pending_candle_sl": pending,
        },
    )


@pytest.fixture
def strategy():
    return RsiNoRetestStrategy(CONFIG)


def test_wick_below_sl_no_close(strategy, monkeypatch):
    """Wick (low=93) below soft_sl=95 but close=97 → no ClosePosition, no flag set."""
    df = _make_df()
    last = {"open": 98.0, "high": 99.0, "low": 93.0, "close": 97.0,
            "ema21": 100.0, "rsi_ema9": 52.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx())

    assert not any(isinstance(a, ClosePosition) for a in result.actions), (
        "Wick through soft SL must not trigger ClosePosition"
    )
    assert not result.new_context.meta.get("pending_candle_sl", False), (
        "pending_candle_sl must stay False on a wick"
    )


def test_close_below_sl_sets_flag(strategy, monkeypatch):
    """close=94 <= soft_sl=95 → DoNothing + pending_candle_sl=True."""
    df = _make_df()
    last = {"open": 98.0, "high": 99.0, "low": 92.0, "close": 94.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 55.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx())

    assert isinstance(result.actions[0], DoNothing), (
        "First candle closing below soft SL returns DoNothing (2-candle pattern)"
    )
    assert result.new_context.meta.get("pending_candle_sl"), (
        "pending_candle_sl must be set to True"
    )


def test_pending_flag_triggers_close_at_open(strategy, monkeypatch):
    """pending_candle_sl=True → ClosePosition at the next candle's open price."""
    df = _make_df()
    next_open = Decimal("96")
    last = {"open": float(next_open), "high": 97.0, "low": 95.0, "close": 97.0,
            "ema21": 100.0, "rsi_ema9": 49.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx(pending=True))

    close_action = next((a for a in result.actions if isinstance(a, ClosePosition)), None)
    assert close_action is not None, "pending_candle_sl=True must produce ClosePosition"
    assert close_action.reason == "CLOSE_BY_CANDLE_SL"
    assert close_action.price == next_open, (
        f"Exit price must be next candle open ({next_open}), got {close_action.price}"
    )


def test_context_resets_to_scanning_after_close(strategy, monkeypatch):
    """After ClosePosition the new_context must have state=SCANNING and no pending flag."""
    df = _make_df()
    last = {"open": 96.0, "high": 97.0, "low": 95.0, "close": 97.0,
            "ema21": 100.0, "rsi_ema9": 49.0, "rsi_wma45": 50.0}
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx(pending=True))

    assert result.new_context.state == "SCANNING", (
        "Context must reset to SCANNING after candle-close exit"
    )
    assert not result.new_context.meta.get("pending_candle_sl", False), (
        "pending_candle_sl must be cleared after exit"
    )
