"""Verification tests for the Core V2.1 reference simulation (research-only).

Hand-calculated scenarios over synthetic candles: partial TP thirds,
close-only stop triggering, same-bar ordering, overlap skipping, fee math,
open-at-end valuation, and deterministic reproduction.
"""

from __future__ import annotations

from decimal import Decimal as D
import json
from pathlib import Path

import pandas as pd
import pytest

from research import core_v2_1_reference_sim as sim


def _frame(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    """Rows are (open, high, low, close, ema21) on a 15-minute UTC grid."""

    index = pd.date_range("2026-07-01T00:15:00Z", periods=len(rows), freq="15min")
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "ema21": [r[4] for r in rows],
        },
        index=index,
    )


def _events(symbol: str, entries: list[tuple[int, str, str]]) -> pd.DataFrame:
    """Entries are (bar_number_of_signal_close, event_type, reference_entry).

    Reference stop = entry - 1, so 1R = 1 and TP1/2/3 = entry + 1/2/3.
    """

    base = pd.Timestamp("2026-07-01T00:15:00Z")
    rows = []
    for seq, (bar, etype, entry) in enumerate(entries, start=1):
        e = D(entry)
        rows.append(
            {
                "sequence": seq,
                "trigger_closed_at": str(base + pd.Timedelta(minutes=15 * (bar - 1))),
                "symbol": symbol,
                "venue": "BINANCE_FUTURES",
                "event_type": etype,
                "reference_entry": str(e),
                "reference_stop": str(e - 1),
                "risk_1r": "1",
                "tp1": str(e + 1),
                "tp2": str(e + 2),
                "tp3": str(e + 3),
            }
        )
    return pd.DataFrame(rows)


def _qty(ref_entry: D, ref_stop: D) -> D:
    return D("30")


def test_partial_tp_thirds_hand_calculated() -> None:
    # Signal close bar 1 -> entry at bar 2 open 100. TP1=101 on bar 3,
    # TP2=102 on bar 4, TP3=103 on bar 5. Slippage 0 for clean hand math.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),   # bar 1: signal close
            (100, 100.4, 99.8, 100.2, 99),  # bar 2: entry at open 100
            (100.2, 101.3, 100.1, 101.0, 99),  # bar 3: TP1 101 hit
            (101.0, 102.4, 100.8, 102.0, 99),  # bar 4: TP2 102 hit
            (102.0, 103.5, 101.8, 103.1, 99),  # bar 5: TP3 103 hit
        ]
    )
    positions, skipped = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "A_PLUS_LONG", "100")]),
        m15, _qty, D("0"), D("0"),
    )
    assert skipped == []
    (p,) = positions
    assert p.close_reason == "TP3"
    kinds = [f.kind for f in p.fills]
    assert kinds == ["ENTRY", "TP1", "TP2", "TP3"]
    assert p.fills[0].qty == D("30")
    assert all(f.qty == D("10") for f in p.fills[1:])
    assert [str(f.price) for f in p.fills[1:]] == ["101", "102", "103"]
    # gross = 10*(101+102+103) - 30*100 = 60
    assert p.gross_pnl == D("60")
    assert p.gross_pnl / (p.risk_1r * p.qty_total) == D("2")  # 2R average exit


def test_stop_is_close_only_not_wick() -> None:
    # Bar 3 wicks below EMA21 (low 97 < 99) but closes above -> no trigger.
    # Bar 4 closes below EMA21 -> exit at bar 5 open.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.4, 99.8, 100.2, 99),   # entry at open 100
            (100.2, 100.3, 97.0, 99.5, 99),  # wick below ema21, close 99.5 > 99
            (99.5, 99.6, 98.4, 98.5, 99),    # close 98.5 < 99 -> stop trigger
            (98.4, 98.5, 98.0, 98.2, 99),    # exit at open 98.4
        ]
    )
    positions, _ = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "PULLBACK_LONG", "100")]),
        m15, _qty, D("0"), D("0"),
    )
    (p,) = positions
    assert p.close_reason == "STOP_EMA21"
    assert p.family == "pullback_long"
    assert str(p.stop_close_time) == str(m15.index[3])
    exit_fill = p.fills[-1]
    assert exit_fill.kind == "STOP"
    assert str(exit_fill.time) == str(m15.index[4])
    assert exit_fill.price == D("98.4")
    # gross = 30*98.4 - 30*100 = -48
    assert p.gross_pnl == D("-48")

def test_same_bar_stop_beats_tp_and_entry_bar_has_no_tp() -> None:
    # Entry bar 2 also reaches TP1 (high 101.5) -> ignored (TP starts next
    # candle). Bar 3 reaches TP1 (high 101.2) AND closes below EMA21 ->
    # frozen ordering: stop wins, TP fill ignored; exit at bar 4 open.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 101.5, 99.8, 100.8, 99),   # entry 100; TP1 101 reached, ignored
            (100.8, 101.2, 98.0, 98.5, 99),  # high >= TP1 but close < ema21
            (98.4, 98.6, 98.0, 98.3, 99),    # exit at open 98.4
        ]
    )
    positions, _ = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "A_PLUS_LONG", "100")]),
        m15, _qty, D("0"), D("0"),
    )
    (p,) = positions
    assert [f.kind for f in p.fills] == ["ENTRY", "STOP"]
    assert p.close_reason == "STOP_EMA21"


def test_overlap_skipped_and_slippage_adverse() -> None:
    # Two signals back to back; the second arrives while the first position
    # is open -> OVERLAP_SKIPPED. Slippage 0.1% adverse on entry and exit.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.4, 99.8, 100.2, 99),   # entry #1 at open 100 -> 100.1
            (100.2, 100.3, 99.9, 100.1, 99), # signal #2 close (skipped)
            (100.1, 100.2, 98.0, 98.4, 99),  # stop trigger close
            (98.0, 98.1, 97.8, 97.9, 99),    # exit at open 98 -> 97.902
        ]
    )
    positions, skipped = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES",
        _events("ETHUSDT", [(1, "A_PLUS_LONG", "100"), (3, "PULLBACK_LONG", "100.1")]),
        m15, _qty, D("0.001"), D("0"),
    )
    assert [s["reason"] for s in skipped] == ["OVERLAP_SKIPPED"]
    (p,) = positions
    assert p.simulated_fill == D("100") * D("1.001")
    stop_fill = p.fills[-1]
    assert stop_fill.price == D("98") * D("0.999")


def test_fee_math_and_venue_rates() -> None:
    # Binance: taker 0.0005, maker 0.0002 at fee_scale 1.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.4, 99.8, 100.2, 99),
            (100.2, 101.3, 100.1, 101.0, 99),  # TP1
            (101.0, 102.4, 100.8, 102.0, 99),  # TP2
            (102.0, 103.5, 101.8, 103.1, 99),  # TP3
        ]
    )
    positions, _ = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "A_PLUS_LONG", "100")]),
        m15, _qty, D("0"), D("1"),
    )
    (p,) = positions
    # entry fee = 30*100*0.0005 = 1.5; TP fees = 10*price*0.0002 each
    expected_fees = D("1.5") + D("10") * (
        D("101") + D("102") + D("103")
    ) * D("0.0002")
    assert p.fees == expected_fees
    assert p.net_pnl == p.gross_pnl - expected_fees
    # Hyperliquid rates differ and scale with fee_scale.
    taker, maker = sim._fee_rates("HYPERLIQUID", D("2"))
    assert taker == D("0.0009") and maker == D("0.0003")


def test_open_at_end_valuation_and_zero_size_skip() -> None:
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.4, 99.8, 100.2, 99),   # entry 100
            (100.2, 100.6, 100.0, 100.5, 99),  # never stops, no TP reach
        ]
    )
    events = _events("ETHUSDT", [(1, "A_PLUS_LONG", "100"), (3, "A_PLUS_LONG", "100.5")])
    positions, skipped = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", events, m15, _qty, D("0"), D("0")
    )
    reasons = sorted(s["reason"] for s in skipped)
    assert "NO_FILL_CANDLE" in reasons  # signal on the final close
    (p,) = positions
    assert p.close_reason == "OPEN_AT_END"
    assert p.qty_remaining == D("30")
    mark_value = p.qty_remaining * (p.mark_price - p.simulated_fill)
    assert mark_value == D("30") * (D("100.5") - D("100"))  # 15

    def zero_qty(a: D, b: D) -> D:
        return D("0")

    positions, skipped = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "A_PLUS_LONG", "100")]),
        m15, zero_qty, D("0"), D("0"),
    )
    assert positions == [] and skipped[0]["reason"] == "ZERO_SIZE"

def test_stop_can_trigger_on_entry_candle_close() -> None:
    # Entry bar 2 closes below EMA21 -> stop exits at bar 3 open.
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.3, 98.0, 98.5, 99),    # entry at open 100, close < ema21
            (98.4, 98.5, 98.1, 98.2, 99),    # exit at open 98.4
        ]
    )
    positions, _ = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", _events("ETHUSDT", [(1, "A_PLUS_LONG", "100")]),
        m15, _qty, D("0"), D("0"),
    )
    (p,) = positions
    assert [f.kind for f in p.fills] == ["ENTRY", "STOP"]
    assert p.fills[-1].price == D("98.4")


def test_deterministic_reproduction() -> None:
    m15 = _frame(
        [
            (100, 100.5, 99.5, 100, 99),
            (100, 100.4, 99.8, 100.2, 99),
            (100.2, 101.3, 100.1, 101.0, 99),
            (101.0, 102.4, 100.8, 102.0, 99),
            (102.0, 103.5, 101.8, 103.1, 99),
            (103.0, 103.2, 98.0, 98.5, 99),
            (98.4, 98.6, 98.0, 98.3, 99),
        ]
    )
    events = _events("ETHUSDT", [(1, "A_PLUS_LONG", "100"), (6, "PULLBACK_LONG", "98.5")])
    first = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", events, m15, _qty, D("0.001"), D("1")
    )
    second = sim._simulate_symbol(
        "ETHUSDT", "BINANCE_FUTURES", events, m15, _qty, D("0.001"), D("1")
    )
    assert [sim._position_record(p) for p in first[0]] == [
        sim._position_record(p) for p in second[0]
    ]
    assert first[1] == second[1]


def test_protocol_freeze_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    digest = sim.freeze_protocol(path)
    frozen = path.read_text(encoding="utf-8")
    payload = __import__("json").loads(frozen)
    assert payload["protocol_sha256"] == digest
    assert payload["protocol"]["name"] == sim.PROTOCOL_NAME
    bases = {v.get("basis") for v in payload["protocol"].values() if isinstance(v, dict)}
    assert "ASSUMPTION_NOT_A_DECISION" in json.dumps(payload)