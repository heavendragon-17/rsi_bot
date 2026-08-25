from __future__ import annotations

import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from app.trading.strategy.core_v2_1 import (
    INDICATOR_SEED_CONVENTION,
    INDICATOR_VERSION,
    READINESS_COLUMN,
    atr_wilder,
    compute_alt_h1_indicators,
    compute_btc_h1_indicators,
    compute_btc_h4_indicators,
    compute_m15_indicators,
    ema,
    rsi_wilder,
    wma,
)


def test_indicator_metadata_records_exact_seed_conventions() -> None:
    assert INDICATOR_VERSION == "core-v2.1-indicators-v1"
    assert "first 21 gains/losses" in INDICATOR_SEED_CONVENTION
    assert "first 14 true ranges" in INDICATOR_SEED_CONVENTION
    assert "first TR=high-low" in INDICATOR_SEED_CONVENTION
    assert "alpha=2/(n+1)" in INDICATOR_SEED_CONVENTION
    assert "weights 1..45" in INDICATOR_SEED_CONVENTION


def test_ema_is_seeded_from_first_finite_value() -> None:
    values = pd.Series([math.nan, 1.0, 2.0, 3.0], name="source")
    actual = ema(values, period=3)
    expected = pd.Series([math.nan, 1.0, 1.5, 2.25], name="ema3")
    assert_series_equal(actual, expected)


def test_ema_retains_nan_and_reseeds_after_a_gap() -> None:
    values = pd.Series([1.0, 2.0, math.nan, 10.0, 12.0])
    actual = ema(values, period=3)
    expected = pd.Series([1.0, 1.5, math.nan, 10.0, 11.0], name="ema3")
    assert_series_equal(actual, expected)


def test_wma_uses_linear_weights_one_through_period() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0])
    actual = wma(values, period=3)
    expected = pd.Series(
        [math.nan, math.nan, 14.0 / 6.0, 20.0 / 6.0],
        name="wma3",
    )
    assert_series_equal(actual, expected)


def test_wilder_rsi_has_sma_seed_then_recursive_smoothing() -> None:
    values = pd.Series([1.0, 2.0, 1.0, 3.0, 2.0, 4.0])
    actual = rsi_wilder(values, period=3)
    assert actual.iloc[:3].isna().all()
    assert actual.iloc[3] == pytest.approx(75.0)
    assert actual.iloc[4] == pytest.approx(54.54545454545455)
    assert actual.iloc[5] == pytest.approx(75.0)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (list(range(30)), 100.0),
        (list(range(30, 0, -1)), 0.0),
        ([7.0] * 30, 50.0),
    ],
    ids=["zero-loss", "zero-gain", "flat"],
)
def test_wilder_rsi_handles_zero_denominator_cases(values: list[float], expected: float) -> None:
    actual = rsi_wilder(pd.Series(values), period=21)
    assert actual.iloc[:21].isna().all()
    assert (actual.iloc[21:] == expected).all()


def test_wilder_atr_uses_first_row_high_low_and_recursive_smoothing() -> None:
    high = pd.Series([10.0, 12.0, 13.0, 15.0, 14.0])
    low = pd.Series([8.0, 9.0, 11.0, 12.0, 10.0])
    close = pd.Series([9.0, 11.0, 12.0, 13.0, 11.0])
    actual = atr_wilder(high, low, close, period=3)
    assert actual.iloc[:2].isna().all()
    assert actual.iloc[2] == pytest.approx(7.0 / 3.0)
    assert actual.iloc[3] == pytest.approx(23.0 / 9.0)
    assert actual.iloc[4] == pytest.approx(82.0 / 27.0)


def _ohlc(rows: int = 80) -> pd.DataFrame:
    close = pd.Series([100.0 + index * 0.5 for index in range(rows)])
    return pd.DataFrame(
        {
            "ts": range(rows),
            "open": close - 0.1,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [10.0] * rows,
        }
    )


def test_m15_frame_exposes_warmup_readiness_without_coercing_nan() -> None:
    source = _ohlc()
    actual = compute_m15_indicators(source)
    assert actual.loc[:12, "atr14"].isna().all()
    assert actual.loc[:20, "rsi21"].isna().all()
    assert actual.loc[:64, "rsi_wma45"].isna().all()
    assert not actual.loc[:64, READINESS_COLUMN].any()
    assert actual.loc[65:, READINESS_COLUMN].all()
    assert actual.loc[21:, "rsi21"].eq(100.0).all()
    assert actual.loc[21:, "rsi_ema9"].eq(100.0).all()
    assert actual.loc[65:, "rsi_wma45"].eq(100.0).all()


def test_price_emas_use_first_close_seed() -> None:
    actual = compute_m15_indicators(_ohlc(3))
    assert actual.loc[0, "ema21"] == pytest.approx(100.0)
    assert actual.loc[0, "ema200"] == pytest.approx(100.0)
    expected_ema21_second = (2.0 / 22.0) * 100.5 + (20.0 / 22.0) * 100.0
    assert actual.loc[1, "ema21"] == pytest.approx(expected_ema21_second)


def test_all_timeframe_builders_have_only_their_required_indicator_sets() -> None:
    source = _ohlc()
    alt_h1 = compute_alt_h1_indicators(source)
    btc_h1 = compute_btc_h1_indicators(source)
    btc_h4 = compute_btc_h4_indicators(source)
    for column in ("rsi21", "rsi_ema9", "rsi_wma45", READINESS_COLUMN):
        assert column in alt_h1
        assert column in btc_h1
        assert column in btc_h4
    assert "ema21" not in alt_h1
    assert "ema21" in btc_h1
    assert "ema21" not in btc_h4
    assert alt_h1[READINESS_COLUMN].equals(btc_h4[READINESS_COLUMN])


def test_indicator_builders_are_pure_and_deterministic() -> None:
    source = _ohlc()
    untouched = source.copy(deep=True)
    first = compute_m15_indicators(source)
    second = compute_m15_indicators(source)
    assert_frame_equal(source, untouched)
    assert_frame_equal(first, second)
    assert first is not source


def test_empty_frame_returns_empty_enriched_frame() -> None:
    source = pd.DataFrame(columns=["high", "low", "close"])
    actual = compute_m15_indicators(source)
    assert actual.empty
    for column in ("ema21", "ema200", "atr14", "rsi21", "rsi_ema9", "rsi_wma45"):
        assert column in actual
    assert actual[READINESS_COLUMN].dtype == bool


def test_invalid_ohlc_is_rejected_instead_of_silently_coerced() -> None:
    source = _ohlc(3)
    source.loc[1, "high"] = source.loc[1, "low"] - 1.0
    with pytest.raises(ValueError, match="high cannot be below low"):
        compute_m15_indicators(source)

    source = _ohlc(3)
    source.loc[1, "close"] = math.nan
    with pytest.raises(ValueError, match="finite"):
        compute_m15_indicators(source)


@pytest.mark.parametrize("period", [0, -1, True, 1.5])
def test_indicator_period_must_be_positive_integer(period) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ema(pd.Series([1.0]), period=period)
