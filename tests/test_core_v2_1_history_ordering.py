"""Temporal-ordering tests for the Core V2.1 shared-engine bridge (synthetic).

The shared loop processes each candle's high/low (resting-order fills)
BEFORE the adapter's actions for that candle, while entry/stop actions are
priced at that candle's open (next-open semantics labeled as candle-price
proxies).  These tests pin the consequences through real components:

* same-candle TP-before-stop fills are kept (documented difference from the
  reference simulator, which ignored them);
* entry-candle TP touches never fill (limits are placed after that candle's
  fill check);
* a stop exit cancels remaining TPs (no orphan fills afterwards);
* entry_fired records without a BUY fill are reported as order skips;
* pre-seeded warmed states continue the exact 15-minute cadence.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.core_v2_1.engine_adapter import CoreV21EngineStrategy, _SymbolState
from app.backtest.core_v2_1.engine_backtest import build_positions
from app.backtest.core_v2_1.engine_history import cross_check_fills, warmup_state
from app.backtest.core_v2_1.replay import ReplayFrames
from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
from app.backtest.engine.portfolio_engine import PortfolioEngine
from app.backtest.exchange.mock_exchange import MockExchange

SYMBOL = "ETHUSDT"
N = 70
START = pd.Timestamp("2026-06-01T00:15:00Z")


def _m15_frame(n: int = N) -> pd.DataFrame:
    idx = pd.date_range(START, periods=n, freq="15min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10.0,
            "ema21": 101.0, "ema200": 90.0, "atr14": 1.5,
            "rsi21": 45.0, "rsi_ema9": 40.0, "rsi_wma45": 45.0,
        },
        index=idx,
    )
    frame.index.name = "timestamp"
    return frame


def _h_frame(m15: pd.DataFrame, freq: str, extra_cols: dict) -> pd.DataFrame:
    start = (m15.index[0] - pd.Timedelta(hours=4)).floor(freq)
    idx = pd.date_range(start, m15.index[-1], freq=freq, tz="UTC")
    data = {"rsi21": 45.0, "rsi_ema9": 40.0, "rsi_wma45": 45.0}
    data.update(extra_cols)
    frame = pd.DataFrame(data, index=idx)
    frame.index.name = "timestamp"
    return frame


def _frames(m15: pd.DataFrame) -> ReplayFrames:
    return ReplayFrames(
        alt_m15={SYMBOL: m15},
        alt_h1={SYMBOL: _h_frame(m15, "1h", {})},
        btc_h1=_h_frame(m15, "1h", {"close": 50000.0, "ema21": 51000.0}),
        btc_h4=_h_frame(m15, "4h", {}),
    )


def _arm_signal(m15: pd.DataFrame, btc_h1: pd.DataFrame, k: int) -> None:
    m15.loc[m15.index[k - 1], ["rsi_ema9", "rsi_wma45"]] = [44.0, 45.0]
    m15.loc[m15.index[k], ["open", "high", "low", "close"]] = [100.9, 101.2, 100.8, 101.0]
    m15.loc[m15.index[k], ["ema21", "ema200", "atr14"]] = [100.0, 90.0, 2.0]
    m15.loc[m15.index[k], ["rsi21", "rsi_ema9", "rsi_wma45"]] = [60.0, 46.0, 45.0]
    m15.loc[m15.index[k - 3], "ema21"] = 99.0


def _bullish_context(frames: ReplayFrames, as_of_row: int) -> None:
    as_of = frames.alt_m15[SYMBOL].index[as_of_row]
    h1_close = as_of.floor("1h")
    h4_close = as_of.floor("4h")
    for frame in (frames.alt_h1[SYMBOL], frames.btc_h1):
        frame.loc[h1_close, ["rsi21", "rsi_ema9", "rsi_wma45"]] = [60.0, 55.0, 54.0]
    frames.btc_h1.loc[h1_close, ["close", "ema21"]] = [50000.0, 49000.0]
    frames.btc_h4.loc[h4_close, ["rsi21", "rsi_ema9", "rsi_wma45"]] = [60.0, 55.0, 54.0]


TEST_CONFIG = {
    "risk": {
        "risk_per_trade_pct": 0.01,
        "max_position_size_pct": 10,
        "use_risk_based_sizing": True,
        "use_initial_capital_for_risk": True,
        "min_sl_distance_pct": 0.003,
        "leverage": 10,
        "taker_fee": 0.0005,
        "maker_fee": 0.0002,
    },
    "backtest": {"initial_balance": 10000},
    "slippage_pct": 0.001,
}


def _run(frames: ReplayFrames, seed_state=None, config: dict = TEST_CONFIG):
    CoreV21EngineStrategy.bind_frames(frames)
    try:
        exchange = MockExchange(
            initial_balance=config["backtest"]["initial_balance"],
            leverage=int(config["risk"]["leverage"]),
            taker_fee=float(config["risk"]["taker_fee"]),
            maker_fee=float(config["risk"]["maker_fee"]),
            slippage_pct=float(config.get("slippage_pct", 0.0)),
        )
        engine = PortfolioEngine(
            event_source=BatchPortfolioEventSource(
                {SYMBOL: frames.alt_m15[SYMBOL]}, start_idx=0
            ),
            strategy_class=CoreV21EngineStrategy,
            exchange=exchange,
            config=config,
            symbols=[SYMBOL],
        )
        if seed_state is not None:
            engine.strategy._states[SYMBOL] = _SymbolState(core=seed_state)
        results = engine.run()
        strategy: CoreV21EngineStrategy = engine.strategy
        strategy.finalize({SYMBOL: frames.alt_m15[SYMBOL].index[-1].isoformat()})
        return engine, exchange, strategy, results
    finally:
        CoreV21EngineStrategy.unbind_frames()


def _quiet_aftermath(m15: pd.DataFrame, k: int) -> None:
    # No re-arm, no stop, no TP touch after the entry candle.
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1]:, ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.5, 101.3, 101.5, 100.0]


def test_same_candle_tp_before_stop_is_kept():
    # TP1 = 101.7. Candle k+2 both touches TP1 (high) and closes below
    # EMA21 (stop trigger). Engine fill order keeps the standing TP fill,
    # then the stop exits only the remainder.
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1], ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.6, 101.3, 101.5, 100.0]
    m15.loc[m15.index[k + 2], ["open", "high", "low", "close", "ema21"]] = [
        101.5, 101.9, 98.9, 99.0, 100.0]
    m15.loc[m15.index[k + 3]:, ["open", "high", "low", "close", "ema21"]] = [
        99.0, 99.2, 98.8, 99.1, 100.0]
    _, exchange, strategy, _ = _run(frames)

    history = exchange.trade_history
    tp1 = [t for t in history if t["info"].get("exit_reason") == "TP1"]
    assert len(tp1) == 1
    assert Decimal(str(tp1[0]["price"])) == Decimal("101.7")
    stops = [t for t in history if (t["info"].get("exit_reason") or "").startswith("CORE_V2_1")]
    assert len(stops) == 1
    # Stop exits the remainder only: TP1 qty + stop qty == entry qty.
    entry = next(t for t in history if t["side"] == "BUY")
    assert float(Decimal(str(tp1[0]["filled"])) + Decimal(str(stops[0]["filled"]))) == pytest.approx(
        float(Decimal(str(entry["filled"]))), rel=1e-9
    )
    assert exchange.positions == {}


def test_entry_candle_tp_touch_does_not_fill():
    # Entry candle (k+1) high touches TP1, but limits are placed after that
    # candle's fill check, so no TP fill carries the entry candle's time.
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1], ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.9, 101.3, 101.5, 100.0]
    _quiet_aftermath(m15, k + 1)
    # Keep later highs below TP1 so the only touch is the entry candle.
    m15.loc[m15.index[k + 2]:, ["open", "high", "low", "close"]] = [
        101.4, 101.5, 101.3, 101.5]
    _, exchange, strategy, _ = _run(frames)

    fired = [r for r in strategy.ledger if r.get("type") == "entry_fired"][0]
    tp_fills = [t for t in exchange.trade_history if t["info"].get("exit_reason") == "TP1"]
    assert all(pd.Timestamp(t["time"]).isoformat() != fired["fill_time"] for t in tp_fills)
    assert tp_fills == []  # later candles stay quiet: nothing filled early
    positions, _ = build_positions(exchange.trade_history, strategy.ledger, Decimal("100"))
    assert len(positions) == 1
    assert positions[0]["close_reason"] == "EOD"  # forced window-end exit, labeled


def test_stop_exit_cancels_remaining_tps_no_orphan_fills():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1], ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.6, 101.3, 101.5, 100.0]
    # k+2 triggers the stop (close < EMA21), no TP touch.
    m15.loc[m15.index[k + 2], ["open", "high", "low", "close", "ema21"]] = [
        101.0, 101.1, 98.9, 99.0, 100.0]
    # k+3 is the stop-exit candle; k+4 high would touch TP2 if orders lived.
    m15.loc[m15.index[k + 3]:, ["open", "high", "low", "close", "ema21"]] = [
        99.0, 99.2, 98.8, 99.1, 100.0]
    m15.loc[m15.index[k + 4], ["high"]] = [105.0]
    _, exchange, _, _ = _run(frames)

    history = exchange.trade_history
    stop = next(t for t in history if (t["info"].get("exit_reason") or "").startswith("CORE_V2_1"))
    stop_time = pd.Timestamp(stop["time"])
    later_tps = [
        t for t in history
        if (t["info"].get("exit_reason") or "") in ("TP1", "TP2", "TP3")
        and pd.Timestamp(t["time"]) > stop_time
    ]
    assert later_tps == []


def test_cross_check_flags_fired_entries_without_buy():
    ledger = [
        {"type": "entry_fired", "symbol": "A", "fill_time": "2026-01-01T00:15:00+00:00",
         "event_type": "A_PLUS_LONG", "sequence": 1},
        {"type": "entry_fired", "symbol": "A", "fill_time": "2026-01-02T00:15:00+00:00",
         "event_type": "A_PLUS_LONG", "sequence": 2},
    ]
    history = [
        {"id": "mock_1", "symbol": "A", "side": "BUY", "filled": 10.0,
         "time": "2026-01-01T00:15:00+00:00"},
    ]
    check = cross_check_fills(history, ledger)
    assert check["entry_fired"] == 2
    assert check["buy_fills"] == 1
    assert check["matched"] == 1
    assert check["buys_without_fired"] == []
    assert len(check["fired_without_buy_order_skips"]) == 1
    assert check["fired_without_buy_order_skips"][0]["sequence"] == 2


def test_cross_check_matches_across_timestamp_formats():
    # Engine trade rows serialize pandas Timestamps with a space separator
    # while ledger records use ISO 'T' separators: same instant must match.
    import pandas as pd

    ledger = [
        {"type": "entry_fired", "symbol": "A",
         "fill_time": "2026-01-01T00:15:00+00:00",
         "event_type": "A_PLUS_LONG", "sequence": 1},
    ]
    history = [
        {"id": "mock_1", "symbol": "A", "side": "BUY", "filled": 10.0,
         "time": pd.Timestamp("2026-01-01T00:15:00+00:00")},
    ]
    assert str(history[0]["time"]) == "2026-01-01 00:15:00+00:00"  # space, not T
    check = cross_check_fills(history, ledger)
    assert check["matched"] == 1
    assert check["buys_without_fired"] == []
    assert check["fired_without_buy_order_skips"] == []


def test_preseeded_warm_state_continues_exact_cadence():
    # Warm the state machine over rows [k-10, k), seed it, and run the real
    # engine: no exact-cadence ValueError, and the armed cross still fires.
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    _quiet_aftermath(m15, k)
    m15.loc[m15.index[k + 1]:, ["open", "high", "low", "close"]] = [
        101.4, 101.5, 101.3, 101.5]

    # Warm over the 10 bars immediately before the engine's first analyzed
    # candle (index 49, since the engine gate skips 0..48).
    first_analyzed = m15.index[49]
    state, counts = warmup_state(
        SYMBOL, m15, frames.alt_h1[SYMBOL], frames.btc_h1, frames.btc_h4,
        m15.index[39], first_analyzed,
    )
    assert counts["warmed"] + counts["not_ready"] == 10
    assert state.last_processed_at == first_analyzed - pd.Timedelta(minutes=15)

    _, exchange, strategy, _ = _run(frames, seed_state=state)
    fired = [r for r in strategy.ledger if r.get("type") == "entry_fired"]
    assert len(fired) == 1  # the k-signal still fires exactly once
    assert exchange.positions == {}  # quiet aftermath runs to EOD


def test_short_mirror_preserves_r_distances():
    levels = {
        "reference_entry": "100", "reference_stop": "98", "risk_1r": "2",
        "tp1": "102", "tp2": "104", "tp3": "106",
    }
    mirrored = CoreV21EngineStrategy.mirror_short_levels(levels, Decimal("100.5"))
    assert mirrored["soft_stop"] == Decimal("102.5")  # fill + 1R
    assert mirrored["tp1"] == Decimal("98.5")  # fill - 1R
    assert mirrored["tp2"] == Decimal("96.5")  # fill - 2R
    assert mirrored["tp3"] == Decimal("94.5")  # fill - 3R


def test_short_mirror_fails_closed_on_bad_levels():
    base = {
        "reference_entry": "100", "reference_stop": "98", "risk_1r": "2",
        "tp1": "102", "tp2": "104", "tp3": "106",
    }
    with pytest.raises(ValueError):
        CoreV21EngineStrategy.mirror_short_levels(
            {**base, "risk_1r": "0"}, Decimal("100"))
    with pytest.raises(ValueError):
        CoreV21EngineStrategy.mirror_short_levels(
            {**base, "tp2": "102"}, Decimal("100"))  # unordered TPs


def test_stop_trigger_mirrors_by_mode():
    try:
        CoreV21EngineStrategy.SHORT_MODE = False
        assert CoreV21EngineStrategy._stop_triggered(Decimal("1"), Decimal("2"))
        assert not CoreV21EngineStrategy._stop_triggered(Decimal("3"), Decimal("2"))
        assert CoreV21EngineStrategy._stop_reason() == "CORE_V2_1_STOP_M15_CLOSE_BELOW_EMA21"
        CoreV21EngineStrategy.SHORT_MODE = True
        assert CoreV21EngineStrategy._stop_triggered(Decimal("3"), Decimal("2"))
        assert not CoreV21EngineStrategy._stop_triggered(Decimal("1"), Decimal("2"))
        assert CoreV21EngineStrategy._stop_reason() == "CORE_V2_1_SHORT_STOP_M15_CLOSE_ABOVE_EMA21"
    finally:
        CoreV21EngineStrategy.SHORT_MODE = False


def test_build_positions_short_sign_flips_pnl():
    from decimal import Decimal as D

    history = [
        {"id": "mock_1", "symbol": "A", "side": "SELL", "filled": 10.0,
         "price": 100.0, "time": "2026-01-01 00:15:00+00:00",
         "fee": {"cost": 0.05, "rate": 0.0005}, "info": {}},
        {"id": "mock_2", "symbol": "A", "side": "BUY", "filled": 10.0,
         "price": 90.0, "time": "2026-01-01 01:00:00+00:00",
         "fee": {"cost": 0.045, "rate": 0.0005}, "info": {"exit_reason": "TP3"}},
    ]
    positions, _ = build_positions(history, [], D("200"), "short")
    assert len(positions) == 1
    pos = positions[0]
    assert pos["direction"] == "short"
    assert pos["close_reason"] == "TP3"
    # Short wins when price falls: 10*100 - 10*90 = +100 gross.
    assert D(pos["gross_pnl"]) == D("100.0")
    assert D(pos["net_pnl"]) == D("100.0") - D("0.095")


def test_cross_check_short_matches_sell_entries():
    ledger = [
        {"type": "entry_fired", "symbol": "A",
         "fill_time": "2026-01-01T00:15:00+00:00",
         "event_type": "A_PLUS_LONG", "sequence": 1},
    ]
    history = [
        {"id": "mock_1", "symbol": "A", "side": "SELL", "filled": 10.0,
         "time": "2026-01-01 00:15:00+00:00"},
        {"id": "mock_2", "symbol": "A", "side": "BUY", "filled": 10.0,
         "time": "2026-01-01 01:00:00+00:00"},  # exit: must not count as entry
    ]
    check = cross_check_fills(history, ledger, "short")
    assert check["matched"] == 1
    assert check["buys_without_fired"] == []
    assert check["fired_without_buy_order_skips"] == []


def test_mock_exchange_fills_short_tp_limit():
    # Short TPs are resting BUY limits below entry: the shared wick fill
    # simulator must fill them when the candle trades through.
    exchange = MockExchange(initial_balance=100000.0, leverage=10)
    exchange.update_candle("A", 100.0, 100.5, 99.5, 100.0, "2026-01-01T00:00:00+00:00")
    entry = exchange.create_order(
        symbol="A", order_type="market", side="SELL", amount=Decimal("10"),
        price=Decimal("100"), params={},
    )
    assert entry is not None
    assert exchange.positions["A"] == Decimal("-10")
    tp = exchange.create_order(
        symbol="A", order_type="limit", side="BUY", amount=Decimal("10"),
        price=Decimal("98"), params={"reduceOnly": True, "exit_reason": "TP3"},
    )
    assert tp is not None and tp.get("status") == "open"
    executed = exchange.update_candle(
        "A", 99.0, 99.5, 97.0, 98.0, "2026-01-01T00:15:00+00:00")
    assert any(
        o.get("side") == "BUY" and o.get("info", {}).get("exit_reason") == "TP3"
        for o in executed
    )
    assert "A" not in exchange.positions  # fully closed by the TP fill


def test_short_partial_exit_pnl_uses_closing_amount():
    # Regression: partial short exits must book (entry - exit) * closed
    # amount, not scale by the full open position.
    from app.backtest.exchange.executor import execute_order

    exchange = MockExchange(initial_balance=100000.0, leverage=10,
                            taker_fee=0.0, maker_fee=0.0)
    exchange.update_candle("A", 100.0, 100.5, 99.5, 100.0, "2026-01-01T00:00:00+00:00")
    exchange.create_order(symbol="A", order_type="market", side="SELL",
                          amount=Decimal("10"), price=Decimal("100"), params={})
    part = execute_order(exchange, "A", "BUY", Decimal("4"), Decimal("90"),
                         "2026-01-01T00:15:00+00:00", "LIMIT", "TP1")
    assert part["pnl"] == pytest.approx((100 - 90) * 4)
    rest = execute_order(exchange, "A", "BUY", Decimal("6"), Decimal("95"),
                         "2026-01-01T00:30:00+00:00", "MARKET", "STOP")
    assert rest["pnl"] == pytest.approx((100 - 95) * 6)
    assert "A" not in exchange.positions
