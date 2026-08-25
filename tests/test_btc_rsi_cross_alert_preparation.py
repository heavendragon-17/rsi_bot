"""Tests for pure BTC RSI cross alert preparation (point-in-time slicing,
bootstrap eligibility, continuity, finiteness, indicator window locking)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    H4_DURATION,
    TRIGGER_DURATION_BY_TIMEFRAME,
    candle_close_time,
    expected_h4_close_for,
    normalize_candle_open,
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.core_v2_1.indicators import ema, rsi_wilder, wma

UTC = UTC
STORAGE_SHIFT = timedelta(hours=7)

# Fixed scenario instants (all UTC):
#   H4 candles close ..., 04:00, 08:00; the trigger candle closes 09:35.
BASE_DATE = datetime(2026, 8, 24, tzinfo=UTC)
TRIGGER_TF = "5m"
TRIGGER_DURATION = TRIGGER_DURATION_BY_TIMEFRAME[TRIGGER_TF]
TRIGGER_CLOSE = BASE_DATE.replace(hour=9, minute=35)
EXPECTED_H4_CLOSE = BASE_DATE.replace(hour=8)
READY_AT = BASE_DATE.replace(hour=9)  # after 08:00 H4 close, before 09:35


def _utc_close_times(end: datetime, count: int, step: timedelta) -> list[datetime]:
    return [end - step * (count - 1 - i) for i in range(count)]


def _storage_index(
    close_times: list[datetime], step: timedelta, *, aware: bool = False
) -> list:
    """Index values as the multiplexer stores them (open time).

    Default mirrors ``DataNormalizer``: naive wall-clock UTC+07:00 of the
    open instant. ``aware=True`` stores timezone-aware UTC opens instead.
    """
    values = []
    for close_time in close_times:
        open_utc = close_time - step
        if aware:
            values.append(pd.Timestamp(open_utc))
        else:
            values.append(pd.Timestamp((open_utc + STORAGE_SHIFT).replace(tzinfo=None)))
    return values


def _frame(
    close_times: list[datetime],
    *,
    step: timedelta,
    closes: list[float] | None = None,
    closed: list[bool] | None = None,
    aware_index: bool = False,
    extra_rows: list[tuple[object, bool, float]] | None = None,
) -> pd.DataFrame:
    n = len(close_times)
    closes = closes if closes is not None else [100.0 + i for i in range(n)]
    closed = closed if closed is not None else [True] * n
    index = _storage_index(close_times, step, aware=aware_index)
    data = {"close": closes, "closed": closed}
    if extra_rows:
        for index_value, row_closed, row_close in extra_rows:
            index.append(index_value)
            data["close"].append(row_close)
            data["closed"].append(row_closed)
    frame = pd.DataFrame(data, index=pd.Index(index, name="timestamp"))
    return frame


def _trigger_frame(
    *,
    end: datetime = TRIGGER_CLOSE,
    count: int = 80,
    closes: list[float] | None = None,
    closed: list[bool] | None = None,
    aware_index: bool = False,
    extra_rows=None,
) -> pd.DataFrame:
    return _frame(
        _utc_close_times(end, count, TRIGGER_DURATION),
        step=TRIGGER_DURATION,
        closes=closes,
        closed=closed,
        aware_index=aware_index,
        extra_rows=extra_rows,
    )


def _h4_frame(
    *,
    end: datetime = EXPECTED_H4_CLOSE,
    count: int = 70,
    closes: list[float] | None = None,
    closed: list[bool] | None = None,
    aware_index: bool = False,
    extra_rows=None,
) -> pd.DataFrame:
    return _frame(
        _utc_close_times(end, count, H4_DURATION),
        step=H4_DURATION,
        closes=closes,
        closed=closed,
        aware_index=aware_index,
        extra_rows=extra_rows,
    )


def _prepare(
    trigger_df,
    h4_df,
    *,
    timeframe=TRIGGER_TF,
    observed=frozenset(),
    open_value=None,
):
    return prepare_btc_rsi_cross_input(
        trigger_df,
        h4_df,
        symbol="BTC/USDT",
        trigger_timeframe=timeframe,
        trigger_open_time=open_value if open_value is not None else trigger_df.index[-1],
        history_ready_at=READY_AT,
        observed_live_h4_closes=observed,
    )


def _bundle_of(closes: list[float]) -> tuple[float, float, float]:
    series = pd.Series(closes, dtype="float64")
    rsi21 = rsi_wilder(series, 21)
    ema9 = ema(rsi21, 9)
    wma45 = wma(rsi21, 45)
    return (
        float(rsi21.iloc[-1]),
        float(ema9.iloc[-1]),
        float(wma45.iloc[-1]),
    )


class TestReadyBaseline:
    def test_default_frames_are_ready(self):
        prep = _prepare(_trigger_frame(), _h4_frame())
        assert prep.reason == "READY"
        assert prep.input is not None
        assert prep.input.trigger_close_time == TRIGGER_CLOSE
        assert prep.input.h4_close_time == EXPECTED_H4_CLOSE
        assert prep.input.symbol == "BTC/USDT"
        assert prep.input.trigger_timeframe == "5m"
        assert isinstance(prep.input.trigger_close_price, Decimal)

    def test_input_is_not_none_exactly_when_ready(self):
        ready = _prepare(_trigger_frame(), _h4_frame())
        assert (ready.input is not None) == (ready.reason == "READY")
        # Ask for a close time that is absent from the frame entirely.
        missing_open = _storage_index([TRIGGER_CLOSE], TRIGGER_DURATION)[0]
        missing = _prepare(
            _trigger_frame(end=TRIGGER_CLOSE - TRIGGER_DURATION),
            _h4_frame(),
            open_value=missing_open,
        )
        assert missing.reason == "TRIGGER_CURRENT_ROW_MISSING"
        assert missing.input is None

    def test_fifteen_minute_trigger_supported(self):
        tf = "15m"
        duration = TRIGGER_DURATION_BY_TIMEFRAME[tf]
        end = BASE_DATE.replace(hour=9, minute=45)
        trigger = _frame(
            _utc_close_times(end, 80, duration), step=duration
        )
        prep = prepare_btc_rsi_cross_input(
            trigger,
            _h4_frame(),
            symbol="BTC/USDT",
            trigger_timeframe=tf,
            trigger_open_time=trigger.index[-1],
            history_ready_at=READY_AT,
            observed_live_h4_closes=frozenset(),
        )
        assert prep.reason == "READY"
        assert prep.input.trigger_close_time == end


class TestTimestampNormalization:
    def test_naive_stored_opens_are_utc_plus_seven_advanced_once(self):
        # The stored naive value is the OPEN instant rendered in UTC+07
        # wall-clock: 09:30 UTC open -> 16:30 naive. Normalizing interprets
        # it as fixed UTC+07:00 exactly once and yields 09:30 UTC; the close
        # adds the 5m timeframe once more.
        raw_last = _trigger_frame().index[-1]
        assert raw_last.tzinfo is None
        assert raw_last == pd.Timestamp(datetime(2026, 8, 24, 16, 30))

        normalized_open = normalize_candle_open(raw_last)
        assert normalized_open == datetime(2026, 8, 24, 9, 30, tzinfo=UTC)

        close = candle_close_time(raw_last, TRIGGER_DURATION)
        assert close == TRIGGER_CLOSE

    def test_aware_timestamps_preserve_instant_without_second_shift(self):
        aware_trigger = _trigger_frame(aware_index=True)
        aware_h4 = _h4_frame(aware_index=True)
        prep = _prepare(aware_trigger, aware_h4)
        assert prep.reason == "READY"
        assert prep.input.trigger_close_time == TRIGGER_CLOSE
        assert prep.input.h4_close_time == EXPECTED_H4_CLOSE

    def test_naive_and_aware_frames_agree(self):
        naive_prep = _prepare(_trigger_frame(), _h4_frame())
        aware_prep = _prepare(_trigger_frame(aware_index=True), _h4_frame(aware_index=True))
        assert naive_prep.input.current_trigger == aware_prep.input.current_trigger
        assert naive_prep.input.previous_trigger == aware_prep.input.previous_trigger
        assert naive_prep.input.h4 == aware_prep.input.h4

    def test_expected_h4_close_is_native_utc_boundary(self):
        assert expected_h4_close_for(TRIGGER_CLOSE) == EXPECTED_H4_CLOSE
        assert expected_h4_close_for(EXPECTED_H4_CLOSE) == EXPECTED_H4_CLOSE
        assert expected_h4_close_for(EXPECTED_H4_CLOSE - timedelta(seconds=1)) == (
            EXPECTED_H4_CLOSE - H4_DURATION
        )

    def test_naive_history_ready_or_observed_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            prepare_btc_rsi_cross_input(
                _trigger_frame(),
                _h4_frame(),
                symbol="BTC/USDT",
                trigger_timeframe="5m",
                trigger_open_time=_trigger_frame().index[-1],
                history_ready_at=READY_AT.replace(tzinfo=None),
                observed_live_h4_closes=frozenset(),
            )


class TestExactRowSelection:
    def test_current_and_previous_trigger_rows_as_of_t(self):
        frame = _trigger_frame()
        prep = _prepare(frame, _h4_frame())
        closes = [float(v) for v in frame["close"]]
        expected_current = _bundle_of(closes)
        expected_previous = _bundle_of(closes[:-1])
        current = prep.input.current_trigger
        previous = prep.input.previous_trigger
        assert (current.rsi21, current.rsi_ema9, current.rsi_wma45) == pytest.approx(expected_current)
        assert (
            previous.rsi21,
            previous.rsi_ema9,
            previous.rsi_wma45,
        ) == pytest.approx(expected_previous)

    def test_future_trigger_candle_never_used(self):
        frame_with_future = _trigger_frame(
            extra_rows=[
                (_storage_index([TRIGGER_CLOSE + TRIGGER_DURATION], TRIGGER_DURATION)[0], True, 999.0)
            ]
        )
        # Evaluate the REAL current candle (second-to-last stored row), not
        # the appended future row.
        open_value = _trigger_frame().index[-1]
        prep = _prepare(frame_with_future, _h4_frame(), open_value=open_value)
        assert prep.reason == "READY"
        closes = [float(v) for v in frame_with_future["close"]][:-1]
        assert (prep.input.current_trigger.rsi21,) == pytest.approx((_bundle_of(closes)[0],))

    def test_forming_current_trigger_row_is_missing(self):
        flags = [True] * 80
        flags[-1] = False
        prep = _prepare(_trigger_frame(closed=flags), _h4_frame())
        assert prep.reason == "TRIGGER_CURRENT_ROW_MISSING"

    def test_missing_current_row(self):
        # The frame ends one interval BEFORE T; nothing closes exactly at T.
        missing_open = _storage_index([TRIGGER_CLOSE], TRIGGER_DURATION)[0]
        prep = _prepare(
            _trigger_frame(end=TRIGGER_CLOSE - TRIGGER_DURATION),
            _h4_frame(),
            open_value=missing_open,
        )
        assert prep.reason == "TRIGGER_CURRENT_ROW_MISSING"

    def test_exact_h4_selected_as_of_t(self):
        prep = _prepare(_trigger_frame(), _h4_frame())
        h4_closes = [float(v) for v in _h4_frame()["close"]]
        expected = _bundle_of(h4_closes)
        h4 = prep.input.h4
        assert (h4.rsi21, h4.rsi_ema9, h4.rsi_wma45) == pytest.approx(expected)

    def test_future_forming_h4_candle_never_used(self):
        # A later H4 row exists (closes 12:00 > T) and the expected 08:00 row
        # is marked forming → the 08:00 context must be reported missing.
        future_open = _storage_index(
            [EXPECTED_H4_CLOSE + H4_DURATION], H4_DURATION
        )[0]
        flags = [True] * 70
        flags[-1] = False
        frame = _h4_frame(closed=flags, extra_rows=[(future_open, False, 999.0)])
        prep = _prepare(_trigger_frame(), frame)
        assert prep.reason == "H4_EXPECTED_CLOSE_MISSING"

    def test_h4_row_after_t_is_excluded(self):
        future_open = _storage_index(
            [EXPECTED_H4_CLOSE + H4_DURATION], H4_DURATION
        )[0]
        frame = _h4_frame(extra_rows=[(future_open, True, 999.0)])
        prep = _prepare(_trigger_frame(), frame)
        assert prep.reason == "READY"
        h4_closes = [float(v) for v in _h4_frame()["close"]]
        assert (prep.input.h4.rsi21,) == pytest.approx((_bundle_of(h4_closes)[0],))


class TestLiveH4Confirmation:
    def test_post_bootstrap_h4_requires_observed_membership(self):
        late_h4_close = BASE_DATE.replace(hour=12)  # > READY_AT
        trigger_end = BASE_DATE.replace(hour=12, minute=5)
        trigger = _trigger_frame(end=trigger_end)
        h4 = _h4_frame(end=late_h4_close, count=70)
        common = dict(
            symbol="BTC/USDT",
            trigger_timeframe="5m",
            history_ready_at=READY_AT,
        )
        unconfirmed = prepare_btc_rsi_cross_input(
            trigger,
            h4,
            trigger_open_time=trigger.index[-1],
            observed_live_h4_closes=frozenset(),
            **common,
        )
        assert unconfirmed.reason == "H4_LIVE_CLOSE_UNCONFIRMED"

        confirmed = prepare_btc_rsi_cross_input(
            trigger,
            h4,
            trigger_open_time=trigger.index[-1],
            observed_live_h4_closes=frozenset({late_h4_close}),
            **common,
        )
        assert confirmed.reason == "READY"

    def test_pre_bootstrap_h4_trusted_without_observation(self):
        prep = _prepare(_trigger_frame(), _h4_frame(), observed=frozenset())
        assert prep.reason == "READY"


class TestReadinessBoundaries:
    @pytest.mark.parametrize(
        "rows, ready", [(66, False), (67, True), (80, True)]
    )
    def test_trigger_boundary(self, rows, ready):
        prep = _prepare(_trigger_frame(count=rows), _h4_frame())
        assert (prep.reason == "READY") is ready
        if not ready:
            assert prep.reason == "TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY"

    @pytest.mark.parametrize("rows, ready", [(65, False), (66, True)])
    def test_h4_boundary(self, rows, ready):
        prep = _prepare(_trigger_frame(count=90), _h4_frame(count=rows))
        assert (prep.reason == "READY") is ready
        if not ready:
            assert prep.reason == "H4_INSUFFICIENT_CONTIGUOUS_HISTORY"

    def test_unsupported_timeframe(self):
        prep = _prepare(_trigger_frame(), _h4_frame(), timeframe="1h")
        assert prep.reason == "TRIGGER_UNSUPPORTED_TIMEFRAME"
        assert prep.input is None


class TestDataIntegrity:
    def test_duplicate_trigger_times_rejected(self):
        frame = _trigger_frame()
        dup_value = frame.index[-2]
        extra = [(dup_value, True, 123.0)]
        prep = _prepare(_trigger_frame(extra_rows=extra), _h4_frame())
        assert prep.reason == "TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME"

    def test_backward_trigger_times_rejected(self):
        frame = _trigger_frame()
        backward_value = frame.index[-3]  # earlier than existing last row
        extra = [(backward_value, True, 123.0)]
        prep = _prepare(_trigger_frame(extra_rows=extra), _h4_frame())
        assert prep.reason == "TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME"

    def test_duplicate_h4_times_rejected(self):
        dup_value = _h4_frame().index[-2]
        extra = [(dup_value, True, 123.0)]
        prep = _prepare(_trigger_frame(), _h4_frame(extra_rows=extra))
        assert prep.reason == "H4_DUPLICATE_OR_NON_INCREASING_TIME"

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), "oops"])
    def test_non_finite_trigger_close_rejected(self, bad):
        closes = [100.0 + i for i in range(80)]
        closes[70] = bad
        prep = _prepare(_trigger_frame(closes=closes), _h4_frame())
        assert prep.reason == "TRIGGER_NON_FINITE_DATA"

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), None])
    def test_non_finite_h4_close_rejected(self, bad):
        closes = [100.0 + i for i in range(70)]
        closes[68] = bad
        prep = _prepare(_trigger_frame(), _h4_frame(closes=closes))
        assert prep.reason == "H4_NON_FINITE_DATA"


class TestContiguousSuffixRules:
    def _gapped_trigger(self, rows_after_gap: int):
        """Trigger frame whose most recent cadence gap leaves exactly
        ``rows_after_gap`` contiguous rows ending at ``TRIGGER_CLOSE``.

        Two candles are skipped at the junction so the head/tail boundary is
        a genuine 3-interval gap while every row stays strictly increasing.
        """
        total = 80
        tail_times = [
            TRIGGER_CLOSE - TRIGGER_DURATION * k
            for k in range(rows_after_gap - 1, -1, -1)
        ]
        head_count = total - rows_after_gap - 2  # skip 2 candles -> 3x gap
        head_times = _utc_close_times(
            TRIGGER_CLOSE - TRIGGER_DURATION * (rows_after_gap + 2),
            head_count,
            TRIGGER_DURATION,
        )
        return _frame(head_times + tail_times, step=TRIGGER_DURATION)

    def test_old_gap_allowed_when_suffix_long_enough(self):
        frame = self._gapped_trigger(rows_after_gap=70)
        prep = _prepare(frame, _h4_frame())
        assert prep.reason == "READY"
        # Indicators computed over ONLY the 70-row suffix, not the prefix.
        closes = [float(v) for v in frame["close"]][-70:]
        expected = _bundle_of(closes)
        current = prep.input.current_trigger
        assert (current.rsi21, current.rsi_ema9, current.rsi_wma45) == pytest.approx(
            expected
        )

    def test_recent_gap_leaving_short_suffix_not_ready(self):
        prep = _prepare(self._gapped_trigger(rows_after_gap=40), _h4_frame())
        assert prep.reason == "TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY"

    def test_widening_suffix_changes_result_deterministically(self):
        # V-shaped closes: recursive seeds depend on the window start, so
        # widening the contiguous suffix must change the bundle values.
        def v_closes(count: int) -> list[float]:
            return [
                200.0 - i if i < count // 2 else 100.0 + (i - count // 2)
                for i in range(count)
            ]

        narrow = _trigger_frame(count=67, closes=v_closes(67))
        wide = _trigger_frame(count=80, closes=v_closes(80))
        narrow_prep = _prepare(narrow, _h4_frame())
        wide_prep = _prepare(wide, _h4_frame())

        for frame, prep in ((narrow, narrow_prep), (wide, wide_prep)):
            closes = [float(v) for v in frame["close"]]
            expected = _bundle_of(closes)
            current = prep.input.current_trigger
            assert (
                current.rsi21,
                current.rsi_ema9,
                current.rsi_wma45,
            ) == pytest.approx(expected)

        # The wider contiguous window genuinely re-seeds recursion — proving
        # the adapter computes over the entire suffix, never a fixed tail.
        assert wide_prep.input.current_trigger != narrow_prep.input.current_trigger

    def test_primitive_passthrough_matches_core_outputs_directly(self):
        frame = _trigger_frame()
        prep = _prepare(frame, _h4_frame())
        closes_series = pd.Series(
            [float(v) for v in frame["close"]], dtype="float64"
        )
        rsi21 = rsi_wilder(closes_series, 21)
        ema9 = ema(rsi21, 9)
        wma45 = wma(rsi21, 45)
        current = prep.input.current_trigger
        assert current.rsi21 == pytest.approx(float(rsi21.iloc[-1]))
        assert current.rsi_ema9 == pytest.approx(float(ema9.iloc[-1]))
        assert current.rsi_wma45 == pytest.approx(float(wma45.iloc[-1]))
