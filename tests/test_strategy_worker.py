"""Tests for StrategyWorker — action dispatch + exit-event application."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd

from app.core.actions import (
    ClosePosition,
    DoNothing,
    MoveSL,
    OpenPosition,
    PartialClose,
)
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


def _mk_instance_cfg(
    *,
    name="rsi_no_retest",
    symbols=("BTC/USDT",),
    timeframe="15m",
):
    return StrategyInstanceConfig(
        name=name,
        telegram_topic_id=STRATEGY_TOPIC,
        symbols=symbols,
        timeframe=timeframe,
        risk=RiskConfig(),
    )


def _mk_candle(symbol="BTC", ts=None, close="62000", high="62500", low="61500"):
    return Candle(
        symbol=symbol,
        timestamp=ts or datetime(2024, 1, 1, 0, 0, 0),
        open=Decimal("62000"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1"),
        closed=True,
        timeframe="15m",
    )


def _mk_worker(
    *,
    strategy=None,
    multiplexer=None,
    vp_store=None,
    notifier=None,
    symbols=("BTC/USDT",),
    **kwargs,
):
    cfg = _mk_instance_cfg(symbols=symbols)
    strategy = strategy or MagicMock()
    if multiplexer is None:
        mux = MagicMock(spec=TimeframeMultiplexer)
        mux.get_dataframe.return_value = pd.DataFrame({"close": [1]})
    else:
        mux = multiplexer
    store = vp_store or VirtualPositionStore()
    notifier = notifier or MagicMock()
    worker = StrategyWorker(
        instance_cfg=cfg,
        strategy=strategy,
        multiplexer=mux,
        vp_store=store,
        notifier=notifier,
        debug_topic_id=DEBUG_TOPIC,
        **kwargs,
    )
    return worker, strategy, mux, store, notifier


def _noop_result():
    return AnalysisResult(
        actions=[DoNothing()],
        new_context=ContextSnapshot(state="SCANNING"),
    )


class TestQueueEnqueue:
    def test_enqueue_puts_triple(self):
        worker, *_ = _mk_worker()
        candle = _mk_candle()
        worker.enqueue("BTC/USDT", "15m", candle)
        assert worker._queue.get_nowait() == ("BTC/USDT", "15m", candle)

    def test_enqueue_drops_when_full(self):
        worker, *_ = _mk_worker(queue_size=1)
        worker.enqueue("BTC/USDT", "15m", _mk_candle())
        # Second enqueue should drop silently (not raise).
        worker.enqueue("BTC/USDT", "15m", _mk_candle(close="63000"))
        assert worker._queue.qsize() == 1

    def test_untargeted_candle_ignored(self):
        worker, strategy, *_ = _mk_worker(symbols=("BTC/USDT",))
        # Directly hit _process with non-target symbol via a raw run-loop path
        # is too invasive; instead, drive run() with stop sentinel after one
        # non-target enqueue.
        worker.enqueue("DOGE/USDT", "15m", _mk_candle())
        worker.request_stop()
        worker.run()
        strategy.analyze.assert_not_called()


class TestOpenAction:
    def test_open_creates_vp_and_sends_entry_message(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
            actions=[
                OpenPosition(
                    symbol="BTC/USDT",
                    side="BUY",
                    entry_price=Decimal("62340"),
                    sl_price=Decimal("61800"),
                    soft_sl_price=None,
                    tp_prices=[Decimal("62960"), Decimal("63500")],
                    tp_allocations={"TP1": 0.5, "TP2": 0.5},
                    lock_profit_price=None,
                    signal_class=1,
                    reason="rsi cross",
                )
            ],
            new_context=ContextSnapshot(state="CONFIRMING"),
        )
        worker, *_, store, notifier = _mk_worker(strategy=strategy)

        worker._process("BTC/USDT", "15m", _mk_candle())

        vp = store.get_for_symbol("rsi_no_retest", "BTC/USDT")
        assert vp is not None
        assert vp.side == "LONG"
        assert vp.sl_price == Decimal("61800")
        assert vp.tp_levels == (Decimal("62960"), Decimal("63500"))
        # Entry message went to the strategy topic, not debug.
        notifier.send_message.assert_called_once()
        args, kwargs = notifier.send_message.call_args
        assert kwargs["topic_id"] == STRATEGY_TOPIC
        assert "LONG" in args[0]
        assert "BTC/USDT" in args[0]

    def test_short_maps_sell_side(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
            actions=[
                OpenPosition(
                    symbol="BTC/USDT",
                    side="SELL",
                    entry_price=Decimal("62000"),
                    sl_price=Decimal("62500"),
                    soft_sl_price=None,
                    tp_prices=[Decimal("61000")],
                    tp_allocations={"TP1": 1.0},
                    lock_profit_price=None,
                    signal_class=1,
                    reason="short setup",
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, store, _ = _mk_worker(strategy=strategy)

        worker._process("BTC/USDT", "15m", _mk_candle())

        vp = store.get_for_symbol("rsi_no_retest", "BTC/USDT")
        assert vp.side == "SHORT"

    def test_open_while_vp_exists_routes_to_debug(self):
        # First open
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
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
                    reason="first",
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, notifier = _mk_worker(strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        notifier.reset_mock()

        # Attempt a second open — debug warn, no change
        strategy.analyze.return_value = AnalysisResult(
            actions=[
                OpenPosition(
                    symbol="BTC/USDT",
                    side="BUY",
                    entry_price=Decimal("62100"),
                    sl_price=Decimal("61600"),
                    soft_sl_price=None,
                    tp_prices=[Decimal("63100")],
                    tp_allocations={"TP1": 1.0},
                    lock_profit_price=None,
                    signal_class=1,
                    reason="scale-in",
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        # PositionSnapshot for second call reflects existing VP.
        worker._process("BTC/USDT", "15m", _mk_candle(close="62100"))

        # All send_message calls during the second iteration should go to debug.
        for call in notifier.send_message.call_args_list:
            assert call.kwargs["topic_id"] == DEBUG_TOPIC


class TestCloseAction:
    def test_close_with_vp_closes_and_messages_strategy_topic(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
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
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        notifier.reset_mock()

        strategy.analyze.return_value = AnalysisResult(
            actions=[
                ClosePosition(
                    symbol="BTC/USDT",
                    reason="strategy close",
                    price=Decimal("62500"),
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker._process("BTC/USDT", "15m", _mk_candle(close="62500"))

        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None
        # Exit message went to strategy topic.
        assert any(
            c.kwargs["topic_id"] == STRATEGY_TOPIC
            and "STRATEGY EXIT" in c.args[0]
            for c in notifier.send_message.call_args_list
        )

    def test_close_without_vp_routes_to_debug(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
            actions=[ClosePosition(symbol="BTC/USDT", reason="x", price=None)],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, notifier = _mk_worker(strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        for c in notifier.send_message.call_args_list:
            assert c.kwargs["topic_id"] == DEBUG_TOPIC


class TestMoveSL:
    def test_updates_vp_and_messages_strategy(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
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
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        notifier.reset_mock()

        strategy.analyze.return_value = AnalysisResult(
            actions=[
                MoveSL(symbol="BTC/USDT", new_sl_price=Decimal("61800"), reason="trail")
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker._process("BTC/USDT", "15m", _mk_candle())

        vp = store.get_for_symbol("rsi_no_retest", "BTC/USDT")
        assert vp.sl_price == Decimal("61800")
        assert any(
            "SL MOVED" in c.args[0] and c.kwargs["topic_id"] == STRATEGY_TOPIC
            for c in notifier.send_message.call_args_list
        )


class TestPartialClose:
    def test_message_sent_but_vp_stays(self):
        strategy = MagicMock()
        strategy.analyze.return_value = AnalysisResult(
            actions=[
                OpenPosition(
                    symbol="BTC/USDT",
                    side="BUY",
                    entry_price=Decimal("62000"),
                    sl_price=Decimal("61500"),
                    soft_sl_price=None,
                    tp_prices=[Decimal("63000"), Decimal("64000")],
                    tp_allocations={"TP1": 0.5, "TP2": 0.5},
                    lock_profit_price=None,
                    signal_class=1,
                    reason="open",
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        notifier.reset_mock()

        strategy.analyze.return_value = AnalysisResult(
            actions=[
                PartialClose(
                    symbol="BTC/USDT",
                    tp_level="TP1",
                    price=Decimal("63010"),
                    reason="tp1",
                    new_sl_price=None,
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker._process("BTC/USDT", "15m", _mk_candle())

        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is not None
        assert any("PARTIAL CLOSE" in c.args[0] for c in notifier.send_message.call_args_list)


class TestExitMonitorIntegration:
    def _seed_vp(self, worker, strategy):
        strategy.analyze.return_value = AnalysisResult(
            actions=[
                OpenPosition(
                    symbol="BTC/USDT",
                    side="BUY",
                    entry_price=Decimal("62000"),
                    sl_price=Decimal("61500"),
                    soft_sl_price=None,
                    tp_prices=[Decimal("63000"), Decimal("64000")],
                    tp_allocations={"TP1": 0.5, "TP2": 0.5},
                    lock_profit_price=None,
                    signal_class=1,
                    reason="open",
                )
            ],
            new_context=ContextSnapshot(state="SCANNING"),
        )
        worker._process("BTC/USDT", "15m", _mk_candle())
        strategy.analyze.reset_mock()

    def test_sl_hit_closes_vp_skips_analyze(self):
        strategy = MagicMock()
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        self._seed_vp(worker, strategy)
        notifier.reset_mock()

        # close below SL → SL hit
        worker._process("BTC/USDT", "15m", _mk_candle(close="61000", high="62100", low="60900"))

        strategy.analyze.assert_not_called()
        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None
        assert any(
            "EXIT advice" in c.args[0] and c.kwargs["topic_id"] == STRATEGY_TOPIC
            for c in notifier.send_message.call_args_list
        )

    def test_tp_hit_messages_and_updates(self):
        strategy = MagicMock()
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        self._seed_vp(worker, strategy)
        notifier.reset_mock()

        # high reaches TP1 only
        worker._process("BTC/USDT", "15m", _mk_candle(high="63100", close="62700"))

        vp = store.get_for_symbol("rsi_no_retest", "BTC/USDT")
        assert vp is not None
        assert 0 in vp.tp_hits
        assert any("TP1 hit" in c.args[0] for c in notifier.send_message.call_args_list)

    def test_final_tp_closes_vp(self):
        strategy = MagicMock()
        worker, *_, store, notifier = _mk_worker(strategy=strategy)
        self._seed_vp(worker, strategy)
        notifier.reset_mock()

        # high reaches both TPs this candle
        worker._process("BTC/USDT", "15m", _mk_candle(high="64100", close="62700"))

        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None


class TestDataGuards:
    def test_empty_dataframe_skips_analyze(self):
        mux = MagicMock(spec=TimeframeMultiplexer)
        mux.get_dataframe.return_value = None
        strategy = MagicMock()
        worker, *_ = _mk_worker(multiplexer=mux, strategy=strategy)
        worker._process("BTC/USDT", "15m", _mk_candle())
        strategy.analyze.assert_not_called()


class TestStop:
    def test_request_stop_unblocks_run(self):
        worker, *_ = _mk_worker()
        import threading
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        worker.request_stop()
        t.join(timeout=2.0)
        assert not t.is_alive()
