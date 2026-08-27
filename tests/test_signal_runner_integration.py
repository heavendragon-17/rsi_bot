"""End-to-end smoke for the signal-bot pipeline (slice 8).

Uses a real ``SignalRunner`` with:
  * real ``TimeframeMultiplexer``
  * real ``VirtualPositionStore``
  * real ``StrategyWorker`` threads (spawned via ``runner.start()``)
  * a stub strategy class registered into ``STRATEGY_MAP`` for the duration
    of the test (avoids the indicator warmup requirements of the real RSI
    strategies)
  * ``MagicMock`` ``BinanceStreamManager`` — no WebSocket, no HTTP
  * ``MagicMock`` ``NotificationService`` — captures every outbound message

Flow:
    1. Build + start the runner (mocked stream, real worker thread).
    2. Fire a synthetic closed candle through the multiplexer.
    3. Wait briefly for the worker to drain the queue.
    4. Assert: strategy received analyze() call, VP was opened, entry
       message went to the strategy's topic.
    5. Fire a second candle that trips the VP's SL; assert SL-hit message.
    6. Shut down; assert clean stop.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.core.actions import DoNothing, OpenPosition
from app.core.analysis_result import AnalysisResult
from app.core.events import Candle
from app.core.snapshots import ContextSnapshot
from app.signal.runner import SignalRunner
from app.trading.strategy.loader import STRATEGY_MAP


class _StubStrategy:
    """Minimal strategy wired to return scripted AnalysisResults.

    Instance-level ``scripted`` attribute is a list; each analyze() call
    pops the first entry. Instances are keyed on strategy_name-level
    config so the runner uses the right one.
    """

    scripted: list[AnalysisResult] = []

    def __init__(self, config: dict):
        self.config = config

    def analyze(self, symbol, df, position=None, context=None):
        if _StubStrategy.scripted:
            return _StubStrategy.scripted.pop(0)
        return AnalysisResult(
            actions=[DoNothing()],
            new_context=ContextSnapshot(state="SCANNING"),
        )


@pytest.fixture
def stub_strategy():
    """Register ``_StubStrategy`` under ``rsi_no_retest`` for the test."""
    original = STRATEGY_MAP["rsi_no_retest"]
    STRATEGY_MAP["rsi_no_retest"] = _StubStrategy
    _StubStrategy.scripted = []
    try:
        yield _StubStrategy
    finally:
        STRATEGY_MAP["rsi_no_retest"] = original
        _StubStrategy.scripted = []


def _raw_config():
    return {
        "bot": {"mode": "signal"},
        "telegram": {"group_id": -100, "debug_topic_id": 99},
        "timeframe": "15m",
        "symbols": ["BTC/USDT"],
        "risk": {
            "risk_per_trade_pct": 0.002,
            "max_position_size_pct": 0.99,
            "leverage": 10,
            "tp1_close_pct": 1,
            "tp2_close_pct": 0,
            "min_sl_distance_pct": 0.003,
        },
        "strategies": [
            {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
        ],
    }


def _closed_candle(ts: datetime, close: Decimal, high: Decimal, low: Decimal) -> Candle:
    return Candle(
        symbol="BTC",
        timestamp=ts,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
        closed=True,
        timeframe="15m",
    )


def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestEndToEndSmoke:
    def test_open_signal_flows_through_pipeline(self, stub_strategy):
        notifier = MagicMock()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner = SignalRunner(
                _raw_config(), notifier, install_signal_handlers=False
            )

            entry_ts = datetime(2024, 1, 1, 0, 0, 0)
            stub_strategy.scripted = [
                AnalysisResult(
                    actions=[
                        OpenPosition(
                            symbol="BTC/USDT",
                            side="BUY",
                            entry_price=Decimal("62000"),
                            sl_price=Decimal("61500"),
                            soft_sl_price=None,
                            tp_prices=[Decimal("63000")],
                            tp_allocations={"TP1": 1.0},
                            lock_profit_price=None,
                            signal_class=1,
                            reason="smoke open",
                        )
                    ],
                    new_context=ContextSnapshot(state="CONFIRMING"),
                ),
            ]

            runner.start()
            assert runner._multiplexer is not None

            # Fire the candle the strategy will open on.
            candle = _closed_candle(
                ts=entry_ts,
                close=Decimal("62000"),
                high=Decimal("62100"),
                low=Decimal("61900"),
            )
            runner._multiplexer.on_kline_event("BTC/USDT", "15m", candle)

            # Worker runs on a separate thread — poll until the VP appears.
            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is not None
            ), "VP was never opened"

            # Entry message routed to the strategy's topic.
            entry_calls = [
                c for c in notifier.send_message.call_args_list
                if "LONG BTC/USDT" in c.args[0]
            ]
            assert entry_calls, "no entry message enqueued"
            assert entry_calls[0].kwargs["topic_id"] == 42

            # Now fire a candle that closes below SL → mechanical SL exit.
            notifier.reset_mock()
            sl_candle = _closed_candle(
                ts=entry_ts + timedelta(minutes=15),
                close=Decimal("61000"),
                high=Decimal("61600"),
                low=Decimal("60800"),
            )
            runner._multiplexer.on_kline_event("BTC/USDT", "15m", sl_candle)

            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is None
            ), "VP was never closed on SL"

            sl_calls = [
                c for c in notifier.send_message.call_args_list
                if "EXIT advice" in c.args[0]
            ]
            assert sl_calls, "no SL-exit message enqueued"
            assert sl_calls[0].kwargs["topic_id"] == 42

            runner.stop()
            for thread in runner._threads:
                assert not thread.is_alive()

    def test_untargeted_candle_is_dropped_by_multiplexer(self, stub_strategy):
        """Defense-in-depth: sending an event for a non-target pair must
        not reach the strategy worker."""
        notifier = MagicMock()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner = SignalRunner(
                _raw_config(), notifier, install_signal_handlers=False
            )
            runner.start()

            # Preload enough history for the strategy to analyze, but only
            # on an untargeted pair — should be dropped silently.
            base_ts = datetime(2024, 1, 1)
            candle = Candle(
                symbol="DOGE",
                timestamp=base_ts,
                open=Decimal("0.1"),
                high=Decimal("0.11"),
                low=Decimal("0.09"),
                close=Decimal("0.1"),
                volume=Decimal("100"),
                closed=True,
                timeframe="15m",
            )
            runner._multiplexer.on_kline_event("DOGE/USDT", "15m", candle)

            # Give worker thread a chance to react (it shouldn't).
            time.sleep(0.2)

            # No VP was opened, no messages sent.
            assert runner._vp_store.get_for_symbol(
                "rsi_no_retest", "DOGE/USDT"
            ) is None
            assert notifier.send_message.call_count == 0

            runner.stop()

    def test_shutdown_broadcast_after_vp_open(self, stub_strategy):
        """When shutdown fires with an open VP, the shutdown broadcast
        message should include that VP's summary line."""
        notifier = MagicMock()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner = SignalRunner(
                _raw_config(), notifier, install_signal_handlers=False
            )
            stub_strategy.scripted = [
                AnalysisResult(
                    actions=[
                        OpenPosition(
                            symbol="BTC/USDT",
                            side="BUY",
                            entry_price=Decimal("62000"),
                            sl_price=Decimal("61500"),
                            soft_sl_price=None,
                            tp_prices=[Decimal("63000")],
                            tp_allocations={"TP1": 1.0},
                            lock_profit_price=None,
                            signal_class=1,
                            reason="open",
                        )
                    ],
                    new_context=ContextSnapshot(state="CONFIRMING"),
                ),
            ]
            runner.start()

            candle = _closed_candle(
                ts=datetime(2024, 1, 1),
                close=Decimal("62000"),
                high=Decimal("62100"),
                low=Decimal("60800"),
            )
            runner._multiplexer.on_kline_event("BTC/USDT", "15m", candle)
            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is not None
            )

            notifier.reset_mock()
            runner.stop()

            broadcast = [
                c for c in notifier.send_message.call_args_list
                if "Signal bot shutting down" in c.args[0]
            ]
            assert len(broadcast) == 1
            body = broadcast[0].args[0]
            assert "BTC/USDT" in body
            assert "RSIN#001" in body
            assert broadcast[0].kwargs["topic_id"] == 42


def _btc_raw_config() -> dict:
    raw = _raw_config()
    raw["strategies"].append(
        {
            "name": "btc_rsi_cross_alert",
            "active": True,
            "telegram_topic_id": 1007,
            "symbol": "BTC/USDT",
            "trigger_timeframes": ["5m", "15m"],
            "trend_timeframe": "4h",
            "rsi_period": 21,
            "rsi_ema_period": 9,
            "rsi_wma_period": 45,
            "context_settle_seconds": 5,
        }
    )
    return raw


class TestBtcAlertEndToEnd:
    def test_qualifying_m5_close_reaches_btc_topic_without_virtual_position(self):
        from btc_alert_fixtures import (
            BASE,
            READY_AT,
            h4_close_times,
            h4_price_above_ema21_closes,
            make_candle,
            qualifying_m5_trigger,
        )

        notifier = MagicMock()
        raw = _btc_raw_config()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner = SignalRunner(raw, notifier, install_signal_handlers=False)
            runner.start()

        mux = runner._multiplexer
        step = timedelta(minutes=5)

        # REST-style hydration: trusted H4 history through 08:00 UTC and the
        # trigger frame through one candle before the live cross.
        m5_times, m5_closes = qualifying_m5_trigger(
            step,
            BASE.replace(hour=9, minute=45),
        )
        for position in range(len(m5_times) - 1):
            mux.on_kline_event(
                "BTC/USDT",
                "5m",
                make_candle(m5_times[position], step, m5_closes[position]),
            )
        h4_times = h4_close_times(BASE.replace(hour=8))
        h4_closes = h4_price_above_ema21_closes()
        for position in range(len(h4_times)):
            mux.on_kline_event(
                "BTC/USDT",
                "4h",
                make_candle(h4_times[position], timedelta(hours=4), h4_closes[position]),
            )

        # The stream manager fires the captured hook exactly once after all
        # fetch attempts; here we simulate that wiring with a frozen clock
        # so the synthetic timeline stays consistent.
        from app.signal.btc_rsi_cross_alert import worker as btc_worker_module

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ARG003 — signature parity
                return READY_AT

        history_hook = Stream.call_args.kwargs["history_complete_callback"]
        with patch.object(btc_worker_module, "datetime", _FrozenDatetime):
            history_hook()

        # Live closed M5 candle carrying the qualifying bullish alignment.
        mux.on_kline_event(
            "BTC/USDT", "5m", make_candle(m5_times[-1], step, m5_closes[-1])
        )

        assert _wait_for(lambda: notifier.send_message.call_count >= 1)
        alert_calls = [
            c for c in notifier.send_message.call_args_list
            if "BTC RSI BULLISH ALIGNMENT" in c.args[0]
        ]
        assert len(alert_calls) == 1
        assert alert_calls[0].kwargs["topic_id"] == 1007

        # The BTC alert never creates a virtual position or order path.
        assert runner._vp_store.all_open_by_strategy() == {}
        assert runner._vp_store.get_for_symbol("btc_rsi_cross_alert", "BTC/USDT") is None

        worker = runner._alert_workers[0]
        assert len(worker.emitted_event_ids) == 1

        # A duplicate of the same candle cannot duplicate the alert.
        notifier.reset_mock()
        mux.on_kline_event(
            "BTC/USDT", "5m", make_candle(m5_times[-1], step, m5_closes[-1])
        )
        time.sleep(0.2)
        assert notifier.send_message.call_count == 0

        runner.stop()
        for thread in runner._threads + runner._alert_threads:
            assert not thread.is_alive()
