"""Tests for StrategyWorker failure policy: per-symbol retry counter and
hybrid-hard-death when SIGNAL_MAX_CONSECUTIVE_FAILURES is reached."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd

from app.core.analysis_result import AnalysisResult
from app.core.config import RiskConfig
from app.core.events import Candle
from app.core.snapshots import ContextSnapshot
from app.data.multiplexer import TimeframeMultiplexer
from app.signal.strategy_config import StrategyInstanceConfig
from app.signal.strategy_worker import StrategyWorker
from app.signal.virtual_position import VirtualPositionStore

STRATEGY_TOPIC = 42
DEBUG_TOPIC = 99


def _mk_candle():
    return Candle(
        symbol="BTC",
        timestamp=datetime(2024, 1, 1),
        open=Decimal("62000"),
        high=Decimal("62500"),
        low=Decimal("61500"),
        close=Decimal("62000"),
        volume=Decimal("1"),
        closed=True,
        timeframe="15m",
    )


def _mk_worker(*, max_failures=3, strategy=None):
    strategy = strategy or MagicMock()
    mux = MagicMock(spec=TimeframeMultiplexer)
    mux.get_dataframe.return_value = pd.DataFrame({"close": [1]})
    cfg = StrategyInstanceConfig(
        name="rsi_no_retest",
        telegram_topic_id=STRATEGY_TOPIC,
        symbols=("BTC/USDT", "ETH/USDT"),
        timeframe="15m",
        risk=RiskConfig(),
    )
    notifier = MagicMock()
    worker = StrategyWorker(
        instance_cfg=cfg,
        strategy=strategy,
        multiplexer=mux,
        vp_store=VirtualPositionStore(),
        notifier=notifier,
        debug_topic_id=DEBUG_TOPIC,
        max_failures=max_failures,
    )
    return worker, strategy, notifier


class TestRetryCounter:
    def test_single_failure_does_not_kill(self):
        strategy = MagicMock()
        strategy.analyze.side_effect = RuntimeError("boom")
        worker, _, _ = _mk_worker(strategy=strategy, max_failures=3)
        died = worker._process("BTC/USDT", "15m", _mk_candle())
        assert died is False
        assert worker._failure_counts["BTC/USDT"] == 1

    def test_success_resets_counter(self):
        strategy = MagicMock()
        strategy.analyze.side_effect = [
            RuntimeError("first"),
            AnalysisResult(actions=[], new_context=ContextSnapshot(state="SCANNING")),
            RuntimeError("third"),
        ]
        worker, _, _ = _mk_worker(strategy=strategy, max_failures=3)
        worker._process("BTC/USDT", "15m", _mk_candle())
        assert worker._failure_counts["BTC/USDT"] == 1
        worker._process("BTC/USDT", "15m", _mk_candle())  # success
        assert worker._failure_counts["BTC/USDT"] == 0
        worker._process("BTC/USDT", "15m", _mk_candle())
        assert worker._failure_counts["BTC/USDT"] == 1

    def test_failures_tracked_per_symbol(self):
        strategy = MagicMock()
        strategy.analyze.side_effect = RuntimeError("boom")
        worker, _, _ = _mk_worker(strategy=strategy, max_failures=3)
        worker._process("BTC/USDT", "15m", _mk_candle())
        worker._process("ETH/USDT", "15m", _mk_candle())
        assert worker._failure_counts["BTC/USDT"] == 1
        assert worker._failure_counts["ETH/USDT"] == 1
        # Exceeding the counter on BTC shouldn't affect ETH
        worker._process("BTC/USDT", "15m", _mk_candle())
        worker._process("BTC/USDT", "15m", _mk_candle())
        assert worker._failure_counts["BTC/USDT"] == 3
        assert worker._failure_counts["ETH/USDT"] == 1


class TestThreadDeath:
    def test_reaching_max_failures_signals_thread_death(self):
        strategy = MagicMock()
        strategy.analyze.side_effect = RuntimeError("boom")
        worker, _, notifier = _mk_worker(strategy=strategy, max_failures=3)

        worker._process("BTC/USDT", "15m", _mk_candle())
        worker._process("BTC/USDT", "15m", _mk_candle())
        died = worker._process("BTC/USDT", "15m", _mk_candle())

        assert died is True
        # Debug-topic message sent with "disabled" phrasing on death
        dead_calls = [
            c for c in notifier.send_message.call_args_list
            if c.kwargs["topic_id"] == DEBUG_TOPIC and "disabled" in c.args[0]
        ]
        assert len(dead_calls) == 1

    def test_run_exits_on_thread_death(self):
        """Worker.run() returns when failure budget is exhausted."""
        strategy = MagicMock()
        strategy.analyze.side_effect = RuntimeError("boom")
        worker, _, _ = _mk_worker(strategy=strategy, max_failures=2)

        # Enqueue two failing candles, then a stop sentinel as a safety net.
        worker.enqueue("BTC/USDT", "15m", _mk_candle())
        worker.enqueue("BTC/USDT", "15m", _mk_candle())
        worker.enqueue("BTC/USDT", "15m", _mk_candle())  # never consumed

        import threading
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        t.join(timeout=5.0)
        assert not t.is_alive()

    def test_death_only_on_consecutive_failures(self):
        """A success between failures should reset the counter and prevent death."""
        strategy = MagicMock()
        strategy.analyze.side_effect = [
            RuntimeError("1"),
            RuntimeError("2"),
            AnalysisResult(actions=[], new_context=ContextSnapshot(state="SCANNING")),
            RuntimeError("3"),
            RuntimeError("4"),
        ]
        worker, _, _ = _mk_worker(strategy=strategy, max_failures=3)

        for _ in range(5):
            died = worker._process("BTC/USDT", "15m", _mk_candle())
            assert died is False
