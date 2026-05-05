"""
Tests for the ``sl_trigger_mode`` config switch.

In ``"candle_close"`` mode (default, legacy behavior):
  - close <= soft_sl → strategy sets pending_candle_sl=True, exits next open.
  - disaster_sl_price is widened by ``disaster_sl_multiplier``.

In ``"touch"`` mode:
  - close <= soft_sl is ignored by the strategy — exchange-level stop
    handles the SL on touch.
  - disaster_sl_price equals soft_sl_price (exchange stop sits at soft SL).
"""

from decimal import Decimal

import pandas as pd
import pytest

from app.core.actions import ClosePosition, DoNothing
from app.core.constants import SL_TRIGGER_CANDLE_CLOSE, SL_TRIGGER_TOUCH
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy
from app.trading.strategy.rsi_no_retest_entry import check_entry as no_retest_check_entry
from app.trading.strategy.rsi_no_retest_exit import manage_exit as no_retest_manage_exit

SYMBOL = "BTC/USDT"
ENTRY = Decimal("100")
SOFT_SL = Decimal("95")


def _base_config(sl_trigger_mode: str) -> dict:
    return {
        "strategy_params": {
            "use_active_trades": True,
            "nr_tp_count": 3,
            "nr_move_sl_rr": 10.0,
            "nr_lock_profit_rr": 5.0,
            "sl_trigger_mode": sl_trigger_mode,
            "disaster_sl_multiplier": 3.0,
        },
        "risk": {"leverage": 1},
        "bot": {"timeframe": "15m"},
        "backtest": {"initial_balance": 1000},
        "symbols": [SYMBOL],
    }


def _make_df(n: int = 220) -> pd.DataFrame:
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15 * i) for i in range(n)]
    timestamps.reverse()
    rows = [
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "rsi_14": 50.0,
            "rsi_ema9": 50.0,
            "rsi_wma45": 50.0,
            "ema21": 100.0,
            "ema200": 100.0,
            "closed": True,
        }
        for _ in range(n)
    ]
    return pd.DataFrame(rows, index=timestamps)


def _position() -> PositionSnapshot:
    return PositionSnapshot(
        has_position=True,
        symbol=SYMBOL,
        side="BUY",
        entry_price=ENTRY,
        current_sl=SOFT_SL,
        soft_sl=SOFT_SL,
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


# ──────────────────────────────────────────────────────────
# Strategy-level: full analyze() in touch mode
# ──────────────────────────────────────────────────────────


def test_touch_mode_close_below_sl_does_not_set_flag(monkeypatch):
    """In touch mode, a close <= soft_sl must NOT set pending_candle_sl."""
    strategy = RsiNoRetestStrategy(_base_config(SL_TRIGGER_TOUCH))
    df = _make_df()
    last = {
        "open": 98.0,
        "high": 99.0,
        "low": 92.0,
        "close": 94.0,
        "ema21": 100.0,
        "rsi_ema9": 50.0,
        "rsi_wma45": 55.0,
    }
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx())

    assert isinstance(result.actions[0], DoNothing)
    assert not result.new_context.meta.get("pending_candle_sl", False), (
        "touch mode must not set pending_candle_sl on close-through"
    )
    assert not any(isinstance(a, ClosePosition) for a in result.actions)


def test_candle_close_mode_still_sets_flag(monkeypatch):
    """Default (candle_close) mode keeps the legacy behavior."""
    strategy = RsiNoRetestStrategy(_base_config(SL_TRIGGER_CANDLE_CLOSE))
    df = _make_df()
    last = {
        "open": 98.0,
        "high": 99.0,
        "low": 92.0,
        "close": 94.0,
        "ema21": 100.0,
        "rsi_ema9": 50.0,
        "rsi_wma45": 55.0,
    }
    monkeypatch.setattr(strategy.indicators, "compute", lambda *a, **kw: df)
    monkeypatch.setattr(Indicators, "last", staticmethod(lambda df: last))

    result = strategy.analyze(SYMBOL, df, position=_position(), context=_ctx())

    assert isinstance(result.actions[0], DoNothing)
    assert result.new_context.meta.get("pending_candle_sl") is True


# ──────────────────────────────────────────────────────────
# Direct manage_exit() unit tests
# ──────────────────────────────────────────────────────────


def test_manage_exit_touch_mode_skips_step2():
    result = no_retest_manage_exit(
        symbol=SYMBOL,
        context=_ctx(),
        close=Decimal("90"),  # well below soft_sl=95
        high=Decimal("100"),
        open_price=Decimal("96"),
        move_sl_rr=Decimal("10"),
        lock_profit_rr=Decimal("5"),
        taker_fee=Decimal("0.0005"),
        maker_fee=Decimal("0.0002"),
        sl_trigger_mode=SL_TRIGGER_TOUCH,
    )
    assert isinstance(result.actions[0], DoNothing)
    assert not result.new_context.meta.get("pending_candle_sl", False)


def test_manage_exit_candle_close_mode_sets_flag():
    result = no_retest_manage_exit(
        symbol=SYMBOL,
        context=_ctx(),
        close=Decimal("90"),
        high=Decimal("100"),
        open_price=Decimal("96"),
        move_sl_rr=Decimal("10"),
        lock_profit_rr=Decimal("5"),
        taker_fee=Decimal("0.0005"),
        maker_fee=Decimal("0.0002"),
        sl_trigger_mode=SL_TRIGGER_CANDLE_CLOSE,
    )
    assert isinstance(result.actions[0], DoNothing)
    assert result.new_context.meta.get("pending_candle_sl") is True


# ──────────────────────────────────────────────────────────
# Entry-side: disaster_sl placement
# ──────────────────────────────────────────────────────────


def _build_entry_df(soft_sl_target: float) -> pd.DataFrame:
    """Build a df with a controlled lowest_close so compute_entry_sl picks it up."""
    n = 220
    timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15 * i) for i in range(n)]
    timestamps.reverse()
    rows = []
    for i in range(n):
        if i == n - 35:
            close = soft_sl_target  # this candle becomes the lowest close in lookback
        else:
            close = 100.0
        rows.append(
            {
                "open": 100.0,
                "high": 105.0,
                "low": close,
                "close": close,
                "rsi_14": 60.0,
                "rsi_ema9": 60.0,
                "rsi_wma45": 50.0,
                "ema21": 99.0,
                "ema200": 100.0,
                "closed": True,
            }
        )
    rows[-1]["close"] = 100.0
    rows[-1]["ema21"] = 99.0
    rows[-2]["close"] = 98.0
    rows[-2]["ema21"] = 99.0
    rows[-3]["close"] = 98.0
    rows[-3]["ema21"] = 99.0
    return pd.DataFrame(rows, index=timestamps)


@pytest.mark.parametrize(
    "mode,multiplier,expected_factor",
    [
        (SL_TRIGGER_TOUCH, 3.0, Decimal("1")),  # disaster == soft
        (SL_TRIGGER_CANDLE_CLOSE, 3.0, Decimal("3")),  # disaster = soft × multiplier (in distance)
    ],
)
def test_entry_disaster_sl_respects_mode(mode, multiplier, expected_factor):
    """check_entry should set disaster_sl appropriately for each mode.

    We capture the OpenPosition action from a synthetic CONFIRMING context
    and assert the relationship between entry, soft_sl, and disaster_sl.
    """
    from app.core.context import CONFIRMING

    strategy = RsiNoRetestStrategy(_base_config(mode))
    df = _build_entry_df(soft_sl_target=95.0)
    df_ind = strategy.indicators.compute(df, symbol=SYMBOL, timeframe="15m")
    last = Indicators.last(df_ind)
    if last is None:
        pytest.skip("indicators returned no data on synthetic df")

    context = ContextSnapshot(state=CONFIRMING)
    debug_rows: list[dict] = []

    result = no_retest_check_entry(
        symbol=SYMBOL,
        df_ind=df_ind,
        context=context,
        close=Decimal(str(last["close"])),
        ema21=Decimal(str(last["ema21"])),
        rsi_ema9=last.get("rsi_ema9"),
        rsi_wma45=last.get("rsi_wma45"),
        lookback=strategy.lookback,
        max_above_ema21=strategy.max_above_ema21,
        rsi_spread_min=strategy.rsi_spread_min,
        sl_mode=strategy.sl_mode,
        sl_buffer_pct=strategy.sl_buffer_pct,
        disaster_sl_multiplier=multiplier,
        sl_trigger_mode=mode,
        tp1_rr=strategy.tp1_rr,
        tp2_rr=strategy.tp2_rr,
        tp3_rr=strategy.tp3_rr,
        tp_count=strategy.tp_count,
        tp1_close_pct=strategy.tp1_close_pct,
        tp2_close_pct=strategy.tp2_close_pct,
        move_sl_rr=strategy.move_sl_rr,
        lock_profit_rr=strategy.lock_profit_rr,
        taker_fee=strategy.taker_fee,
        maker_fee=strategy.maker_fee,
        indicators=strategy.indicators,
        debug_enabled=False,
        debug_rows=debug_rows,
        df_ind_index_last=df_ind.index[-1],
    )

    open_actions = [a for a in result.actions if a.__class__.__name__ == "OpenPosition"]
    if not open_actions:
        pytest.skip("entry conditions not met on synthetic df — assertion path unreachable")
    op = open_actions[0]

    entry = op.entry_price
    soft = op.soft_sl_price
    disaster = op.sl_price
    assert soft is not None and disaster is not None
    soft_distance = entry - soft
    disaster_distance = entry - disaster
    if expected_factor == Decimal("1"):
        assert disaster == soft, "touch mode must place disaster_sl at soft_sl"
    else:
        assert disaster_distance == soft_distance * expected_factor


# ──────────────────────────────────────────────────────────
# Validation: bad mode rejected at construction time
# ──────────────────────────────────────────────────────────


def test_invalid_sl_trigger_mode_raises():
    cfg = _base_config("garbage")
    with pytest.raises(ValueError, match="sl_trigger_mode"):
        RsiNoRetestStrategy(cfg)
