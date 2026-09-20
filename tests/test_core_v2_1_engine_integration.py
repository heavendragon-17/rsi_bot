"""Core V2.1 shared-engine integration tests (synthetic, through real components).

Every test drives the actual shared stack — BatchPortfolioEventSource,
PortfolioEngine, MockExchange, PortfolioManager/PositionSizer/SLTPManager —
with the thin CoreV21EngineStrategy adapter over small synthetic locked-shape
frames.  Nothing here reimplements fills, sizing, or accounting.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.core_v2_1.engine_adapter import CoreV21EngineStrategy
from app.backtest.core_v2_1.engine_backtest import build_positions
from app.backtest.core_v2_1.replay import ReplayFrames
from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
from app.backtest.engine.portfolio_engine import PortfolioEngine
from app.backtest.exchange.mock_exchange import MockExchange

SYMBOL = "ETHUSDT"
VENUE = "BINANCE_FUTURES"

# NOTE: the shared engine never calls analyze() for the first 50 candles
# (warm-up gate).  Signal rows therefore sit at k=52; on real data rows 0..48
# are NOT_READY warm-up under the H4 seed, so the gate changes nothing there.
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
    """Make row k an A_PLUS_LONG cross with passing filters."""
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


def _run(frames: ReplayFrames, config: dict = TEST_CONFIG):
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
        results = engine.run()
        strategy: CoreV21EngineStrategy = engine.strategy
        strategy.finalize({SYMBOL: frames.alt_m15[SYMBOL].index[-1].isoformat()})
        return engine, exchange, strategy, results
    finally:
        CoreV21EngineStrategy.unbind_frames()


def _signals(strategy) -> list[dict]:
    return [r for r in strategy.ledger if r.get("type") == "signal"]


# ----------------------------------------------------------------------
# Verification: section 3 invariants through the shared engine
# ----------------------------------------------------------------------


def test_flat_prices_create_no_equity():
    frames = _frames(_m15_frame())
    engine, exchange, strategy, results = _run(frames)
    assert exchange.trade_history == []
    assert float(exchange.balance) == 10000
    assert results["net_profit"] == 0.0
    assert _signals(strategy) == []


def test_next_open_entry_timestamps_and_prices():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    # Keep the aftermath quiet: no re-arm (ema9 stays above wma45), no stop.
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1]:, ["close", "ema21"]] = [101.5, 100.0]
    m15.loc[m15.index[k + 1]:, ["open", "high", "low"]] = [101.4, 101.6, 101.3]
    engine, exchange, strategy, results = _run(frames)

    fired = [r for r in strategy.ledger if r.get("type") == "entry_fired"]
    assert len(fired) == 1
    fill = fired[0]
    # Fill timestamp is the entry candle's close, exactly one candle after
    # the signal close; the fill price is that candle's OPEN, not its close.
    assert pd.Timestamp(fill["fill_time"]) - pd.Timestamp(fill["signal_close"]) == pd.Timedelta(
        minutes=15
    )
    entry_candle = m15.loc[fill["fill_time"]]
    assert Decimal(fill["entry_open"]) == Decimal(str(entry_candle["open"]))
    assert Decimal(fill["entry_open"]) != Decimal(str(entry_candle["close"]))

    opening = [t for t in exchange.trade_history if t["side"] == "BUY"][0]
    assert pd.Timestamp(opening["time"]).isoformat() == fill["fill_time"]
    # Shared MockExchange applies adverse slippage on the market fill.
    assert Decimal(str(opening["price"])) == pytest.approx(
        Decimal(fill["entry_open"]) * Decimal("1.001"), rel=Decimal("1e-9")
    )


def test_partial_exits_conserve_quantity_and_charge_fees_once():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    # TP1 = 101.0 + 0.7 = 101.7. Touch it two candles after entry, then stop.
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1], ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.6, 101.3, 101.5, 100.0]
    m15.loc[m15.index[k + 2], ["open", "high", "low", "close", "ema21"]] = [
        101.5, 101.9, 101.4, 101.6, 100.0]
    m15.loc[m15.index[k + 3]:, ["open", "high", "low", "close", "ema21"]] = [
        101.0, 101.1, 98.9, 99.0, 100.0]
    engine, exchange, strategy, results = _run(frames)

    history = exchange.trade_history
    entry = next(t for t in history if t["side"] == "BUY")
    exits = [t for t in history if t["side"] == "SELL"]
    entry_qty = Decimal(str(entry["filled"]))
    # Quantity is conserved across partial exits (trade_history serializes
    # floats, so conservation holds to float precision; the engine's internal
    # Decimal accounting closed the position fully with no residue).
    assert float(sum(Decimal(str(t["filled"])) for t in exits)) == pytest.approx(
        float(entry_qty), rel=1e-9
    )
    assert exchange.positions == {}
    tp1 = next(t for t in exits if t["info"]["exit_reason"] == "TP1")
    assert float(Decimal(str(tp1["filled"]))) == pytest.approx(float(entry_qty / 3), rel=1e-9)
    # Each fill carries exactly one fee application at the right rate.
    assert float(Decimal(str(tp1["fee"]["cost"]))) == pytest.approx(
        float(Decimal(str(tp1["filled"])) * Decimal(str(tp1["price"])) * Decimal("0.0002")),
        rel=1e-9,
    )
    assert float(Decimal(str(entry["fee"]["cost"]))) == pytest.approx(
        float(Decimal(str(entry["filled"])) * Decimal(str(entry["price"])) * Decimal("0.0005")),
        rel=1e-9,
    )
    assert len(history) == len(exits) + 1  # one fee record per fill, none duplicated

    positions, _ = build_positions(history, strategy.ledger, Decimal("100"))
    assert len(positions) == 1
    assert positions[0]["close_reason"].startswith("CORE_V2_1_STOP")


def test_tp_fills_survive_later_close_stop():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1], ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.6, 101.3, 101.5, 100.0]
    m15.loc[m15.index[k + 2], ["open", "high", "low", "close", "ema21"]] = [
        101.5, 101.9, 101.4, 101.6, 100.0]
    m15.loc[m15.index[k + 3]:, ["open", "high", "low", "close", "ema21"]] = [
        101.0, 101.1, 98.9, 99.0, 100.0]
    engine, exchange, strategy, results = _run(frames)

    history = exchange.trade_history
    tp1 = next(t for t in history if t["info"].get("exit_reason") == "TP1")
    stop = next(t for t in history if (t["info"].get("exit_reason") or "").startswith("CORE_V2_1"))
    entry = next(t for t in history if t["side"] == "BUY")
    # The earlier TP1 fill is NOT erased by the later close-based stop; the
    # stop exits only the remainder (float-serialized history: to precision).
    assert float(Decimal(str(stop["filled"]))) == pytest.approx(
        float(Decimal(str(entry["filled"])) - Decimal(str(tp1["filled"]))), rel=1e-9
    )
    assert Decimal(str(tp1["price"])) == Decimal("101.7")


def test_reference_fill_sizing_and_r_stay_distinct_and_consistent():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    m15.loc[m15.index[k + 1]:, ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    m15.loc[m15.index[k + 1]:, ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.6, 101.3, 101.5, 100.0]
    m15.loc[m15.index[k + 2]:, ["open", "high", "low", "close", "ema21"]] = [
        101.0, 101.1, 98.9, 99.0, 100.0]
    engine, exchange, strategy, results = _run(frames)

    fired = [r for r in strategy.ledger if r.get("type") == "entry_fired"][0]
    history = exchange.trade_history
    entry = next(t for t in history if t["side"] == "BUY")
    # Reference entry (signal close) vs simulated fill (next open + slippage).
    assert Decimal(fired["reference_entry"]) == Decimal("101.0")
    assert Decimal(str(entry["price"])) != Decimal(fired["reference_entry"])
    # Sizing basis recorded separately from the fill.
    assert Decimal(fired["reference_stop"]) == Decimal("100.3")

    risk_amount = Decimal("100")  # 10000 * 0.01
    positions, _ = build_positions(history, strategy.ledger, risk_amount)
    pos = positions[0]
    gross = sum(
        (Decimal(str(f["qty"])) * Decimal(str(f["price"])) for f in pos["fills"]), Decimal("0")
    ) - Decimal(pos["entry_qty"]) * Decimal(pos["entry_fill"])
    assert Decimal(pos["gross_pnl"]) == gross
    assert Decimal(pos["gross_realized_r"]) == gross / risk_amount
    net = gross - Decimal(pos["fees_recorded"])
    assert Decimal(pos["net_pnl"]) == net
    assert Decimal(pos["net_realized_r"]) == net / risk_amount


def test_overlap_stays_explicit_and_position_survives_to_eod():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    # Keep the position alive (no stop, no TP touch: highs below TP1=101.7).
    m15.loc[m15.index[k + 1]:, ["open", "high", "low", "close", "ema21"]] = [
        101.4, 101.5, 101.3, 101.5, 100.0]
    # Force a second entry signal while the first position is open: re-arm
    # then cross again at k+5.  Row k+2 ema21 keeps the EMA21 slope filter
    # passing at the second cross.
    m15.loc[m15.index[k + 2], ["rsi_ema9", "rsi_wma45"]] = [44.0, 45.0]
    m15.loc[m15.index[k + 2], "ema21"] = 99.5
    m15.loc[m15.index[k + 3], ["rsi_ema9", "rsi_wma45"]] = [44.0, 45.0]
    m15.loc[m15.index[k + 4], ["rsi_ema9", "rsi_wma45"]] = [44.0, 45.0]
    m15.loc[m15.index[k + 5], ["rsi_ema9", "rsi_wma45"]] = [46.0, 45.0]
    for j in (k + 2, k + 3, k + 4, k + 5):
        m15.loc[m15.index[j], ["rsi21"]] = [60.0]
        m15.loc[m15.index[j], ["close"]] = [101.5]
    _bullish_context(frames, k + 5)
    engine, exchange, strategy, results = _run(frames)

    kinds = [r.get("type") for r in strategy.ledger]
    assert "overlap_skipped" in kinds
    entries = [t for t in exchange.trade_history if t["side"] == "BUY"]
    assert len(entries) == 1  # the overlapping signal never opened
    # Position still open at end: the engine EOD-closes it with an explicit label.
    reasons = {t["info"].get("exit_reason") for t in exchange.trade_history}
    assert "EOD" in reasons


def test_signal_on_last_candle_is_no_fill_candle():
    m15 = _m15_frame()
    frames = _frames(m15)
    last = N - 1
    m15.loc[m15.index[last - 3], "ema21"] = 99.5
    m15.loc[m15.index[last], ["open", "high", "low", "close"]] = [100.9, 101.2, 100.8, 101.0]
    m15.loc[m15.index[last], ["ema21", "ema200", "atr14"]] = [100.0, 90.0, 2.0]
    m15.loc[m15.index[last], ["rsi21", "rsi_ema9", "rsi_wma45"]] = [60.0, 46.0, 45.0]
    _bullish_context(frames, last)
    engine, exchange, strategy, results = _run(frames)

    kinds = [r.get("type") for r in strategy.ledger]
    assert "no_fill_candle" in kinds
    assert [t for t in exchange.trade_history if t["side"] == "BUY"] == []


def test_gap_after_state_start_fails_closed():
    m15 = _m15_frame()
    frames = _frames(m15)
    k = 52
    _arm_signal(m15, frames.btc_h1, k)
    _bullish_context(frames, k)
    # Corrupt one post-signal indicator: the corrupt row itself is NOT_READY
    # (state unchanged, counted explicitly); the next row cannot build its
    # required previous snapshot, so evaluation fails closed with an explicit
    # error instead of simulating on corrupt inputs.
    m15.loc[m15.index[k + 2], "rsi21"] = float("nan")
    with pytest.raises(ValueError, match="evaluation input invalid"):
        _run(frames)


def _fill_row(ts, oid, side, amount, price, reason):
    return {
        "id": oid, "symbol": "SYM", "side": side, "type": "market",
        "price": price, "amount": amount, "filled": amount,
        "fee": {"cost": amount * price * 0.0005, "rate": 0.0005},
        "info": {"exit_reason": reason}, "time": ts,
    }


def test_build_positions_handles_interleaved_symbols():
    from app.backtest.core_v2_1.engine_backtest import build_positions

    history = [
        dict(_fill_row("2026-07-15 03:00:00+00:00", "mock_order_1", "BUY", 30.0, 100.0, ""), symbol="A"),
        dict(_fill_row("2026-07-15 03:00:00+00:00", "mock_order_2", "BUY", 10.0, 50.0, ""), symbol="B"),
        # Same-candle TP3 close (id 9) before a new entry (id 10): numeric,
        # not lexicographic, id order keeps the sequence intact.
        dict(_fill_row("2026-07-15 04:00:00+00:00", "mock_order_9", "SELL", 30.0, 101.0, "TP3"), symbol="A"),
        dict(_fill_row("2026-07-15 04:00:00+00:00", "mock_order_10", "BUY", 20.0, 102.0, ""), symbol="A"),
        dict(_fill_row("2026-07-15 05:00:00+00:00", "mock_order_11", "SELL", 10.0, 51.0, "TP1"), symbol="B"),
    ]
    positions, _ = build_positions(history, [], Decimal("100"))
    by_symbol = {}
    for pos in positions:
        by_symbol.setdefault(pos["symbol"], []).append(pos)
    assert [p["close_reason"] for p in by_symbol["A"]] == ["TP3", "UNCLOSED_ENGINE"]
    assert len(by_symbol["B"]) == 1  # TP1 exit closed the whole 10.0 excerpt
    assert by_symbol["B"][0]["close_reason"] == "TP1"
