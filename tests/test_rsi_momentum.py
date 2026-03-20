"""
Unit tests for RsiMomentumStrategy (SHORT-only entries).

Test categories:
  1. Entry conditions (S1-S5)
  2. Divergence detection
  3. SL/TP computation
  4. Exit management (lock-profit, candle-close SL)
  5. Edge cases (warm-up, ignore existing position)
"""
import unittest
import pandas as pd
import numpy as np
from decimal import Decimal

from app.trading.strategy.rsi_momentum import RsiMomentumStrategy, RsiMomentumConfig
from app.utils.crossover_indicators import CrossoverIndicators
from app.trading.sl_tp_calculator import SLTPCalculator
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.actions import OpenPosition, ClosePosition, MoveSL, DoNothing
from app.core.context import SCANNING


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n: int = 100, base_close: float = 100.0) -> pd.DataFrame:
    """Create an n-row OHLCV DataFrame with flat prices."""
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    df = pd.DataFrame({
        "open": base_close,
        "high": base_close * 1.001,
        "low": base_close * 0.999,
        "close": base_close,
        "volume": 1000.0,
        "closed": True,
    }, index=ts)
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
    rsis[pivot_b] = 65.0    # Lower RSI High → bearish divergence
    # Ensure N bars on each side are strictly lower
    for i in range(pivot_b - N, pivot_b):
        highs[i] = 99.0
    for i in range(pivot_b + 1, min(pivot_b + N + 1, n)):
        highs[i] = 99.0

    df = pd.DataFrame({
        "open": closes,
        "high": highs,
        "low": [c * 0.999 for c in closes],
        "close": closes,
        "volume": 1000.0,
        "closed": True,
        "rsi_14": rsis,
        "rsi_ema9": emas,
        "rsi_wma45": wmas,
    }, index=ts)
    return df


def _make_strategy(cfg_overrides: dict = None) -> RsiMomentumStrategy:
    """Create a strategy instance with a minimal config dict."""
    config = {
        "strategy_params": cfg_overrides or {},
        "bot": {"timeframe": "15m"},
        "risk": {"leverage": 1},
        "backtest": {"initial_balance": 10000},
        "symbols": ["BTC/USDT"],
    }
    return RsiMomentumStrategy(config)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Entry condition tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryConditions(unittest.TestCase):

    def setUp(self):
        self.strategy = _make_strategy()
        self.symbol = "BTC/USDT"
        self.ctx = ContextSnapshot(state=SCANNING)

    def _analyze_with_df(self, df_ind, context=None):
        """Run analyze() with a pre-built indicator DataFrame."""
        ctx = context or self.ctx
        # Patch compute to return the pre-built df
        self.strategy.indicators.compute = lambda d, **kw: df_ind
        return self.strategy.analyze(self.symbol, df_ind, position=None, context=ctx)

    def _short_signal_df(self, spread: float = 5.0, with_crossover: bool = True) -> pd.DataFrame:
        """Return a df_ind that satisfies all S1-S5 conditions.

        Uses _bearish_divergence_df for pivot structure, then overlays
        alignment indicators WITHOUT overwriting the pivot RSI values
        (rsi_14 at n-25 and n-12 must be preserved for divergence detection).
        """
        n = 80
        df = _bearish_divergence_df(n=n)

        # Set EMA9 and WMA45 for alignment/crossover/spread checks
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 45.0 + spread

        # Set rsi_14 for alignment (must be < rsi_ema9=45)
        # Preserve pivot RSI values: pivot_a=rsi_14@n-25=70, pivot_b=rsi_14@n-12=65
        # These satisfy rsi_14 > 45 at pivot positions, BUT check_alignment uses
        # only the LAST row (df.iloc[-1]), so setting last row's rsi_14=40 is sufficient.
        df["rsi_14"] = 40.0
        # Restore pivot RSI values needed for divergence detection
        pivot_a_idx = n - 25
        pivot_b_idx = n - 12
        df.iloc[pivot_a_idx, df.columns.get_loc("rsi_14")] = 70.0
        df.iloc[pivot_b_idx, df.columns.get_loc("rsi_14")] = 65.0

        if with_crossover:
            # Previous candle: EMA9 >= WMA45 to create a bearish crossover
            df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 55.0
            df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 55.0 - spread

        return df

    def test_short_entry_all_conditions_met(self):
        """S1-S5 all true → OpenPosition(side='SELL')"""
        df = self._short_signal_df()
        result = self._analyze_with_df(df)
        self.assertEqual(len(result.actions), 1)
        action = result.actions[0]
        self.assertIsInstance(action, OpenPosition)
        self.assertEqual(action.side, "SELL")
        self.assertEqual(action.symbol, self.symbol)

    def test_short_entry_no_crossover_no_history(self):
        """Alignment holds but no crossover ever fired → DoNothing"""
        df = _bearish_divergence_df(n=80)
        # Bearish alignment on both prev and current → no crossover
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        # No crossover (EMA was already below WMA on prev candle too)
        result = self._analyze_with_df(df)
        actions = result.actions
        self.assertIsInstance(actions[0], DoNothing)

    def test_short_entry_alignment_broken(self):
        """RSI > EMA9 → alignment fails → DoNothing"""
        df = _bearish_divergence_df(n=80)
        df["rsi_14"] = 55.0   # RSI > EMA9
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        result = self._analyze_with_df(df)
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_short_entry_spread_too_narrow(self):
        """(WMA45 - EMA9) <= 2.5 → S4 fails → DoNothing"""
        df = _bearish_divergence_df(n=80)
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 47.5
        df["rsi_wma45"] = 50.0  # spread = 2.5, not > 2.5
        # Add crossover
        df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
        df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0
        result = self._analyze_with_df(df)
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_short_entry_no_divergence(self):
        """No swing highs in lookback → S5 fails → DoNothing"""
        df = _make_df(n=80, base_close=100.0)
        # Inject flat highs — no pivot will be detected
        df["high"] = 100.5
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        # Add crossover
        df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
        df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0
        result = self._analyze_with_df(df)
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_short_entry_flexible_signal_persistence(self):
        """
        Crossover fires on candle N, alignment still holds on N+1 → OpenPosition.
        Context carries crossover_detected=True from N.
        """
        n = 80
        df = _bearish_divergence_df(n=n)
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        df["rsi_14"] = 40.0
        # Restore pivot RSI values
        df.iloc[n - 25, df.columns.get_loc("rsi_14")] = 70.0
        df.iloc[n - 12, df.columns.get_loc("rsi_14")] = 65.0
        # No crossover on this candle (EMA was already below WMA prev candle too)
        # But crossover_detected=True in context (from a previous candle)
        ctx_with_crossover = ContextSnapshot(
            state=SCANNING,
            meta={"crossover_detected": True},
        )
        result = self._analyze_with_df(df, context=ctx_with_crossover)
        action = result.actions[0]
        self.assertIsInstance(action, OpenPosition)
        self.assertEqual(action.side, "SELL")

    def test_short_entry_signal_expires_when_alignment_breaks(self):
        """Crossover detected before, but now RSI > EMA9 → signal expired → DoNothing"""
        df = _make_df(n=80)
        df["rsi_14"] = 55.0  # broken alignment
        df["rsi_ema9"] = 48.0
        df["rsi_wma45"] = 52.0
        ctx_with_crossover = ContextSnapshot(
            state=SCANNING,
            meta={"crossover_detected": True},
        )
        result = self._analyze_with_df(df, context=ctx_with_crossover)
        self.assertIsInstance(result.actions[0], DoNothing)
        # Flag should be reset
        self.assertFalse(result.new_context.meta.get("crossover_detected", False))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Divergence detection tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDivergenceDetection(unittest.TestCase):

    def setUp(self):
        self.ind = CrossoverIndicators()

    def test_bearish_divergence_detected(self):
        """Price HH + RSI LH → True"""
        df = _bearish_divergence_df(n=80)
        # lookback=30 captures both pivot_a (at n-25=55) and pivot_b (at n-12=68)
        result = self.ind.detect_bearish_divergence(df, lookback=30, pivot_strength=5)
        self.assertTrue(result)

    def test_no_divergence_insufficient_pivots(self):
        """Flat highs — fewer than 2 swing highs → False"""
        df = _make_df(n=80)
        df["rsi_14"] = 45.0
        df["high"] = 100.5  # all same → no pivots
        result = self.ind.detect_bearish_divergence(df, lookback=60, pivot_strength=5)
        self.assertFalse(result)

    def test_divergence_outside_lookback_ignored(self):
        """Divergence exists but only outside the lookback window → False"""
        df = _bearish_divergence_df(n=80)
        # Only look at last 10 candles — divergence is at indices 10 and 25
        result = self.ind.detect_bearish_divergence(df, lookback=5, pivot_strength=1)
        self.assertFalse(result)

    def test_no_divergence_when_rsi_also_higher(self):
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

        df = pd.DataFrame({
            "open": 100.0, "high": highs, "low": 99.5,
            "close": 100.0, "volume": 1000.0, "closed": True,
            "rsi_14": rsis, "rsi_ema9": 50.0, "rsi_wma45": 55.0,
        }, index=ts)
        result = self.ind.detect_bearish_divergence(df, lookback=50, pivot_strength=5)
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# 3. SL/TP computation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSLTPCalculation(unittest.TestCase):

    def setUp(self):
        self.symbol = "BTC/USDT"

    def test_sl_is_highest_high_30_candles(self):
        """compute_soft_sl for SHORT = max high in lookback window."""
        df = _make_df(n=50, base_close=100.0)
        df["high"] = 100.5
        df.loc[df.index[-15], "high"] = 115.0  # The highest high in the last 30 candles

        sl = SLTPCalculator.compute_soft_sl(df, side="SELL", lookback=30)
        self.assertIsNotNone(sl)
        self.assertEqual(sl, Decimal("115.0"))

    def test_sl_long_is_lowest_low(self):
        """compute_soft_sl for LONG = min low in lookback window."""
        df = _make_df(n=50, base_close=100.0)
        df["low"] = 99.5
        df.loc[df.index[-10], "low"] = 85.0

        sl = SLTPCalculator.compute_soft_sl(df, side="BUY", lookback=30)
        self.assertIsNotNone(sl)
        self.assertEqual(sl, Decimal("85.0"))

    def test_disaster_sl_short_at_3x(self):
        """Short disaster SL = entry + 3 × (soft_sl - entry)."""
        entry = Decimal("100")
        soft_sl = Decimal("105")  # 5 points above entry for short
        disaster = SLTPCalculator.compute_disaster_sl(entry, soft_sl, "SELL", Decimal("3"))
        expected = entry + (soft_sl - entry) * Decimal("3")
        self.assertEqual(disaster, expected)  # = 115

    def test_disaster_sl_long_at_3x(self):
        """Long disaster SL = entry - 3 × (entry - soft_sl)."""
        entry = Decimal("100")
        soft_sl = Decimal("95")  # 5 points below entry for long
        disaster = SLTPCalculator.compute_disaster_sl(entry, soft_sl, "BUY", Decimal("3"))
        expected = entry - (entry - soft_sl) * Decimal("3")
        self.assertEqual(disaster, expected)  # = 85

    def test_sl_equals_entry_skipped_in_strategy(self):
        """If soft SL <= entry for short, strategy returns DoNothing."""
        strategy = _make_strategy()
        df = _bearish_divergence_df(n=80)
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        # Force all highs to be exactly at entry price (or lower)
        df["high"] = 100.0
        df["close"] = 100.0

        # Inject crossover
        df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
        df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0

        strategy.indicators.compute = lambda d, **kw: df
        result = strategy.analyze("BTC/USDT", df, position=None, context=ContextSnapshot(state=SCANNING))
        # soft_sl (max high = 100) == entry (close = 100) → skip
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_tp_prices_below_entry_for_short(self):
        """All TP levels should be below the entry price for a short."""
        entry = Decimal("100")
        sl = Decimal("105")  # SL above entry for short
        for rr in [Decimal("1"), Decimal("2"), Decimal("3")]:
            tp = SLTPCalculator.compute_tp_price(entry, sl, "SELL", rr)
            self.assertIsNotNone(tp)
            self.assertLess(tp, entry, f"TP at {rr}R should be below entry for short")

    def test_tp_prices_above_entry_for_long(self):
        """All TP levels should be above the entry price for a long."""
        entry = Decimal("100")
        sl = Decimal("95")  # SL below entry for long
        for rr in [Decimal("1"), Decimal("2"), Decimal("3")]:
            tp = SLTPCalculator.compute_tp_price(entry, sl, "BUY", rr)
            self.assertIsNotNone(tp)
            self.assertGreater(tp, entry, f"TP at {rr}R should be above entry for long")

    def test_tp_zero_risk_returns_none(self):
        """Zero risk distance → compute_tp_price returns None."""
        entry = Decimal("100")
        sl = Decimal("100")  # same as entry
        result = SLTPCalculator.compute_tp_price(entry, sl, "SELL", Decimal("1"))
        self.assertIsNone(result)

    def test_lock_profit_short_below_entry(self):
        """Lock-profit price for short should be below the entry price."""
        entry = Decimal("100")
        soft_sl = Decimal("105")  # SL above entry for short
        lock = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry,
            soft_sl_price=soft_sl,
            side="SELL",
            lock_profit_rr=Decimal("0.2"),
        )
        self.assertIsNotNone(lock)
        self.assertLess(lock, entry, "Lock-profit SL should be below entry for short")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Exit management tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExitManagement(unittest.TestCase):

    def setUp(self):
        self.strategy = _make_strategy()
        self.symbol = "BTC/USDT"
        self.entry = Decimal("100")
        self.soft_sl = Decimal("105")  # Short: SL above entry

    def _open_position(self) -> PositionSnapshot:
        return PositionSnapshot(
            has_position=True,
            symbol=self.symbol,
            side="SELL",
            entry_price=self.entry,
            current_sl=self.soft_sl,
        )

    def _base_context(self, extra: dict = None) -> ContextSnapshot:
        meta = {
            "entry_price": self.entry,
            "sl_price": self.soft_sl,
            "soft_sl_price": self.soft_sl,
            "original_soft_sl": self.soft_sl,
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
        }
        if extra:
            meta.update(extra)
        return ContextSnapshot(state=SCANNING, soft_sl_price=self.soft_sl, meta=meta)

    def _df_with_candle(self, open_: float, high: float, low: float, close: float, n: int = 80) -> pd.DataFrame:
        df = _make_df(n=n, base_close=open_)
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        # Last candle custom OHLC
        df.iloc[-1, df.columns.get_loc("open")] = open_
        df.iloc[-1, df.columns.get_loc("high")] = high
        df.iloc[-1, df.columns.get_loc("low")] = low
        df.iloc[-1, df.columns.get_loc("close")] = close
        return df

    def _analyze_exit(self, df, context):
        position = self._open_position()
        self.strategy.indicators.compute = lambda d, **kw: df
        return self.strategy.analyze(self.symbol, df, position=position, context=context)

    def test_lock_profit_triggered_when_price_drops(self):
        """
        For a short, when low <= move_trigger (price moved in our favor),
        strategy should emit MoveSL to lock-profit level.
        """
        # move_trigger for short ≈ entry - 0.5 * risk = 100 - 0.5*5 = 97.5 (approx)
        # We use a very low price to ensure the trigger fires
        df = self._df_with_candle(open_=100, high=100.5, low=90.0, close=91.0)
        ctx = self._base_context()
        result = self._analyze_exit(df, ctx)
        move_sl_actions = [a for a in result.actions if isinstance(a, MoveSL)]
        self.assertTrue(len(move_sl_actions) > 0, "Should emit MoveSL when price drops sufficiently")

    def test_candle_close_sl_flags_when_close_above_soft_sl(self):
        """
        For a short, close >= soft_sl (price went AGAINST us) → set pending_candle_sl flag.
        """
        df = self._df_with_candle(open_=100, high=106, low=99, close=106.0)
        ctx = self._base_context()
        result = self._analyze_exit(df, ctx)
        self.assertIsInstance(result.actions[0], DoNothing)
        self.assertTrue(result.new_context.meta.get("pending_candle_sl", False))

    def test_pending_sl_closes_on_next_candle(self):
        """
        When pending_candle_sl is True, next candle open → ClosePosition(reason=CLOSE_BY_CANDLE_SL).
        """
        next_open = 104.0
        df = self._df_with_candle(open_=next_open, high=105, low=103, close=104)
        ctx = self._base_context({"pending_candle_sl": True})
        result = self._analyze_exit(df, ctx)
        close_actions = [a for a in result.actions if isinstance(a, ClosePosition)]
        self.assertTrue(len(close_actions) > 0)
        self.assertEqual(close_actions[0].reason, "CLOSE_BY_CANDLE_SL")
        self.assertEqual(close_actions[0].price, Decimal(str(next_open)))

    def test_wick_above_sl_no_close(self):
        """
        A wick above soft SL (high > soft_sl but close < soft_sl) must NOT trigger close.
        """
        # close < soft_sl=105 → no trigger
        df = self._df_with_candle(open_=100, high=108, low=99, close=103.0)
        ctx = self._base_context()
        result = self._analyze_exit(df, ctx)
        has_close = any(isinstance(a, ClosePosition) for a in result.actions)
        self.assertFalse(has_close)
        self.assertFalse(result.new_context.meta.get("pending_candle_sl", False))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def setUp(self):
        self.strategy = _make_strategy()
        self.symbol = "BTC/USDT"

    def test_warmup_insufficient_candles(self):
        """Fewer candles than min_candles → DoNothing (warm-up)."""
        df = _make_df(n=10)  # far fewer than 75
        result = self.strategy.analyze(self.symbol, df)
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_ignore_new_entry_when_position_open(self):
        """If position already exists, strategy manages exit, not entry."""
        position = PositionSnapshot(
            has_position=True,
            symbol=self.symbol,
            side="SELL",
            entry_price=Decimal("100"),
            current_sl=Decimal("105"),
        )
        n = 80
        df = _bearish_divergence_df(n=n)
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        # Restore pivot RSI values
        df.iloc[n - 25, df.columns.get_loc("rsi_14")] = 70.0
        df.iloc[n - 12, df.columns.get_loc("rsi_14")] = 65.0
        # Add crossover
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
        self.strategy.indicators.compute = lambda d, **kw: df
        result = self.strategy.analyze(self.symbol, df, position=position, context=ctx)
        # Should never return OpenPosition when a position is already open
        has_open = any(isinstance(a, OpenPosition) for a in result.actions)
        self.assertFalse(has_open, "Should not open a second position while one is active")

    def test_zero_risk_distance_returns_do_nothing(self):
        """soft_sl == entry price for short → zero risk → DoNothing."""
        df = _bearish_divergence_df(n=80)
        df["rsi_14"] = 40.0
        df["rsi_ema9"] = 45.0
        df["rsi_wma45"] = 50.0
        df["high"] = 100.0   # highest high = 100 = close = 100 → zero risk
        df["close"] = 100.0

        # Add crossover
        df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 51.0
        df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 49.0

        self.strategy.indicators.compute = lambda d, **kw: df
        result = self.strategy.analyze(self.symbol, df, position=None)
        self.assertIsInstance(result.actions[0], DoNothing)

    def test_crossover_detection_requires_strict_inequality(self):
        """EMA9 == WMA45 on both candles → not a crossover."""
        ind = CrossoverIndicators()
        df = _make_df(n=10)
        df["rsi_14"] = 50.0
        df["rsi_ema9"] = 50.0   # EMA == WMA: no crossover
        df["rsi_wma45"] = 50.0
        self.assertFalse(ind.detect_crossover(df, direction="bearish"))
        self.assertFalse(ind.detect_crossover(df, direction="bullish"))

    def test_loader_registers_rsi_momentum(self):
        """rsi_momentum should be available in the strategy loader."""
        from app.trading.strategy.loader import STRATEGY_MAP
        self.assertIn("rsi_momentum", STRATEGY_MAP)
        from app.trading.strategy.rsi_momentum import RsiMomentumStrategy
        self.assertIs(STRATEGY_MAP["rsi_momentum"], RsiMomentumStrategy)

    def test_open_position_action_supports_sell_side(self):
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
        self.assertEqual(action.side, "SELL")


# ─────────────────────────────────────────────────────────────────────────────
# 6. SLTPCalculator static method tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSLTPCalculatorStatic(unittest.TestCase):

    def test_position_size_direction_agnostic(self):
        """Position sizing uses absolute distance — same result for both sides."""
        entry = Decimal("100")
        sl_long = Decimal("95")   # 5% below entry
        sl_short = Decimal("105") # 5% above entry

        size_long = SLTPCalculator.compute_position_size(
            entry, sl_long, Decimal("10000"), Decimal("0.02"), Decimal("10")
        )
        size_short = SLTPCalculator.compute_position_size(
            entry, sl_short, Decimal("10000"), Decimal("0.02"), Decimal("10")
        )
        # Both have 5% SL distance → same notional risk → same size
        self.assertAlmostEqual(float(size_long), float(size_short), places=6)

    def test_position_size_zero_on_zero_distance(self):
        """SL == entry → returns 0."""
        result = SLTPCalculator.compute_position_size(
            Decimal("100"), Decimal("100"), Decimal("10000"), Decimal("0.02"), Decimal("10")
        )
        self.assertEqual(result, Decimal("0"))

    def test_compute_soft_sl_insufficient_data(self):
        """Fewer rows than lookback → None."""
        df = _make_df(n=5)
        result = SLTPCalculator.compute_soft_sl(df, "SELL", lookback=30)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
