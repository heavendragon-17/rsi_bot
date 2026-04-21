"""Unit tests for signal_detection pure helpers."""

from unittest.mock import MagicMock

import pandas as pd

from app.trading.strategy.utils.signal_detection import (
    check_rsi_alignment,
    check_rsi_spread,
    detect_crossover_signal,
)


class TestDetectCrossoverSignal:
    def test_delegates_to_indicators(self):
        indicators = MagicMock()
        indicators.detect_crossover.return_value = True
        df = pd.DataFrame()
        assert detect_crossover_signal(indicators, df, "bearish") is True
        indicators.detect_crossover.assert_called_once_with(df, direction="bearish")


class TestCheckRsiAlignment:
    def test_delegates_to_indicators(self):
        indicators = MagicMock()
        indicators.check_alignment.return_value = False
        df = pd.DataFrame()
        assert check_rsi_alignment(indicators, df, "bullish") is False
        indicators.check_alignment.assert_called_once_with(df, direction="bullish")


class TestCheckRsiSpread:
    def test_none_df_returns_false(self):
        assert check_rsi_spread(None, 1.0) is False

    def test_empty_df_returns_false(self):
        assert check_rsi_spread(pd.DataFrame(), 1.0) is False

    def test_missing_columns_returns_false(self):
        df = pd.DataFrame([{"rsi_ema9": None, "rsi_wma45": None}])
        assert check_rsi_spread(df, 1.0) is False

    def test_spread_above_threshold(self):
        df = pd.DataFrame([{"rsi_ema9": 30.0, "rsi_wma45": 40.0}])
        assert check_rsi_spread(df, 5.0) is True

    def test_spread_below_threshold(self):
        df = pd.DataFrame([{"rsi_ema9": 30.0, "rsi_wma45": 31.0}])
        assert check_rsi_spread(df, 5.0) is False

    def test_nan_values_return_false(self):
        df = pd.DataFrame([{"rsi_ema9": float("nan"), "rsi_wma45": 40.0}])
        assert check_rsi_spread(df, 1.0) is False
