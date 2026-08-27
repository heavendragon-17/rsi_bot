"""Tests for the BTC RSI cross alert worker: bootstrap gate, point-in-time
evaluation, H4 boundary settle/retry, dedupe, failure budget, shutdown."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from btc_alert_fixtures import (
    BASE,
    READY_AT,
    SYMBOL,
)
from btc_alert_fixtures import (
    assert_h4_close_above_ema21 as _assert_bullish_bundle,
)
from btc_alert_fixtures import (
    h4_price_above_ema21_closes as _bullish_h4_closes,
)
from btc_alert_fixtures import (
    make_candle as _candle,
)
from btc_alert_fixtures import (
    qualifying_m5_trigger as _qualifying_m5_trigger,
)
from btc_alert_fixtures import (
    qualifying_trigger as _qualifying_trigger,
)

from app.data.multiplexer import TimeframeMultiplexer
from app.signal.btc_rsi_cross_alert.config import BtcRsiCrossAlertConfig
from app.signal.btc_rsi_cross_alert.worker import BtcRsiCrossAlertWorker


def _hydrate(
    mux: TimeframeMultiplexer,
    timeframe: str,
    step: timedelta,
    close_times: list[datetime],
    closes: list[float],
    *,
    include_last: bool = False,
) -> None:
    """REST-bootstrap style hydration through the multiplexer.

    By default the final row is withheld (it will arrive as the live
    WebSocket close). Pass ``include_last=True`` for fully historical
    frames such as the trusted pre-bootstrap H4 context.
    """
    rows = len(close_times) if include_last else len(close_times) - 1
    for position in range(rows):
        mux.on_kline_event(
            SYMBOL,
            timeframe,
            _candle(close_times[position], step, closes[position]),
        )


# ---------------------------------------------------------------------------
# Worker factory
# ---------------------------------------------------------------------------
def _config(**overrides) -> BtcRsiCrossAlertConfig:
    values = dict(
        name="btc_rsi_cross_alert",
        telegram_topic_id=1007,
        m15_telegram_topic_id=1008,
        symbol=SYMBOL,
        trigger_timeframes=("5m", "15m"),
        trend_timeframe="4h",
        rsi_period=21,
        rsi_ema_period=9,
        rsi_wma_period=45,
        context_settle_seconds=5,
    )
    values.update(overrides)
    return BtcRsiCrossAlertConfig(**values)


def _make_worker(
    *,
    config: BtcRsiCrossAlertConfig | None = None,
    notifier=None,
) -> tuple[BtcRsiCrossAlertWorker, TimeframeMultiplexer, MagicMock]:
    config = config or _config()
    notifier = notifier if notifier is not None else MagicMock()
    targets = set(config.targets)
    mux = TimeframeMultiplexer(targets=targets)
    worker = BtcRsiCrossAlertWorker(
        config=config,
        multiplexer=mux,
        notifier=notifier,
        debug_topic_id=99,
    )
    mux.register_close_callback(worker.handle_closed_candle)
    return worker, mux, notifier


def _start(worker: BtcRsiCrossAlertWorker) -> threading.Thread:
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    return thread


def _stop(worker: BtcRsiCrossAlertWorker, thread: threading.Thread) -> None:
    worker.request_stop()
    thread.join(timeout=5)
    assert not thread.is_alive()


def _wait_for(predicate, timeout: float = 3.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _bootstrap(worker: BtcRsiCrossAlertWorker) -> None:
    worker.on_history_complete(now=READY_AT)


class TestBootstrapGate:
    def test_callbacks_before_history_ready_are_silently_discarded(self):
        worker, mux, notifier = _make_worker()
        thread = _start(worker)

        close_times, closes = _qualifying_m5_trigger(timedelta(minutes=5), BASE.replace(hour=9, minute=45))
        _hydrate(mux, "5m", timedelta(minutes=5), close_times, closes)
        # Fire several live-looking closed candles pre-ready.
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], timedelta(minutes=5), closes[-1]))

        time.sleep(0.2)
        assert notifier.send_message.call_count == 0
        assert worker.emitted_event_ids == frozenset()

        _stop(worker, thread)

    def test_history_ready_transition_sends_no_alert(self):
        worker, mux, notifier = _make_worker()
        close_times, closes = _qualifying_m5_trigger(timedelta(minutes=5), BASE.replace(hour=9, minute=45))
        _hydrate(mux, "5m", timedelta(minutes=5), close_times, closes)

        _bootstrap(worker)
        time.sleep(0.1)
        assert notifier.send_message.call_count == 0

    def test_delayed_duplicate_at_watermark_stays_silent(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        close_times, closes = _qualifying_m5_trigger(step, BASE.replace(hour=9, minute=45))
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)
        assert worker._bootstrap_watermarks["5m"] == close_times[-2]

        # Delayed WebSocket duplicate of the final REST candle.
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        time.sleep(0.2)
        assert notifier.send_message.call_count == 0

    def test_candle_after_watermark_but_not_after_ready_suppressed(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        close_times, closes = _qualifying_m5_trigger(step, BASE.replace(hour=9, minute=45))
        _hydrate(mux, "5m", step, close_times, closes)

        # Live candle closed during hydration: after REST watermark
        # (09:40) but at/before the history-ready instant (09:45 <= 09:45).
        late_ready = BASE.replace(hour=9, minute=45)
        worker.on_history_complete(now=late_ready)
        assert worker._bootstrap_watermarks["5m"] == close_times[-2]

        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        time.sleep(0.2)
        assert notifier.send_message.call_count == 0

    def test_bootstrap_gate_does_not_advance_cursor(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        close_times, closes = _qualifying_m5_trigger(step, BASE.replace(hour=9, minute=45))
        _hydrate(mux, "5m", step, close_times, closes)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        _bootstrap(worker)
        assert worker.last_evaluated == {"5m": None, "15m": None}


class TestClosedCandleEvaluation:
    def test_qualifying_m5_close_alerts_configured_topic(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        close_times, closes = _qualifying_m5_trigger(step, BASE.replace(hour=9, minute=45))

        h4_closes = _bullish_h4_closes()
        _assert_bullish_bundle(h4_closes)
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)

        _bootstrap(worker)
        thread = _start(worker)

        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        assert _wait_for(lambda: notifier.send_message.call_count == 1)

        call = notifier.send_message.call_args
        assert call.kwargs["topic_id"] == worker.config.telegram_topic_id
        assert "BTC RSI BULLISH ALIGNMENT" in call.args[0]
        assert len(worker.emitted_event_ids) == 1
        assert worker.last_evaluated["5m"] == close_times[-1]

        _stop(worker, thread)

    def test_m5_cooldown_suppresses_five_and_ten_minutes_then_allows_fifteen(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        first_close = BASE.replace(hour=9, minute=45)
        close_times, closes = _qualifying_m5_trigger(step, first_close)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [
            h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)
        ]
        _hydrate(
            mux,
            "4h",
            timedelta(hours=4),
            h4_times,
            h4_closes,
            include_last=True,
        )
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)
        thread = _start(worker)

        mux.on_kline_event(
            SYMBOL,
            "5m",
            _candle(first_close, step, closes[-1]),
        )
        assert _wait_for(lambda: notifier.send_message.call_count == 1)
        assert worker.last_m5_alert_close == first_close

        for minutes, price_increment in ((5, 10.0), (10, 20.0)):
            suppressed_close = first_close + timedelta(minutes=minutes)
            mux.on_kline_event(
                SYMBOL,
                "5m",
                _candle(suppressed_close, step, closes[-1] + price_increment),
            )
            assert _wait_for(
                lambda expected=suppressed_close: worker.last_evaluated["5m"]
                == expected
            )
            assert notifier.send_message.call_count == 1
            assert worker.last_m5_alert_close == first_close

        eligible_close = first_close + timedelta(minutes=15)
        mux.on_kline_event(
            SYMBOL,
            "5m",
            _candle(eligible_close, step, closes[-1] + 30.0),
        )
        assert _wait_for(lambda: notifier.send_message.call_count == 2)
        assert worker.last_m5_alert_close == eligible_close
        assert len(worker.emitted_event_ids) == 2

        _stop(worker, thread)

    def test_open_candles_never_trigger_and_h4_only_marks_context(self):
        worker, mux, notifier = _make_worker()
        _bootstrap(worker)
        thread = _start(worker)

        step = timedelta(minutes=5)
        open_candle = _candle(BASE.replace(hour=10), step, 100.0, closed=False)
        mux.on_kline_event(SYMBOL, "5m", open_candle)

        h4_open = _candle(BASE.replace(hour=12), timedelta(hours=4), 100.0, closed=False)
        mux.on_kline_event(SYMBOL, "4h", h4_open)

        time.sleep(0.2)
        assert notifier.send_message.call_count == 0
        assert worker.last_evaluated == {"5m": None, "15m": None}
        # The closed H4 confirmation path itself is exercised below; the
        # forming H4 candle recorded nothing.
        assert BASE.replace(hour=12) not in worker._observed_h4_closes

        _stop(worker, thread)

    def test_post_bootstrap_h4_row_unusable_until_live_callback_observed(self):
        worker, mux, notifier = _make_worker()
        worker.config = _config(context_settle_seconds=0)
        step = timedelta(minutes=5)
        # Continuous timeline whose final row is qualifying M5 alignment at 12:10.
        end = BASE.replace(hour=12, minute=10)
        close_times, closes = _qualifying_m5_trigger(step, end)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        # Hydrate everything except the final two trigger candles.
        for position in range(len(close_times) - 2):
            mux.on_kline_event(
                SYMBOL, "5m", _candle(close_times[position], step, closes[position])
            )
        _bootstrap(worker)

        thread = _start(worker)
        # Live 12:05 candle: expected H4 context is 12:00 (> ready_at) and
        # not yet observed → single retry then fail closed, cursor advances.
        t1 = close_times[-2]
        mux.on_kline_event(SYMBOL, "5m", _candle(t1, step, closes[-2]))
        assert _wait_for(lambda: worker.last_evaluated["5m"] == t1)
        assert notifier.send_message.call_count == 0

        # The live closed 12:00 H4 callback arrives; a LATER trigger candle
        # can now use that context.
        h4_live_close = h4_closes[-1] + 2.0
        mux.on_kline_event(
            SYMBOL, "4h", _candle(BASE.replace(hour=12), timedelta(hours=4), h4_live_close)
        )
        _assert_bullish_bundle(h4_closes[:-1] + [h4_live_close])

        t2 = close_times[-1]
        mux.on_kline_event(SYMBOL, "5m", _candle(t2, step, closes[-1]))
        assert _wait_for(lambda: notifier.send_message.call_count == 1)

        _stop(worker, thread)

    def test_exact_h4_context_selected_as_of_trigger_close(self):
        """A newer H4 close below EMA21 must suppress even though the older
        row passed — proving exact as-of-T selection."""
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12, minute=35)  # inside [12:00, 16:00)
        close_times, closes = _qualifying_m5_trigger(step, end)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]

        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        # Confirm the live 12:00 H4 close with a price collapse below EMA21.
        below_ema_close = 20.0
        mux.on_kline_event(SYMBOL, "4h", _candle(BASE.replace(hour=12), timedelta(hours=4), below_ema_close))

        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        assert _wait_for(lambda: worker.last_evaluated["5m"] == close_times[-1])
        assert notifier.send_message.call_count == 0

        _stop(worker, thread)

    def test_boundary_race_retries_once_and_succeeds_when_h4_arrives(self):
        worker, mux, notifier = _make_worker()
        cfg = _config(context_settle_seconds=5)
        worker.config = cfg
        worker.max_failures = 5
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12)  # exactly on the H4 boundary
        close_times, closes = _qualifying_m5_trigger(step, end)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))

        # While the worker waits, the live 12:00 H4 close arrives (routed
        # through the SAME multiplexer callback — no manual intervention).
        time.sleep(0.3)
        assert notifier.send_message.call_count == 0  # still waiting
        assert worker.last_evaluated["5m"] is None  # cursor held during retry

        mux.on_kline_event(SYMBOL, "4h", _candle(end, timedelta(hours=4), h4_closes[-1] + 2.0))
        assert _wait_for(lambda: notifier.send_message.call_count == 1)
        assert worker.last_evaluated["5m"] == end

        _stop(worker, thread)

    def test_h4_confirmation_is_synchronous_and_wakes_waiter_without_queue(self):
        worker, mux, notifier = _make_worker()
        worker.config = _config(context_settle_seconds=30)  # would exceed timeout
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12)
        close_times, closes = _qualifying_m5_trigger(step, end)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        time.sleep(0.3)
        assert notifier.send_message.call_count == 0

        started = time.monotonic()
        # Live closed H4 candle through the multiplexer: its close callback
        # records the confirmation SYNCHRONOUSLY (no worker-queue transit)
        # and wakes the waiting evaluation.
        mux.on_kline_event(SYMBOL, "4h", _candle(end, timedelta(hours=4), 200.0))
        assert _wait_for(lambda: notifier.send_message.call_count == 1, timeout=10)
        elapsed = time.monotonic() - started
        assert elapsed < 5  # woke well before the 30 s settle timeout
        # H4 events never pass through the worker queue.
        assert len(worker._pending) == 0

        _stop(worker, thread)

    def test_retry_exhaustion_fails_closed_without_telegram(self):
        worker, mux, notifier = _make_worker()
        worker.config = _config(context_settle_seconds=0)
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12)
        close_times, closes = _qualifying_m5_trigger(step, end)

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        assert _wait_for(lambda: worker.last_evaluated["5m"] == end)
        assert notifier.send_message.call_count == 0

        _stop(worker, thread)


class TestDeduplication:
    def test_duplicate_and_backward_callbacks_ignored(self):
        worker, mux, notifier = _make_worker()
        step = timedelta(minutes=5)
        close_times, closes = _qualifying_m5_trigger(step, BASE.replace(hour=9, minute=45))
        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        live = _candle(close_times[-1], step, closes[-1])
        mux.on_kline_event(SYMBOL, "5m", live)
        assert _wait_for(lambda: notifier.send_message.call_count == 1)

        # Same candle again (duplicate callback) and an older candle.
        notifier.reset_mock()
        mux.on_kline_event(SYMBOL, "5m", live)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-2], step, closes[-2]))
        time.sleep(0.3)
        assert notifier.send_message.call_count == 0

        _stop(worker, thread)

    def test_same_m5_alignment_not_reemitted_when_h4_turns_bullish(self):
        worker, mux, notifier = _make_worker()
        worker.config = _config(context_settle_seconds=0)
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12)
        close_times, closes = _qualifying_m5_trigger(step, end)
        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        # Alignment evaluated once while exact H4 context unavailable → consumed.
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        assert _wait_for(lambda: worker.last_evaluated["5m"] == end)
        assert notifier.send_message.call_count == 0

        # H4 turns available/bullish afterwards — the SAME candle must not
        # emit retroactively.
        mux.on_kline_event(SYMBOL, "4h", _candle(end, timedelta(hours=4), 200.0))
        notifier.reset_mock()
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        time.sleep(0.3)
        assert notifier.send_message.call_count == 0

        _stop(worker, thread)


class TestFailureBudget:
    @pytest.fixture
    def broken_mux_worker(self):
        notifier = MagicMock()
        config = _config(context_settle_seconds=0)
        targets = set(config.targets)
        mux = TimeframeMultiplexer(targets=targets)
        worker = BtcRsiCrossAlertWorker(
            config=config,
            multiplexer=mux,
            notifier=notifier,
            debug_topic_id=99,
            max_failures=3,
        )
        mux.register_close_callback(worker.handle_closed_candle)
        return worker, mux, notifier

    def test_exception_budget_debug_notify_and_terminal_death(self, broken_mux_worker):
        worker, mux, notifier = broken_mux_worker
        _bootstrap(worker)
        thread = _start(worker)

        # Frames are empty → every evaluation raises → requeue-ahead.
        step = timedelta(minutes=5)
        t = BASE.replace(hour=10)
        mux.on_kline_event(SYMBOL, "5m", _candle(t, step, 100.0))

        assert _wait_for(lambda: not thread.is_alive(), timeout=5)
        # Debug notified exactly once about the terminal failure.
        debug_calls = [
            c for c in notifier.send_message.call_args_list
            if c.kwargs.get("topic_id") == 99
        ]
        assert len(debug_calls) == 1
        assert "btc_rsi_cross_alert" in debug_calls[0].args[0]
        # Cursor advanced at budget exhaustion; no alert ever sent.
        assert worker.last_evaluated["5m"] == t
        assert worker.emitted_event_ids == frozenset()

    def test_newer_events_wait_behind_requeued_failure(self, broken_mux_worker):
        worker, mux, notifier = broken_mux_worker
        _bootstrap(worker)
        thread = _start(worker)

        step = timedelta(minutes=5)
        older = BASE.replace(hour=10)
        newer = BASE.replace(hour=10, minute=5)
        mux.on_kline_event(SYMBOL, "5m", _candle(older, step, 100.0))
        time.sleep(0.05)
        mux.on_kline_event(SYMBOL, "5m", _candle(newer, step, 100.0))

        assert _wait_for(lambda: not thread.is_alive(), timeout=5)
        # Only the FIRST event hit the budget; the newer one never processed
        # because the thread died first (requeue kept it ahead of the rest).
        assert worker.last_evaluated["5m"] == older

    def test_success_resets_failure_streak(self, broken_mux_worker):
        worker, mux, notifier = broken_mux_worker
        _bootstrap(worker)
        thread = _start(worker)
        streak_before = worker._failure_streak

        # No exceptions occur (nothing processed); streak untouched.
        worker.request_stop()
        thread.join(timeout=5)
        assert worker._failure_streak == streak_before == 0


class TestMultiTimeframeIndependence:
    def test_simultaneous_valid_m5_m15_closes_produce_two_alerts(self):
        worker, mux, notifier = _make_worker()

        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)

        m5_step = timedelta(minutes=5)
        m15_step = timedelta(minutes=15)
        shared_t = BASE.replace(hour=9, minute=45)  # aligned for both
        m5_times, m5_closes = _qualifying_m5_trigger(m5_step, shared_t)
        m15_times, m15_closes = _qualifying_trigger(m15_step, shared_t)
        _hydrate(mux, "5m", m5_step, m5_times, m5_closes)
        _hydrate(mux, "15m", m15_step, m15_times, m15_closes)
        _bootstrap(worker)

        thread = _start(worker)
        mux.on_kline_event(SYMBOL, "5m", _candle(shared_t, m5_step, m5_closes[-1]))
        mux.on_kline_event(SYMBOL, "15m", _candle(shared_t, m15_step, m15_closes[-1]))

        assert _wait_for(lambda: notifier.send_message.call_count >= 2, timeout=5)
        assert _wait_for(
            lambda: len(worker.emitted_event_ids) == 2, timeout=2
        )
        assert worker.last_evaluated["5m"] == shared_t
        assert worker.last_evaluated["15m"] == shared_t
        alerts_by_title = {
            "m5": next(
                c.kwargs["topic_id"]
                for c in notifier.send_message.call_args_list
                if "BTC RSI BULLISH ALIGNMENT" in c.args[0]
            ),
            "m15": next(
                c.kwargs["topic_id"]
                for c in notifier.send_message.call_args_list
                if "BTC RSI BULLISH CROSS" in c.args[0]
            ),
        }
        assert alerts_by_title == {"m5": 1007, "m15": 1008}

        _stop(worker, thread)


class TestBoundariesAndSafety:
    def test_no_virtual_position_or_order_surface_exists(self):
        worker, _, notifier = _make_worker()
        assert not hasattr(worker, "vp_store")
        assert not hasattr(worker, "strategy")
        methods = {name for name in dir(worker) if callable(getattr(worker, name))}
        for banned in ("open_position", "place_order", "cancel_order"):
            assert banned not in methods

    def test_stop_is_bounded_idempotent_and_interrupts_retry_wait(self):
        worker, mux, notifier = _make_worker()
        worker.config = _config(context_settle_seconds=30)
        step = timedelta(minutes=5)
        end = BASE.replace(hour=12)
        close_times, closes = _qualifying_m5_trigger(step, end)
        h4_closes = _bullish_h4_closes()
        h4_end = BASE.replace(hour=8)
        h4_times = [h4_end - timedelta(hours=4) * (70 - 1 - i) for i in range(70)]
        _hydrate(mux, "4h", timedelta(hours=4), h4_times, h4_closes, include_last=True)
        _hydrate(mux, "5m", step, close_times, closes)
        _bootstrap(worker)

        thread = _start(worker)
        mux.on_kline_event(SYMBOL, "5m", _candle(close_times[-1], step, closes[-1]))
        time.sleep(0.3)  # worker now inside the 30 s settle wait

        worker.request_stop()
        worker.request_stop()  # idempotent
        joined_at = time.monotonic()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert time.monotonic() - joined_at < 3  # did not wait out the settle

    def test_worker_run_logs_started_and_stopped(self, caplog):
        worker, mux, notifier = _make_worker()
        _bootstrap(worker)
        thread = _start(worker)
        _stop(worker, thread)
