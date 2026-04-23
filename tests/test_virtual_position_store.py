"""Tests for VirtualPosition + VirtualPositionStore (signal bot, slice 5)."""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from app.signal.virtual_position import (
    VirtualPosition,
    VirtualPositionStore,
    VPNotFoundError,
    derive_id_prefix,
)


def _mk_vp(
    *,
    signal_id="RSIN#001",
    strategy_name="rsi_no_retest",
    symbol="BTC/USDT",
    side="LONG",
    sl="60000",
    tps=("62000", "64000"),
):
    return VirtualPosition(
        signal_id=signal_id,
        strategy_name=strategy_name,
        symbol=symbol,
        side=side,
        entry_price=Decimal("61000"),
        sl_price=Decimal(sl),
        tp_levels=tuple(Decimal(x) for x in tps),
        tp_close_pcts=tuple(0.5 for _ in tps),
        opened_at_candle_ts=1_700_000_000_000,
        timeframe="15m",
    )


class TestPrefix:
    def test_rsi_no_retest_prefix(self):
        assert derive_id_prefix("rsi_no_retest") == "RSIN"

    def test_rsi_wma_retest_prefix(self):
        assert derive_id_prefix("rsi_wma_retest") == "RSIW"

    def test_rsi_momentum_prefix(self):
        assert derive_id_prefix("rsi_momentum") == "RSIM"


class TestSignalIdCounter:
    def test_monotonic_per_strategy(self):
        store = VirtualPositionStore()
        ids = [store.next_signal_id("rsi_no_retest") for _ in range(3)]
        assert ids == ["RSIN#001", "RSIN#002", "RSIN#003"]

    def test_counters_independent_across_strategies(self):
        store = VirtualPositionStore()
        a = store.next_signal_id("rsi_no_retest")
        b = store.next_signal_id("rsi_wma_retest")
        c = store.next_signal_id("rsi_no_retest")
        assert a == "RSIN#001"
        assert b == "RSIW#001"
        assert c == "RSIN#002"


class TestOpenClose:
    def test_open_and_get(self):
        store = VirtualPositionStore()
        vp = _mk_vp()
        store.open(vp)
        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is vp

    def test_get_for_missing_returns_none(self):
        store = VirtualPositionStore()
        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None

    def test_open_duplicate_raises(self):
        store = VirtualPositionStore()
        store.open(_mk_vp())
        with pytest.raises(ValueError, match="already open"):
            store.open(_mk_vp())

    def test_close_returns_and_removes(self):
        store = VirtualPositionStore()
        vp = _mk_vp()
        store.open(vp)
        assert store.close("rsi_no_retest", "BTC/USDT") is vp
        assert store.get_for_symbol("rsi_no_retest", "BTC/USDT") is None

    def test_close_missing_returns_none(self):
        store = VirtualPositionStore()
        assert store.close("rsi_no_retest", "BTC/USDT") is None


class TestMutators:
    def test_update_sl_returns_new_vp(self):
        store = VirtualPositionStore()
        vp = _mk_vp(sl="60000")
        store.open(vp)
        updated = store.update_sl("rsi_no_retest", "BTC/USDT", Decimal("60500"))
        assert updated.sl_price == Decimal("60500")
        assert vp.sl_price == Decimal("60000")  # original frozen, untouched

    def test_update_sl_missing_raises(self):
        store = VirtualPositionStore()
        with pytest.raises(VPNotFoundError):
            store.update_sl("rsi_no_retest", "BTC/USDT", Decimal("1"))

    def test_mark_tp_hit_adds_index(self):
        store = VirtualPositionStore()
        store.open(_mk_vp())
        updated = store.mark_tp_hit("rsi_no_retest", "BTC/USDT", 0)
        assert updated.tp_hits == frozenset({0})
        after_again = store.mark_tp_hit("rsi_no_retest", "BTC/USDT", 1)
        assert after_again.tp_hits == frozenset({0, 1})

    def test_mark_tp_hit_missing_raises(self):
        store = VirtualPositionStore()
        with pytest.raises(VPNotFoundError):
            store.mark_tp_hit("rsi_no_retest", "BTC/USDT", 0)

    def test_mark_tp_hit_idempotent(self):
        store = VirtualPositionStore()
        store.open(_mk_vp())
        store.mark_tp_hit("rsi_no_retest", "BTC/USDT", 0)
        updated = store.mark_tp_hit("rsi_no_retest", "BTC/USDT", 0)
        assert updated.tp_hits == frozenset({0})


class TestAllOpen:
    def test_all_open_scoped_per_strategy(self):
        store = VirtualPositionStore()
        store.open(_mk_vp(strategy_name="rsi_no_retest", symbol="BTC/USDT"))
        store.open(_mk_vp(strategy_name="rsi_no_retest", symbol="ETH/USDT"))
        store.open(_mk_vp(strategy_name="rsi_wma_retest", symbol="BTC/USDT"))

        rsi_no = store.all_open("rsi_no_retest")
        rsi_wma = store.all_open("rsi_wma_retest")
        assert {v.symbol for v in rsi_no} == {"BTC/USDT", "ETH/USDT"}
        assert {v.symbol for v in rsi_wma} == {"BTC/USDT"}

    def test_all_open_by_strategy_groups_correctly(self):
        store = VirtualPositionStore()
        store.open(_mk_vp(strategy_name="rsi_no_retest", symbol="BTC/USDT"))
        store.open(_mk_vp(strategy_name="rsi_wma_retest", symbol="ETH/USDT"))
        grouped = store.all_open_by_strategy()
        assert set(grouped.keys()) == {"rsi_no_retest", "rsi_wma_retest"}
        assert len(grouped["rsi_no_retest"]) == 1
        assert len(grouped["rsi_wma_retest"]) == 1


class TestThreadSafety:
    def test_concurrent_opens_produce_no_corruption(self):
        """Many threads opening VPs for distinct symbols concurrently."""
        store = VirtualPositionStore()
        errors: list[Exception] = []

        def worker(i: int):
            try:
                store.open(
                    _mk_vp(
                        signal_id=f"RSIN#{i:03d}",
                        symbol=f"SYM{i}/USDT",
                    )
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(store.all_open("rsi_no_retest")) == 50

    def test_concurrent_next_signal_id_is_unique(self):
        store = VirtualPositionStore()
        ids: list[str] = []
        lock = threading.Lock()

        def worker():
            sid = store.next_signal_id("rsi_no_retest")
            with lock:
                ids.append(sid)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(ids)) == 100
