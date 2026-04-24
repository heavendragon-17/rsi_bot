"""
Unit tests for RsiMomentumStrategy (SHORT-only entries).

Test categories:
  1. Entry conditions (S1-S5)
  2. Divergence detection
  3. SL/TP computation
  4. Exit management (lock-profit, candle-close SL)
  5. Edge cases (warm-up, ignore existing position)
"""

from decimal import Decimal

import pandas as pd
import pytest

from app.core.actions import ClosePosition, DoNothing, MoveSL, OpenPosition
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.sl_tp_calculator import SLTPCalculator
from app.trading.strategy.rsi_momentum import RsiMomentumStrategy

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_df(n: int = 100, base_close: float = 100.0) -> pd.DataFrame:
    """Create an n-row OHLCV DataFrame with flat prices."""
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    df = pd.DataFrame(
        {
            "open": base_close,
            "high": base_close * 1.001,
            "low": base_close * 0.999,
            "close": base_close,
            "volume": 1000.0,
            "closed": True,
        },
        index=ts,
    )
    return df


def _inject_indicators(
    df: pd.DataFrame,
    rsi: float = 45.0,
    ema9: float = 50.0,
    wma45: float = 55.0,
) -> pd.DataFrame:
    """Directly inject indicator columns (bypasses actual computation)."""
    out = df.copy()
    out["rsi_14"] = rsi
    out["rsi_ema9"] = ema9
    out["rsi_wma45"] = wma45
    return out


def _bearish_divergence_df(n: int = 80) -> pd.DataFrame:
    """
    Build a DataFrame with a clear bearish RSI divergence.

    With n=80 and lookback=30 (default in strategy), the window is the last 30 rows.
    Pivot placements (relative to end of df):
      - pivot_a at index n-25 (about 25 from end) — within last 30 candles
      - pivot_b at index n-12 (about 12 from end) — within last 30 candles, after A
    Each pivot needs pivot_strength=5 lower highs on each side.
    """
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    closes = [100.0] * n
    highs = [100.5] * n
    rsis = [45.0] * n
    emas = [50.0] * n
    wmas = [55.0] * n

    N = 5  # pivot strength

    # Pivot A: at index n-25 (well within last 30)
    pivot_a = n - 25
    highs[pivot_a] = 110.0  # swing high A (price lower)
    rsis[pivot_a] = 70.0
    # Ensure N bars on each side are strictly lower
    for i in range(pivot_a - N, pivot_a):
        highs[i] = 99.0
    for i in range(pivot_a + 1, pivot_a + N + 1):
        highs[i] = 99.0

    # Pivot B: at index n-12 (closer to end), after pivot_a
    pivot_b = n - 12
    highs[pivot_b] = 115.0  # swing high B (Higher High)
    rsis[pivot_b] = 65.0  # Lower RSI High → bearish divergence
    # Ensure N bars on each side are strictly lower
    for i in range(pivot_b - N, pivot_b):
        highs[i] = 99.0
    for i in range(pivot_b + 1, min(pivot_b + N + 1, n)):
        highs[i] = 99.0

    df = pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": 1000.0,
            "closed": True,
            "rsi_14": rsis,
            "rsi_ema9": emas,
            "rsi_wma45": wmas,
        },
        index=ts,
    )
    return df


def _make_strategy(cfg_overrides: dict = None) -> RsiMomentumStrategy:
    """Create a strategy instance with a minimal config dict.

    Unless explicitly overridden, existing tests opt out of the post-review
    filters (EMA200 trend filter, crossover freshness cap, stale-trade
    exit, stricter warm-up) so their original signal semantics still apply.
    New tests opt *in* to validate each filter individually.
    """
    base_overrides = {
        "min_candles": 75,
        "ema200_filter": False,
        "max_candles_since_crossover": 0,
        "stale_exit_candles": 0,
        # Preserve original lock-profit defaults for legacy tests.
        "move_sl_rr": 0.5,
        "lock_profit_rr": 0.2,
    }
    params = {**base_overrides, **(cfg_overrides or {})}
    config = {
        "strategy_params": params,
        "bot": {"timeframe": "15m"},
        "risk": {"leverage": 1},
        "backtest": {"initial_balance": 10000},
        "symbols": ["BTC/USDT"],
    }
    return RsiMomentumStrategy(config)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def entry_setup():
    strategy = _make_strategy()
    symbol = "BTC/USDT"
    ctx = ContextSnapshot(state=SCANNING)
    return strategy, symbol, ctx


@pytest.fixture
def divergence_indicators():
    return Indicators()


@pytest.fixture
def exit_setup():
    strategy = _make_strategy()
    symbol = "BTC/USDT"
    entry = Decimal("100")
    soft_sl = Decimal("105")  # Short: SL above entry
    return strategy, symbol, entry, soft_sl


@pytest.fixture
def edge_setup():
    strategy = _make_strategy()
    symbol = "BTC/USDT"
    return strategy, symbol


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for entry tests
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_with_df(strategy, symbol, df_ind, context):
    """Run analyze() with a pre-built indicator DataFrame."""
    strategy.indicators.compute = lambda d, **kw: df_ind
    return strategy.analyze(symbol, df_ind, position=None, context=context)


def _short_signal_df(spread: float = 5.0, with_crossover: bool = True) -> pd.DataFrame:
    """Return a df_ind that satisfies all S1-S5 conditions."""
    n = 80
    df = _bearish_divergence_df(n=n)

    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 45.0 + spread

    df["rsi_14"] = 40.0
    # Restore pivot RSI values needed for divergence detection
    pivot_a_idx = n - 25
    pivot_b_idx = n - 12
    df.iloc[pivot_a_idx, df.columns.get_loc("rsi_14")] = 70.0
    df.iloc[pivot_b_idx, df.columns.get_loc("rsi_14")] = 65.0

    if with_crossover:
        df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 55.0
        df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 55.0 - spread

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 1. Entry condition tests
# ─────────────────────────────────────────────────────────────────────────────


def test_short_entry_all_conditions_met(entry_setup):
    """S1-S5 all true → OpenPosition(side='SELL')"""
    strategy, symbol, ctx = entry_setup
    df = _short_signal_df()
    result = _analyze_with_df(strategy, symbol, df, ctx)
    assert len(result.actions) == 1
    action = result.actions[0]
    assert isinstance(action, OpenPosition)
    assert action.side == "SELL"
    assert action.symbol == symbol


def test_short_entry_no_crossover_no_history(entry_setup):
    """Alignment holds but no crossover ever fired → DoNothing"""
    strategy, symbol, ctx = entry_setup
    df = _bearish_divergence_df(n=80)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    result = _analyze_with_df(strategy, symbol, df, ctx)
    actions = result.actions
    assert isinstance(actions[0], DoNothing)


def test_short_entry_alignment_broken(entry_setup):
    """RSI > EMA9 → alignment fails → DoNothing"""
    strategy, symbol, ctx = entry_setup
    df = _bearish_divergence_df(n=80)
    df["rsi_14"] = 55.0  # RSI > EMA9
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    result = _analyze_with_df(strategy, symbol, df, ctx)
    assert isinstance(result.actions[0], DoNothing)


def test_short_entry_spread_too_narrow(entry_setup):
    """(WMA45 - EMA9) <= 2.5 → S4 fails → DoNothing"""
    strategy, symbol, ctx = entry_setup
    df = _bearish_divergence_df(n=80)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 47.5
    df["rsi_wma45"] = 50.0  # spread = 2.5, not > 2.5
    # Add crossover
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0
    result = _analyze_with_df(strategy, symbol, df, ctx)
    assert isinstance(result.actions[0], DoNothing)


def test_short_entry_no_divergence(entry_setup):
    """No swing highs in lookback → S5 fails → DoNothing"""
    strategy, symbol, ctx = entry_setup
    df = _make_df(n=80, base_close=100.0)
    # Inject flat highs — no pivot will be detected
    df["high"] = 100.5
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    # Add crossover
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0
    result = _analyze_with_df(strategy, symbol, df, ctx)
    assert isinstance(result.actions[0], DoNothing)


def test_short_entry_flexible_signal_persistence(entry_setup):
    """
    Crossover fires on candle N, alignment still holds on N+1 → OpenPosition.
    Context carries crossover_detected=True from N.
    """
    strategy, symbol, _ctx = entry_setup
    n = 80
    df = _bearish_divergence_df(n=n)
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    df["rsi_14"] = 40.0
    # Restore pivot RSI values
    df.iloc[n - 25, df.columns.get_loc("rsi_14")] = 70.0
    df.iloc[n - 12, df.columns.get_loc("rsi_14")] = 65.0
    ctx_with_crossover = ContextSnapshot(
        state=SCANNING,
        meta={"crossover_detected": True},
    )
    result = _analyze_with_df(strategy, symbol, df, ctx_with_crossover)
    action = result.actions[0]
    assert isinstance(action, OpenPosition)
    assert action.side == "SELL"


def test_short_entry_signal_expires_when_alignment_breaks(entry_setup):
    """Crossover detected before, but now RSI > EMA9 → signal expired → DoNothing"""
    strategy, symbol, _ctx = entry_setup
    df = _make_df(n=80)
    df["rsi_14"] = 55.0  # broken alignment
    df["rsi_ema9"] = 48.0
    df["rsi_wma45"] = 52.0
    ctx_with_crossover = ContextSnapshot(
        state=SCANNING,
        meta={"crossover_detected": True},
    )
    result = _analyze_with_df(strategy, symbol, df, ctx_with_crossover)
    assert isinstance(result.actions[0], DoNothing)
    # Flag should be reset
    assert not result.new_context.meta.get("crossover_detected", False)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Divergence detection tests
# ─────────────────────────────────────────────────────────────────────────────


def test_bearish_divergence_detected(divergence_indicators):
    """Price HH + RSI LH → True"""
    df = _bearish_divergence_df(n=80)
    result = divergence_indicators.detect_bearish_divergence(df, lookback=30, pivot_strength=5)
    assert result


def test_no_divergence_insufficient_pivots(divergence_indicators):
    """Flat highs — fewer than 2 swing highs → False"""
    df = _make_df(n=80)
    df["rsi_14"] = 45.0
    df["high"] = 100.5  # all same → no pivots
    result = divergence_indicators.detect_bearish_divergence(df, lookback=60, pivot_strength=5)
    assert not result


def test_divergence_outside_lookback_ignored(divergence_indicators):
    """Divergence exists but only outside the lookback window → False"""
    df = _bearish_divergence_df(n=80)
    result = divergence_indicators.detect_bearish_divergence(df, lookback=5, pivot_strength=1)
    assert not result


def test_no_divergence_when_rsi_also_higher(divergence_indicators):
    """Price HH + RSI HH (not lower) → no divergence → False"""
    ts = pd.date_range("2024-01-01", periods=60, freq="15min")
    highs = [100.0] * 60
    rsis = [50.0] * 60

    # First pivot: price=110, rsi=60
    highs[15] = 110.0
    rsis[15] = 60.0
    # Second pivot: price=115 (HH), rsi=65 (also HH — no divergence)
    highs[30] = 115.0
    rsis[30] = 65.0

    df = pd.DataFrame(
        {
            "open": 100.0,
            "high": highs,
            "low": 99.5,
            "close": 100.0,
            "volume": 1000.0,
            "closed": True,
            "rsi_14": rsis,
            "rsi_ema9": 50.0,
            "rsi_wma45": 55.0,
        },
        index=ts,
    )
    result = divergence_indicators.detect_bearish_divergence(df, lookback=50, pivot_strength=5)
    assert not result


# ─────────────────────────────────────────────────────────────────────────────
# 3. SL/TP computation tests
# ─────────────────────────────────────────────────────────────────────────────


def test_sl_is_highest_high_30_candles():
    """compute_soft_sl for SHORT = max high in lookback window."""
    df = _make_df(n=50, base_close=100.0)
    df["high"] = 100.5
    df.loc[df.index[-15], "high"] = 115.0

    sl = SLTPCalculator.compute_soft_sl(df, side="SELL", lookback=30)
    assert sl is not None
    assert sl == Decimal("115.0")


def test_sl_long_is_lowest_low():
    """compute_soft_sl for LONG = min low in lookback window."""
    df = _make_df(n=50, base_close=100.0)
    df["low"] = 99.5
    df.loc[df.index[-10], "low"] = 85.0

    sl = SLTPCalculator.compute_soft_sl(df, side="BUY", lookback=30)
    assert sl is not None
    assert sl == Decimal("85.0")


def test_disaster_sl_short_at_3x():
    """Short disaster SL = entry + 3 × (soft_sl - entry)."""
    entry = Decimal("100")
    soft_sl = Decimal("105")
    disaster = SLTPCalculator.compute_disaster_sl(entry, soft_sl, "SELL", Decimal("3"))
    expected = entry + (soft_sl - entry) * Decimal("3")
    assert disaster == expected  # = 115


def test_disaster_sl_long_at_3x():
    """Long disaster SL = entry - 3 × (entry - soft_sl)."""
    entry = Decimal("100")
    soft_sl = Decimal("95")
    disaster = SLTPCalculator.compute_disaster_sl(entry, soft_sl, "BUY", Decimal("3"))
    expected = entry - (entry - soft_sl) * Decimal("3")
    assert disaster == expected  # = 85


def test_sl_equals_entry_skipped_in_strategy():
    """If soft SL <= entry for short, strategy returns DoNothing."""
    strategy = _make_strategy()
    df = _bearish_divergence_df(n=80)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    df["high"] = 100.0
    df["close"] = 100.0

    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0

    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=None, context=ContextSnapshot(state=SCANNING))
    assert isinstance(result.actions[0], DoNothing)


def test_tp_prices_below_entry_for_short():
    """All TP levels should be below the entry price for a short."""
    entry = Decimal("100")
    sl = Decimal("105")
    for rr in [Decimal("1"), Decimal("2"), Decimal("3")]:
        tp = SLTPCalculator.compute_tp_price(entry, sl, "SELL", rr)
        assert tp is not None
        assert tp < entry, f"TP at {rr}R should be below entry for short"


def test_tp_prices_above_entry_for_long():
    """All TP levels should be above the entry price for a long."""
    entry = Decimal("100")
    sl = Decimal("95")
    for rr in [Decimal("1"), Decimal("2"), Decimal("3")]:
        tp = SLTPCalculator.compute_tp_price(entry, sl, "BUY", rr)
        assert tp is not None
        assert tp > entry, f"TP at {rr}R should be above entry for long"


def test_tp_zero_risk_returns_none():
    """Zero risk distance → compute_tp_price returns None."""
    entry = Decimal("100")
    sl = Decimal("100")
    result = SLTPCalculator.compute_tp_price(entry, sl, "SELL", Decimal("1"))
    assert result is None


def test_lock_profit_short_below_entry():
    """Lock-profit price for short should be below the entry price."""
    entry = Decimal("100")
    soft_sl = Decimal("105")
    lock = SLTPCalculator.compute_lock_profit_price(
        entry_price=entry,
        soft_sl_price=soft_sl,
        side="SELL",
        lock_profit_rr=Decimal("0.2"),
    )
    assert lock is not None
    assert lock < entry, "Lock-profit SL should be below entry for short"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Exit management tests
# ─────────────────────────────────────────────────────────────────────────────


def _open_position(symbol, entry, soft_sl):
    return PositionSnapshot(
        has_position=True,
        symbol=symbol,
        side="SELL",
        entry_price=entry,
        current_sl=soft_sl,
    )


def _base_context(entry, soft_sl, extra=None):
    meta = {
        "entry_price": entry,
        "sl_price": soft_sl,
        "soft_sl_price": soft_sl,
        "original_soft_sl": soft_sl,
        "moved_sl_to_entry": False,
        "pending_candle_sl": False,
    }
    if extra:
        meta.update(extra)
    return ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl, meta=meta)


def _df_with_candle(open_: float, high: float, low: float, close: float, n: int = 80) -> pd.DataFrame:
    df = _make_df(n=n, base_close=open_)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    df.iloc[-1, df.columns.get_loc("open")] = open_
    df.iloc[-1, df.columns.get_loc("high")] = high
    df.iloc[-1, df.columns.get_loc("low")] = low
    df.iloc[-1, df.columns.get_loc("close")] = close
    return df


def _analyze_exit(strategy, symbol, entry, soft_sl, df, context):
    position = _open_position(symbol, entry, soft_sl)
    strategy.indicators.compute = lambda d, **kw: df
    return strategy.analyze(symbol, df, position=position, context=context)


def test_lock_profit_triggered_when_price_drops(exit_setup):
    """For a short, when low <= move_trigger, strategy should emit MoveSL."""
    strategy, symbol, entry, soft_sl = exit_setup
    df = _df_with_candle(open_=100, high=100.5, low=90.0, close=91.0)
    ctx = _base_context(entry, soft_sl)
    result = _analyze_exit(strategy, symbol, entry, soft_sl, df, ctx)
    move_sl_actions = [a for a in result.actions if isinstance(a, MoveSL)]
    assert len(move_sl_actions) > 0, "Should emit MoveSL when price drops sufficiently"


def test_candle_close_sl_flags_when_close_above_soft_sl(exit_setup):
    """For a short, close >= soft_sl → set pending_candle_sl flag."""
    strategy, symbol, entry, soft_sl = exit_setup
    df = _df_with_candle(open_=100, high=106, low=99, close=106.0)
    ctx = _base_context(entry, soft_sl)
    result = _analyze_exit(strategy, symbol, entry, soft_sl, df, ctx)
    assert isinstance(result.actions[0], DoNothing)
    assert result.new_context.meta.get("pending_candle_sl", False)


def test_pending_sl_closes_on_next_candle(exit_setup):
    """pending_candle_sl True → next candle ClosePosition(reason=CLOSE_BY_CANDLE_SL)."""
    strategy, symbol, entry, soft_sl = exit_setup
    next_open = 104.0
    df = _df_with_candle(open_=next_open, high=105, low=103, close=104)
    ctx = _base_context(entry, soft_sl, {"pending_candle_sl": True})
    result = _analyze_exit(strategy, symbol, entry, soft_sl, df, ctx)
    close_actions = [a for a in result.actions if isinstance(a, ClosePosition)]
    assert len(close_actions) > 0
    assert close_actions[0].reason == "CLOSE_BY_CANDLE_SL"
    assert close_actions[0].price == Decimal(str(next_open))


def test_wick_above_sl_no_close(exit_setup):
    """A wick above soft SL (high > soft_sl but close < soft_sl) must NOT trigger close."""
    strategy, symbol, entry, soft_sl = exit_setup
    df = _df_with_candle(open_=100, high=108, low=99, close=103.0)
    ctx = _base_context(entry, soft_sl)
    result = _analyze_exit(strategy, symbol, entry, soft_sl, df, ctx)
    has_close = any(isinstance(a, ClosePosition) for a in result.actions)
    assert not has_close
    assert not result.new_context.meta.get("pending_candle_sl", False)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_warmup_insufficient_candles(edge_setup):
    """Fewer candles than min_candles → DoNothing (warm-up)."""
    strategy, symbol = edge_setup
    df = _make_df(n=10)
    result = strategy.analyze(symbol, df)
    assert isinstance(result.actions[0], DoNothing)


def test_ignore_new_entry_when_position_open(edge_setup):
    """If position already exists, strategy manages exit, not entry."""
    strategy, symbol = edge_setup
    position = PositionSnapshot(
        has_position=True,
        symbol=symbol,
        side="SELL",
        entry_price=Decimal("100"),
        current_sl=Decimal("105"),
    )
    n = 80
    df = _bearish_divergence_df(n=n)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    df.iloc[n - 25, df.columns.get_loc("rsi_14")] = 70.0
    df.iloc[n - 12, df.columns.get_loc("rsi_14")] = 65.0
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0

    ctx = ContextSnapshot(
        state=SCANNING,
        soft_sl_price=Decimal("105"),
        meta={
            "entry_price": Decimal("100"),
            "sl_price": Decimal("105"),
            "soft_sl_price": Decimal("105"),
            "original_soft_sl": Decimal("105"),
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
        },
    )
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze(symbol, df, position=position, context=ctx)
    has_open = any(isinstance(a, OpenPosition) for a in result.actions)
    assert not has_open, "Should not open a second position while one is active"


def test_zero_risk_distance_returns_do_nothing(edge_setup):
    """soft_sl == entry price for short → zero risk → DoNothing."""
    strategy, symbol = edge_setup
    df = _bearish_divergence_df(n=80)
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 50.0
    df["high"] = 100.0
    df["close"] = 100.0

    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0

    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze(symbol, df, position=None)
    assert isinstance(result.actions[0], DoNothing)


def test_crossover_detection_requires_strict_inequality():
    """EMA9 == WMA45 on both candles → not a crossover."""
    ind = Indicators()
    df = _make_df(n=10)
    df["rsi_14"] = 50.0
    df["rsi_ema9"] = 50.0
    df["rsi_wma45"] = 50.0
    assert not ind.detect_crossover(df, direction="bearish")
    assert not ind.detect_crossover(df, direction="bullish")


def test_loader_registers_rsi_momentum():
    """rsi_momentum should be available in the strategy loader."""
    from app.trading.strategy.loader import STRATEGY_MAP

    assert "rsi_momentum" in STRATEGY_MAP
    from app.trading.strategy.rsi_momentum import RsiMomentumStrategy

    assert STRATEGY_MAP["rsi_momentum"] is RsiMomentumStrategy


def test_open_position_action_supports_sell_side():
    """OpenPosition dataclass can carry side='SELL' without errors."""
    from app.core.actions import OpenPosition

    action = OpenPosition(
        symbol="BTC/USDT",
        side="SELL",
        entry_price=Decimal("100"),
        sl_price=Decimal("115"),
        soft_sl_price=Decimal("105"),
        tp_prices=[Decimal("95"), Decimal("90")],
        tp_allocations={"TP1": 0.5, "TP2": 1.0},
        lock_profit_price=Decimal("99"),
        signal_class=1,
        reason="test",
    )
    assert action.side == "SELL"


# ─────────────────────────────────────────────────────────────────────────────
# 6. SLTPCalculator static method tests
# ─────────────────────────────────────────────────────────────────────────────


def test_position_size_direction_agnostic():
    """Position sizing uses absolute distance — same result for both sides."""
    entry = Decimal("100")
    sl_long = Decimal("95")
    sl_short = Decimal("105")

    size_long = SLTPCalculator.compute_position_size(
        entry, sl_long, Decimal("10000"), Decimal("0.02"), Decimal("10")
    )
    size_short = SLTPCalculator.compute_position_size(
        entry, sl_short, Decimal("10000"), Decimal("0.02"), Decimal("10")
    )
    assert float(size_long) == pytest.approx(float(size_short), abs=1e-6)


def test_position_size_zero_on_zero_distance():
    """SL == entry → returns 0."""
    result = SLTPCalculator.compute_position_size(
        Decimal("100"), Decimal("100"), Decimal("10000"), Decimal("0.02"), Decimal("10")
    )
    assert result == Decimal("0")


def test_compute_soft_sl_insufficient_data():
    """Fewer rows than lookback → None."""
    df = _make_df(n=5)
    result = SLTPCalculator.compute_soft_sl(df, "SELL", lookback=30)
    assert result is None
