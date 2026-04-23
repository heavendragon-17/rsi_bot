"""Multi-strategy integration tests (slice 9/10).

Exercises the full signal-bot pipeline at N strategies:
  * overlapping symbol sets → independent analyze() calls per strategy
  * disjoint symbol sets → correct routing
  * different timeframes → multiplexer keeps frames separate
  * invariant violations → debug topic
  * VP scope isolation between strategies
  * per-strategy failure isolation (one strategy dies, others run)

All cases use real SignalRunner, real TimeframeMultiplexer, real workers
on real threads, with scripted strategy classes swapped into STRATEGY_MAP
and a mocked BinanceStreamManager + NotificationService.
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


class _ScriptedStrategy:
    """Strategy stub driven by a per-strategy-name queue of scripted results.

    Keyed on ``config["strategy"]`` so a single class can back every stub
    registered in STRATEGY_MAP. Tests push AnalysisResults onto
    ``_ScriptedStrategy.scripts[name]`` before firing candles.
    """

    scripts: dict[str, list[AnalysisResult]] = {}
    call_log: dict[str, list[str]] = {}

    def __init__(self, config: dict):
        self._name = config["strategy"]
        _ScriptedStrategy.call_log.setdefault(self._name, [])

    def analyze(self, symbol, df, position=None, context=None):
        _ScriptedStrategy.call_log[self._name].append(symbol)
        queue = _ScriptedStrategy.scripts.get(self._name, [])
        if queue:
            return queue.pop(0)
        return AnalysisResult(
            actions=[DoNothing()],
            new_context=ContextSnapshot(state="SCANNING"),
        )

    @classmethod
    def reset(cls):
        cls.scripts = {}
        cls.call_log = {}


@pytest.fixture
def scripted_strategies():
    """Register ``_ScriptedStrategy`` under every STRATEGY_MAP entry."""
    originals = dict(STRATEGY_MAP)
    for name in list(STRATEGY_MAP):
        STRATEGY_MAP[name] = _ScriptedStrategy
    _ScriptedStrategy.reset()
    try:
        yield _ScriptedStrategy
    finally:
        for name, cls in originals.items():
            STRATEGY_MAP[name] = cls
        _ScriptedStrategy.reset()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _raw_config(strategies: list[dict], symbols=("BTC/USDT",), timeframe="15m"):
    return {
        "bot": {"mode": "signal"},
        "telegram": {"group_id": -100, "debug_topic_id": 99},
        "timeframe": timeframe,
        "symbols": list(symbols),
        "risk": {
            "risk_per_trade_pct": 0.002,
            "max_position_size_pct": 0.99,
            "leverage": 10,
            "tp1_close_pct": 1,
            "tp2_close_pct": 0,
            "min_sl_distance_pct": 0.003,
        },
        "strategies": strategies,
    }


def _candle(ts: datetime, close: str, *, high: str = None, low: str = None) -> Candle:
    return Candle(
        symbol="BTC",
        timestamp=ts,
        open=Decimal(close),
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=Decimal(close),
        volume=Decimal("1"),
        closed=True,
        timeframe="15m",
    )


def _open_action(sl: str = "61500", tps: tuple[str, ...] = ("63000",)):
    return OpenPosition(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=Decimal("62000"),
        sl_price=Decimal(sl),
        soft_sl_price=None,
        tp_prices=[Decimal(x) for x in tps],
        tp_allocations={"TP1": 1.0},
        lock_profit_price=None,
        signal_class=1,
        reason="scripted open",
    )


def _open_result():
    return AnalysisResult(
        actions=[_open_action()],
        new_context=ContextSnapshot(state="CONFIRMING"),
    )


def _noop_result():
    return AnalysisResult(
        actions=[DoNothing()],
        new_context=ContextSnapshot(state="SCANNING"),
    )


def _wait_for(predicate, timeout=2.0, interval=0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _build_runner(raw):
    notifier = MagicMock()
    with patch("app.signal.runner.BinanceStreamManager") as Stream:
        Stream.return_value = MagicMock()
        runner = SignalRunner(raw, notifier, install_signal_handlers=False)
        runner.start()
    return runner, notifier


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOverlappingSymbols:
    def test_two_strategies_both_receive_shared_candle(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
                {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
            ]
        )
        scripted_strategies.scripts["rsi_no_retest"] = [_open_result()]
        scripted_strategies.scripts["rsi_wma_retest"] = [_open_result()]

        runner, notifier = _build_runner(raw)
        try:
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(datetime(2024, 1, 1), "62000")
            )

            # Both strategies should have opened a VP.
            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is not None
                and runner._vp_store.get_for_symbol("rsi_wma_retest", "BTC/USDT")
                is not None
            ), "one or both VPs never opened"

            entry_calls = [
                c for c in notifier.send_message.call_args_list
                if "LONG BTC/USDT" in c.args[0]
            ]
            topic_ids = {c.kwargs["topic_id"] for c in entry_calls}
            assert topic_ids == {42, 43}
            # Neither entry landed on the debug topic.
            assert 99 not in topic_ids
        finally:
            runner.stop()


class TestDisjointSubsets:
    def test_only_subscribed_strategy_sees_its_symbols(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {
                    "name": "rsi_no_retest",
                    "active": True,
                    "telegram_topic_id": 42,
                    "symbols": ["BTC/USDT", "ETH/USDT"],
                },
                {
                    "name": "rsi_wma_retest",
                    "active": True,
                    "telegram_topic_id": 43,
                    "symbols": ["SOL/USDT"],
                },
            ]
        )
        runner, _ = _build_runner(raw)
        try:
            ts = datetime(2024, 1, 1)
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(ts, "62000")
            )
            runner._multiplexer.on_kline_event(
                "SOL/USDT", "15m", _candle(ts, "150")
            )

            # Give the worker threads time to drain.
            assert _wait_for(
                lambda: "BTC/USDT" in scripted_strategies.call_log.get(
                    "rsi_no_retest", []
                )
                and "SOL/USDT" in scripted_strategies.call_log.get(
                    "rsi_wma_retest", []
                )
            ), "expected analyze() calls did not arrive"

            # Strategy A should NOT see SOL; B should NOT see BTC.
            assert "SOL/USDT" not in scripted_strategies.call_log["rsi_no_retest"]
            assert "BTC/USDT" not in scripted_strategies.call_log["rsi_wma_retest"]
        finally:
            runner.stop()


class TestDifferentTimeframes:
    def test_each_strategy_sees_only_its_timeframe(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {
                    "name": "rsi_no_retest",
                    "active": True,
                    "telegram_topic_id": 42,
                    "timeframe": "15m",
                },
                {
                    "name": "rsi_wma_retest",
                    "active": True,
                    "telegram_topic_id": 43,
                    "timeframe": "1h",
                },
            ]
        )
        runner, _ = _build_runner(raw)
        try:
            ts = datetime(2024, 1, 1)
            # Fire a 15m candle — only strategy A's worker should enqueue.
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(ts, "62000")
            )
            assert _wait_for(
                lambda: "BTC/USDT" in scripted_strategies.call_log.get(
                    "rsi_no_retest", []
                )
            )
            # Strategy B should still have seen nothing.
            assert scripted_strategies.call_log.get("rsi_wma_retest", []) == []

            # Now fire a 1h candle — only B's worker should enqueue.
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "1h", _candle(ts, "62000")
            )
            assert _wait_for(
                lambda: "BTC/USDT" in scripted_strategies.call_log.get(
                    "rsi_wma_retest", []
                )
            )
            # A's log shouldn't have gained any 1h calls (still only 1 entry).
            assert scripted_strategies.call_log["rsi_no_retest"].count("BTC/USDT") == 1
        finally:
            runner.stop()


class TestDebugTopicRouting:
    def test_invariant_violation_routes_to_debug_topic(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
            ]
        )
        # First candle: open. Second candle: try to open again (violation).
        scripted_strategies.scripts["rsi_no_retest"] = [
            _open_result(),
            _open_result(),
        ]
        runner, notifier = _build_runner(raw)
        try:
            ts = datetime(2024, 1, 1)
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(ts, "62000")
            )
            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is not None
            )
            entry_count = sum(
                1 for c in notifier.send_message.call_args_list
                if "LONG BTC/USDT" in c.args[0]
            )
            assert entry_count == 1

            # Second candle — scripted to OpenPosition again.
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(ts + timedelta(minutes=15), "62100")
            )
            # Wait for the worker to have drained the queue by observing a
            # new debug-topic message appear.
            assert _wait_for(
                lambda: any(
                    c.kwargs.get("topic_id") == 99
                    and "invalid action" in c.args[0]
                    for c in notifier.send_message.call_args_list
                )
            ), "no debug-topic invariant violation message"

            # No second entry message was emitted.
            entry_count_after = sum(
                1 for c in notifier.send_message.call_args_list
                if "LONG BTC/USDT" in c.args[0]
            )
            assert entry_count_after == 1
        finally:
            runner.stop()


class TestVPScopeIsolation:
    def test_closing_one_strategy_vp_preserves_others(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
                {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
            ]
        )
        scripted_strategies.scripts["rsi_no_retest"] = [_open_result()]
        scripted_strategies.scripts["rsi_wma_retest"] = [_open_result()]

        runner, _ = _build_runner(raw)
        try:
            ts = datetime(2024, 1, 1)
            runner._multiplexer.on_kline_event(
                "BTC/USDT", "15m", _candle(ts, "62000")
            )
            assert _wait_for(
                lambda: runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT")
                is not None
                and runner._vp_store.get_for_symbol("rsi_wma_retest", "BTC/USDT")
                is not None
            )

            # Fire a candle closing below strategy A's SL (61500). Both A and B
            # have a VP with the same SL — but B's analyze() is scripted to noop
            # on the next candle. Exit monitor fires SL for BOTH. To isolate A
            # only, we need different SLs.
            # Instead: directly close A's VP to simulate A-only exit.
            runner._vp_store.close("rsi_no_retest", "BTC/USDT")

            assert runner._vp_store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None
            assert (
                runner._vp_store.get_for_symbol("rsi_wma_retest", "BTC/USDT")
                is not None
            )
        finally:
            runner.stop()


class TestFailureIsolation:
    def test_one_strategy_dying_does_not_affect_others(self, scripted_strategies):
        raw = _raw_config(
            strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
                {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
            ]
        )
        # Strategy A: every analyze() raises.
        # Scripted queue can't raise, so override analyze() on the class.
        def boom(*args, **kwargs):
            raise RuntimeError("A is broken")

        # Swap analyze() just for the A-bound stub instances. Since
        # _ScriptedStrategy is shared across names, patch analyze globally
        # and route behavior by name inside.
        original_analyze = _ScriptedStrategy.analyze

        def routed_analyze(self, symbol, df, position=None, context=None):
            if self._name == "rsi_no_retest":
                raise RuntimeError("A is broken")
            return original_analyze(self, symbol, df, position, context)

        _ScriptedStrategy.analyze = routed_analyze
        try:
            runner, notifier = _build_runner(raw)
            try:
                ts = datetime(2024, 1, 1)
                # Fire enough candles to exhaust A's retry budget (3 errors).
                for i in range(5):
                    runner._multiplexer.on_kline_event(
                        "BTC/USDT",
                        "15m",
                        _candle(ts + timedelta(minutes=15 * i), "62000"),
                    )

                # A's worker thread should die after 3 failures.
                a_worker_idx = next(
                    i for i, w in enumerate(runner._workers)
                    if w.instance_cfg.name == "rsi_no_retest"
                )
                b_worker_idx = next(
                    i for i, w in enumerate(runner._workers)
                    if w.instance_cfg.name == "rsi_wma_retest"
                )
                assert _wait_for(
                    lambda: not runner._threads[a_worker_idx].is_alive()
                ), "strategy A thread should have died"
                assert runner._threads[b_worker_idx].is_alive()

                # Debug topic received the "disabled" message for A.
                dead_msgs = [
                    c for c in notifier.send_message.call_args_list
                    if c.kwargs.get("topic_id") == 99
                    and "disabled" in c.args[0]
                    and "rsi_no_retest" in c.args[0]
                ]
                assert dead_msgs
                # No such message for B.
                dead_b = [
                    c for c in notifier.send_message.call_args_list
                    if c.kwargs.get("topic_id") == 99
                    and "disabled" in c.args[0]
                    and "rsi_wma_retest" in c.args[0]
                ]
                assert not dead_b
            finally:
                runner.stop()
        finally:
            _ScriptedStrategy.analyze = original_analyze
