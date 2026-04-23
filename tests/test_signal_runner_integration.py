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
                low=Decimal("61900"),
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
