"""Tests for Indicators class (M14 coverage gap)."""

import numpy as np
import pandas as pd
import pytest

from app.data.indicators import Indicators


@pytest.fixture
def indicators():
    return Indicators(enable_cache=False)


def _make_ohlcv(n=100, trend="flat"):
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    if trend == "flat":
        close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    elif trend == "up":
        close = 100.0 + np.arange(n) * 0.5 + np.random.randn(n) * 0.2
    else:
        close = 100.0 - np.arange(n) * 0.5 + np.random.randn(n) * 0.2
    df = pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + abs(np.random.randn(n) * 0.3),
            "low": close - abs(np.random.randn(n) * 0.3),
            "close": close,
            "volume": np.random.randint(100, 10000, n).astype(float),
            "ts": np.arange(n),
        }
    )
    return df


class TestCompute:
    def test_returns_expected_columns(self, indicators):
        df = _make_ohlcv(100)
        out = indicators.compute(df)
        assert "rsi_14" in out.columns
        assert "rsi_ema9" in out.columns
        assert "rsi_wma45" in out.columns

    def test_compute_with_price_emas(self):
        ind = Indicators(include_price_emas=True, enable_cache=False)
        df = _make_ohlcv(100)
        out = ind.compute(df)
        assert "ema21" in out.columns
        assert "ema200" in out.columns

    def test_empty_dataframe(self, indicators):
        df = pd.DataFrame()
        out = indicators.compute(df)
        assert out.empty

    def test_none_dataframe(self, indicators):
        out = indicators.compute(None)
        assert isinstance(out, pd.DataFrame)
        assert out.empty

    def test_short_dataframe_computes(self, indicators):
        df = _make_ohlcv(5)
        out = indicators.compute(df)
        assert "rsi_14" in out.columns
        assert len(out) == 5


class TestCrossover:
    def test_detect_bearish_crossover(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_ema9": [55.0, 50.0, 45.0],
                "rsi_wma45": [50.0, 50.0, 50.0],
            }
        )
        # prev: ema9(50) >= wma45(50), curr: ema9(45) < wma45(50) → bearish
        assert indicators.detect_crossover(df, direction="bearish")

    def test_detect_bullish_crossover(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_ema9": [45.0, 50.0, 55.0],
                "rsi_wma45": [50.0, 50.0, 50.0],
            }
        )
        # prev: ema9(50) <= wma45(50), curr: ema9(55) > wma45(50) → bullish
        assert indicators.detect_crossover(df, direction="bullish")

    def test_no_crossover(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_ema9": [55.0, 55.0],
                "rsi_wma45": [50.0, 50.0],
            }
        )
        assert not indicators.detect_crossover(df, direction="bearish")

    def test_short_df_returns_false(self, indicators):
        df = pd.DataFrame({"rsi_ema9": [50.0], "rsi_wma45": [50.0]})
        assert not indicators.detect_crossover(df)


class TestAlignment:
    def test_bearish_alignment(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_14": [30.0],
                "rsi_ema9": [40.0],
                "rsi_wma45": [50.0],
            }
        )
        assert indicators.check_alignment(df, direction="bearish")

    def test_bullish_alignment(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_14": [70.0],
                "rsi_ema9": [60.0],
                "rsi_wma45": [50.0],
            }
        )
        assert indicators.check_alignment(df, direction="bullish")

    def test_no_alignment(self, indicators):
        df = pd.DataFrame(
            {
                "rsi_14": [50.0],
                "rsi_ema9": [40.0],
                "rsi_wma45": [45.0],
            }
        )
        assert not indicators.check_alignment(df, direction="bearish")


class TestDivergence:
    def test_detect_bearish_divergence(self, indicators):
        """Craft data with price higher high but RSI lower high."""
        n = 40
        high = np.full(n, 100.0)
        rsi = np.full(n, 50.0)

        # First swing high at index 10
        high[10] = 110.0
        rsi[10] = 70.0
        # Second swing high at index 25 (higher price, lower RSI)
        high[25] = 115.0
        rsi[25] = 65.0

        # Ensure surrounding bars are lower for pivot detection
        for i in range(5, 16):
            if i != 10:
                high[i] = min(high[i], 105.0)
        for i in range(20, 31):
            if i != 25:
                high[i] = min(high[i], 110.0)

        df = pd.DataFrame({"high": high, "rsi_14": rsi})
        assert indicators.detect_bearish_divergence(df, lookback=40, pivot_strength=5)

    def test_no_divergence_short_df(self, indicators):
        df = pd.DataFrame({"high": [100.0] * 5, "rsi_14": [50.0] * 5})
        assert not indicators.detect_bearish_divergence(df, lookback=30)


class TestLast:
    def test_last_returns_dict(self, indicators):
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0], "rsi_14": [40.0, 50.0, 60.0]})
        result = Indicators.last(df)
        assert result["close"] == 3.0
        assert result["rsi_14"] == 60.0

    def test_last_empty_df(self, indicators):
        assert Indicators.last(pd.DataFrame()) == {}
        assert Indicators.last(None) == {}
