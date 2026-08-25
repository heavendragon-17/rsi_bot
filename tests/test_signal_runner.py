"""Tests for SignalRunner orchestrator (slice 7).

Stream manager and notification service are mocked out; we never open a WS
or spawn real threads in these unit tests. Worker threads ARE real but the
mocked multiplexer means they never receive events — only the lifecycle is
exercised.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.signal.runner import SignalRunner, _make_filtered_callback
from app.signal.strategy_config import StrategyInstanceConfig
from app.signal.virtual_position import VirtualPosition


def _base_raw_config(**overrides) -> dict:
    raw = {
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
    raw.update(overrides)
    return raw


def _mk_runner(raw=None, *, patch_stream=True):
    """Build a SignalRunner with BinanceStreamManager stubbed out."""
    raw = raw or _base_raw_config()
    notifier = MagicMock()
    if patch_stream:
        with patch("app.signal.runner.BinanceStreamManager") as MockStream:
            MockStream.return_value = MagicMock()
            runner = SignalRunner(raw, notifier, install_signal_handlers=False)
            return runner, notifier, MockStream
    runner = SignalRunner(raw, notifier, install_signal_handlers=False)
    return runner, notifier, None


class TestStart:
    def test_builds_workers_for_each_active_strategy(self):
        runner, notifier, mock_stream = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        assert len(runner._workers) == 1
        assert runner._workers[0].instance_cfg.name == "rsi_no_retest"
        assert len(runner._threads) == 1
        runner.stop()

    def test_start_is_idempotent(self):
        runner, _, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()
            worker_count = len(runner._workers)
            runner.start()
            assert len(runner._workers) == worker_count
        runner.stop()

    def test_no_active_strategies_does_not_start_stream(self):
        raw = _base_raw_config()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": False, "telegram_topic_id": 42},
        ]
        runner, _, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            runner.start()
            Stream.assert_not_called()
        assert runner._workers == []
        assert runner._stream is None

    def test_no_active_strategies_wait_returns_immediately(self):
        """Regression: after a no-op start(), wait() must not block."""
        import threading
        raw = _base_raw_config()
        raw["strategies"] = []
        runner, _, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager"):
            runner.start()
        t = threading.Thread(target=runner.wait, daemon=True)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive()

    def test_invalid_config_propagates(self):
        raw = _base_raw_config()
        raw["strategies"] = [
            {"name": "ghost_strategy", "active": True, "telegram_topic_id": 42},
        ]
        runner, _, _ = _mk_runner(raw)
        with pytest.raises(ValueError, match="unknown strategy"):
            runner.start()

    def test_non_int_debug_topic_raises_value_error(self):
        raw = _base_raw_config()
        raw["telegram"]["debug_topic_id"] = "not-an-int"
        runner, _, _ = _mk_runner(raw)
        with pytest.raises(ValueError, match="debug_topic_id must be an integer"):
            runner.start()

    def test_running_set_before_workers_spawned(self):
        """Regression: if SIGTERM arrives during ramp-up, stop() must see
        _running set so it can actually tear down."""
        raw = _base_raw_config()
        runner, _, _ = _mk_runner(raw)

        observed_running = []
        real_build = runner._build_workers

        def capture():
            observed_running.append(runner._running.is_set())
            return real_build()

        runner._build_workers = capture
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        assert observed_running == [True]
        runner.stop()


class TestShutdownBroadcast:
    def _seed_vp(self, runner, strategy_name, symbol):
        vp = VirtualPosition(
            signal_id="RSIN#001",
            strategy_name=strategy_name,
            symbol=symbol,
            side="LONG",
            entry_price=Decimal("62000"),
            sl_price=Decimal("61500"),
            tp_levels=(Decimal("63000"),),
            tp_close_pcts=(1.0,),
            opened_at_candle_ts=1_700_000_000_000,
            timeframe="15m",
        )
        runner._vp_store.open(vp)

    def test_shutdown_broadcasts_per_strategy_with_open_vps(self):
        raw = _base_raw_config()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
            {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
        ]
        runner, notifier, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        self._seed_vp(runner, "rsi_no_retest", "BTC/USDT")
        self._seed_vp(runner, "rsi_wma_retest", "ETH/USDT")
        notifier.reset_mock()

        runner.stop()

        broadcast_calls = [
            c for c in notifier.send_message.call_args_list
            if "Signal bot shutting down" in c.args[0]
        ]
        topic_ids = {c.kwargs["topic_id"] for c in broadcast_calls}
        assert topic_ids == {42, 43}

    def test_skips_broadcast_for_strategy_with_no_vps(self):
        raw = _base_raw_config()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
            {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
        ]
        runner, notifier, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        self._seed_vp(runner, "rsi_no_retest", "BTC/USDT")
        notifier.reset_mock()

        runner.stop()

        broadcast_calls = [
            c for c in notifier.send_message.call_args_list
            if "Signal bot shutting down" in c.args[0]
        ]
        assert len(broadcast_calls) == 1
        assert broadcast_calls[0].kwargs["topic_id"] == 42


class TestStop:
    def test_stop_is_idempotent(self):
        runner, _, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            stream_instance = MagicMock()
            Stream.return_value = stream_instance
            runner.start()

        runner.stop()
        # Second stop should be a silent no-op.
        runner.stop()
        stream_instance.stop.assert_called_once()

    def test_stop_before_start_is_safe(self):
        runner, _, _ = _mk_runner()
        # Never started → stop must not raise.
        runner.stop()

    def test_stop_stops_stream_and_drains_notifier(self):
        runner, notifier, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            stream = MagicMock()
            Stream.return_value = stream
            runner.start()

        runner.stop()
        stream.stop.assert_called_once()
        notifier.stop.assert_called_once()

    def test_stop_joins_worker_threads(self):
        runner, _, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        runner.stop()
        for thread in runner._threads:
            assert not thread.is_alive()


class TestWait:
    def test_wait_unblocks_promptly_on_stop(self):
        """wait() must react to stop() within a second, not the previous
        time.sleep(1) worst case."""
        import threading
        import time
        runner, _, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        t = threading.Thread(target=runner.wait, daemon=True)
        t.start()
        time.sleep(0.1)
        stopped_at = time.monotonic()
        runner.stop()
        t.join(timeout=2.0)
        elapsed = time.monotonic() - stopped_at
        assert not t.is_alive()
        assert elapsed < 1.5  # would have been up to 2+ s with sleep-based wait

    def test_shutdown_broadcast_failure_does_not_skip_subsequent_steps(self):
        """A notifier.send_message exception during broadcast must not
        prevent worker-join and notifier.stop."""
        runner, notifier, _ = _mk_runner()
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        # Seed a VP so the broadcast path runs.
        from decimal import Decimal

        from app.signal.virtual_position import VirtualPosition
        runner._vp_store.open(
            VirtualPosition(
                signal_id="RSIN#001",
                strategy_name="rsi_no_retest",
                symbol="BTC/USDT",
                side="LONG",
                entry_price=Decimal("62000"),
                sl_price=Decimal("61500"),
                tp_levels=(Decimal("63000"),),
                tp_close_pcts=(1.0,),
                opened_at_candle_ts=1_700_000_000_000,
                timeframe="15m",
            )
        )

        notifier.send_message.side_effect = RuntimeError("tg boom")
        runner.stop()

        # Worker joined (thread not alive) and notifier.stop() still called.
        for thread in runner._threads:
            assert not thread.is_alive()
        notifier.stop.assert_called_once()


class TestFilteredCallback:
    def test_closure_routes_only_matching_targets(self):
        worker = MagicMock()
        worker.instance_cfg = StrategyInstanceConfig(
            name="rsi_no_retest",
            telegram_topic_id=42,
            symbols=("BTC/USDT",),
            timeframe="15m",
            risk=MagicMock(),
        )
        cb = _make_filtered_callback(worker)

        candle = MagicMock()
        cb("BTC/USDT", "15m", candle)
        cb("ETH/USDT", "15m", candle)
        cb("BTC/USDT", "1h", candle)

        worker.enqueue.assert_called_once_with("BTC/USDT", "15m", candle)


def _btc_entry(**overrides) -> dict:
    entry = {
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
    entry.update(overrides)
    return entry


class TestBtcAlertComponentIntegration:
    def test_mixed_ordinary_and_btc_build_both_worker_groups(self):
        raw = _base_raw_config()
        raw["strategies"].append(_btc_entry())
        runner, notifier, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        assert len(runner._workers) == 1
        assert len(runner._alert_workers) == 1
        assert len(runner._alert_threads) == 1
        # strategies stays ordinary-only; typed alert config exposed separately.
        assert [c.name for c in runner.strategies] == ["rsi_no_retest"]
        assert [c.name for c in runner.alert_components] == ["btc_rsi_cross_alert"]

        stream_kwargs = Stream.call_args.kwargs
        assert {("BTC/USDT", "5m"), ("BTC/USDT", "15m"), ("BTC/USDT", "4h")} <= set(
            stream_kwargs["targets"]
        )
        assert callable(stream_kwargs["history_complete_callback"])
        runner.stop()

    def test_alert_only_config_starts_stream_and_worker(self):
        raw = _base_raw_config()
        raw["strategies"] = [_btc_entry()]
        runner, _, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        assert runner.strategies == []
        assert len(runner.alert_components) == 1
        assert len(runner._workers) == 0
        assert len(runner._alert_workers) == 1
        Stream.assert_called_once()

        # The history-complete hook arms every alert worker when invoked.
        hook = Stream.call_args.kwargs["history_complete_callback"]
        hook()
        assert runner._alert_workers[0].is_history_ready
        runner.stop()

    def test_all_components_disabled_is_clean_noop(self):
        raw = _base_raw_config()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": False, "telegram_topic_id": 42},
            _btc_entry(active=False),
        ]
        runner, _, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            runner.start()
            Stream.assert_not_called()
        assert runner._workers == []
        assert runner._alert_workers == []
        assert runner._stream is None
        runner.stop()

    def test_topic_collision_between_ordinary_and_btc_rejected(self):
        raw = _base_raw_config()
        raw["strategies"].append(_btc_entry(telegram_topic_id=42))
        runner, _, _ = _mk_runner(raw)
        with pytest.raises(ValueError, match="already used by"):
            with patch("app.signal.runner.BinanceStreamManager"):
                runner.start()

    def test_btc_topic_colliding_with_debug_topic_rejected(self):
        raw = _base_raw_config()
        raw["strategies"] = [_btc_entry(telegram_topic_id=99)]
        runner, _, _ = _mk_runner(raw)
        with pytest.raises(ValueError, match="debug_topic_id"):
            with patch("app.signal.runner.BinanceStreamManager"):
                runner.start()

    def test_stop_joins_alert_threads_and_sends_no_vp_broadcast_for_btc(self):
        raw = _base_raw_config()
        raw["strategies"] = [_btc_entry()]
        runner, notifier, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        notifier.reset_mock()
        runner.stop()

        for thread in runner._alert_threads:
            assert not thread.is_alive()
        # No virtual-position shutdown broadcast: the alert owns no VPs.
        broadcasts = [
            c for c in notifier.send_message.call_args_list
            if "Signal bot shutting down" in c.args[0]
        ]
        assert broadcasts == []

    def test_alert_only_wait_returns_immediately_on_stop(self):
        import threading

        raw = _base_raw_config()
        raw["strategies"] = [_btc_entry()]
        runner, _, _ = _mk_runner(raw)
        with patch("app.signal.runner.BinanceStreamManager") as Stream:
            Stream.return_value = MagicMock()
            runner.start()

        t = threading.Thread(target=runner.wait, daemon=True)
        t.start()
        runner.stop()
        t.join(timeout=2.0)
        assert not t.is_alive()
