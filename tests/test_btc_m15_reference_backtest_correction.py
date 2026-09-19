"""Independent regression tests for the v2 research correction.

Each expected number below is a hand-computed literal, not a повтор of the
implementation formula. The tests pin the corrected offline contract without
touching strategies, indicators, horizons, costs, sizing constants, cooldowns,
or production behavior.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.backtest import btc_research_phase1 as phase1
from research import btc_m15_reference_backtest as engine


def _m5_frame(
    *,
    start: str = "2026-01-01T00:00:00Z",
    periods: int = 200,
    opens: np.ndarray | None = None,
    drop_positions: tuple[int, ...] = (),
) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    values = np.full(periods, 100.0) if opens is None else np.asarray(opens, dtype=float)
    frame = pd.DataFrame({"open": values, "close": values}, index=index)
    if drop_positions:
        frame = frame.drop(frame.index[list(drop_positions)])
    return frame


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _set_open(frame: pd.DataFrame, position: int, value: float) -> None:
    frame.iloc[position, frame.columns.get_loc("open")] = value
    frame.iloc[position, frame.columns.get_loc("close")] = value


# ---------------------------------------------------------------------------
# A. Open-position equity
# ---------------------------------------------------------------------------
def test_constant_prices_zero_costs_equity_always_initial_and_drawdown_zero() -> None:
    """Flat 100, zero fees/slippage: equity stays 10,000 even while open."""

    grid = engine.M5Grid.from_frame(_m5_frame(periods=60))
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    engine.build_equity_curve(run, grid)
    # Hand literal: no price move and no costs, so every mark is 10,000.
    assert len(run.equity) > 2
    assert any(row["state"] == "OPEN" for row in run.equity)
    for row in run.equity:
        assert row["equity"] == pytest.approx(10000.0)
        assert row["drawdown_pct"] == pytest.approx(0.0)
        if row["state"] == "OPEN":
            # 10 USDT of quantity 10 at price 100: (100 - 100) * 10 = 0.
            assert row["unrealized_pnl"] == pytest.approx(0.0)
            assert row["cash"] == pytest.approx(10000.0)


def test_known_unrealized_gain_changes_equity_only_by_gain_minus_fees() -> None:
    """Entry 100, mark 110, quantity 10: equity is 10,000 - fee + 100."""

    frame = _m5_frame(periods=60)
    # Grid marks use native M5 closes: close 00:30 carries frame row 00:25.
    # Setting row 00:25 (position 5) to 110 makes the 00:30 mark read 110.
    _set_open(frame, 5, 110.0)
    grid = engine.M5Grid.from_frame(frame)
    fee_rate = 0.0005
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=fee_rate,
        slippage_rate=0.0,
    )
    engine.build_equity_curve(run, grid)
    # Hand literals: quantity = 1000 / 100 = 10; entry fee = 1000 * 0.0005 = 0.5.
    # Mark 110: unrealized = (110 - 100) * 10 = 100.
    # Wallet after fee = 10000 - 0.5 = 9999.5; equity = 9999.5 + 100 = 10099.5.
    marked = next(
        row for row in run.equity if row["state"] == "OPEN" and row["mark_price"] == pytest.approx(110.0)
    )
    assert marked["quantity"] == pytest.approx(10.0)
    assert marked["cash"] == pytest.approx(9999.5)
    assert marked["reserved"] == pytest.approx(1000.0)
    assert marked["unrealized_pnl"] == pytest.approx(100.0)
    assert marked["equity"] == pytest.approx(10099.5)


def test_known_unrealized_loss_with_fees() -> None:
    """Entry 100, mark 90: equity is 10,000 - 0.5 - 100 = 9899.5."""

    frame = _m5_frame(periods=60)
    _set_open(frame, 5, 90.0)
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0005,
        slippage_rate=0.0,
    )
    engine.build_equity_curve(run, grid)
    marked = next(
        row for row in run.equity if row["state"] == "OPEN" and row["mark_price"] == pytest.approx(90.0)
    )
    assert marked["unrealized_pnl"] == pytest.approx(-100.0)
    assert marked["equity"] == pytest.approx(9899.5)


# ---------------------------------------------------------------------------
# B. Drawdown and chronology
# ---------------------------------------------------------------------------
def test_new_equity_peak_resets_drawdown_to_zero() -> None:
    """Balances [100, 90, 110] must give drawdowns [0, 10, 0]."""

    assert engine.research_drawdown_curve([100.0, 90.0, 110.0], 100.0) == pytest.approx(
        [0.0, 10.0, 0.0]
    )
    result = engine.calculate_research_portfolio_drawdown(
        [
            {"date": "2026-01-01T00:00:00Z", "balance": 100.0},
            {"date": "2026-01-01T00:05:00Z", "balance": 90.0},
            {"date": "2026-01-01T00:10:00Z", "balance": 110.0},
        ],
        100.0,
    )
    assert [point["drawdown"] for point in result["drawdown_curve"]] == pytest.approx(
        [0.0, 10.0, 0.0]
    )
    assert result["max_drawdown_pct"] == pytest.approx(10.0)


def test_same_timestamp_observations_keep_individual_identities() -> None:
    """Two rows sharing one timestamp must not collapse through one dict key."""

    curve = [
        {"date": "2026-01-01T01:20:00Z", "balance": 10100.0},
        {"date": "2026-01-01T01:20:00Z", "balance": 9900.0},
    ]
    result = engine.calculate_research_portfolio_drawdown(curve, 10000.0)
    # Hand literals: first row is a new peak (10100 > 10000) so 0; second row is
    # (10100 - 9900) / 10100 * 100 = 1.980198...%.
    assert len(result["drawdown_curve"]) == 2
    assert result["drawdown_curve"][0]["drawdown"] == pytest.approx(0.0)
    assert result["drawdown_curve"][1]["drawdown"] == pytest.approx(1.9802, abs=1e-4)


def test_exit_beyond_window_keeps_timestamps_monotonic(monkeypatch) -> None:
    """An exit past WINDOW_END must not be followed by a WINDOW_END row behind it."""

    frame = _m5_frame(periods=60)
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    trade = run.trades[0]
    assert trade["exit_at"] == "2026-01-01T01:20:00Z"
    # Rebuild with a patched window end earlier than the exit.
    monkeypatch.setattr(engine, "WINDOW_END", _moment("2026-01-01T00:30:00Z"))
    engine.build_equity_curve(run, grid)
    stamps = [row["timestamp"] for row in run.equity]
    assert stamps == sorted(stamps)
    # The last row is the exit past the window end, not a WINDOW_END row behind it.
    assert stamps[-1] == trade["exit_at"]


def test_entry_marks_use_available_close_price() -> None:
    """OPEN marks use the native M5 close at that timestamp, not the entry open."""

    frame = _m5_frame(periods=60)
    # Entry open 00:20 stays 100; the 00:25 row carries the 00:30 close of 120.
    position_00_25 = 5
    frame.iloc[position_00_25, frame.columns.get_loc("open")] = 100.0
    frame.iloc[position_00_25, frame.columns.get_loc("close")] = 120.0
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    engine.build_equity_curve(run, grid)
    marked = next(
        row for row in run.equity if row["state"] == "OPEN" and row["mark_price"] == pytest.approx(120.0)
    )
    # Hand literal: close 120 is the available price, so unrealized is
    # (120 - 100) * 10 = 200 and equity is 10000 + 200 = 10200.
    assert marked["unrealized_pnl"] == pytest.approx(200.0)
    assert marked["equity"] == pytest.approx(10200.0)


# ---------------------------------------------------------------------------
# C. Execution edge cases
# ---------------------------------------------------------------------------
def test_internal_missing_entry_candle_with_later_candles_is_explicit_skip() -> None:
    """Scheduled 00:20 missing but 00:25 present: skip, never jump forward."""

    # Positions: 0->00:00, 1->00:05, 2->00:10, 3->00:15, 4->00:20 (dropped), 5->00:25.
    grid = engine.M5Grid.from_frame(_m5_frame(periods=12, drop_positions=(4,)))
    assert grid.open_index(_moment("2026-01-01T00:20:00Z")) is None
    assert grid.open_index(_moment("2026-01-01T00:25:00Z")) is not None
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert run.trades == []
    skipped = [row for row in run.actions if row["kind"] == "ENTRY_SKIPPED"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "MISSING_ENTRY_CANDLE"
    assert skipped[0]["scheduled_at"] == "2026-01-01T00:20:00Z"


def test_deferred_entry_uses_deferred_time_price_not_original_index() -> None:
    """Second signal deferred to 01:20 must fill at 200, not at 150."""

    frame = _m5_frame(periods=60)
    # 00:35 (position 7) is the second signal's own scheduled entry: 150.
    # 01:20 (position 16) is the deferred fill and first trade's exit: 200.
    _set_open(frame, 7, 150.0)
    _set_open(frame, 16, 200.0)
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z"), _moment("2026-01-01T00:30:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert [trade["entry_at"] for trade in run.trades] == [
        "2026-01-01T00:20:00Z",
        "2026-01-01T01:20:00Z",
    ]
    # Hand literals: deferred fill 200, quantity 1000/200 = 5.
    assert run.trades[1]["entry_fill_price"] == pytest.approx(200.0)
    assert run.trades[1]["quantity"] == pytest.approx(5.0)
    assert run.trades[1]["entry_open_price"] == pytest.approx(200.0)


def test_scheduled_boundary_is_arithmetic_not_data_dependent() -> None:
    """Signal at 00:17:30 schedules 00:20 even when 00:20 is the only check."""

    assert engine.scheduled_m5_open_after(_moment("2026-01-01T00:17:30Z")) == _moment(
        "2026-01-01T00:20:00Z"
    )
    assert engine.scheduled_m5_open_after(_moment("2026-01-01T00:15:00Z")) == _moment(
        "2026-01-01T00:20:00Z"
    )
    assert engine.scheduled_m5_open_after(_moment("2026-01-01T00:20:00Z")) == _moment(
        "2026-01-01T00:25:00Z"
    )


# ---------------------------------------------------------------------------
# A (unresolved) + missing-data handling
# ---------------------------------------------------------------------------
def test_unresolved_position_retains_fee_and_exposure_and_is_not_flat() -> None:
    """Missing exit: cash keeps the 0.5 fee deduction, reserved keeps 1,000."""

    grid = engine.M5Grid.from_frame(_m5_frame(periods=60, drop_positions=(16,)))
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0005,
        slippage_rate=0.0,
    )
    assert run.trades == []
    assert len(run.unresolved) == 1
    unresolved = run.unresolved[0]
    assert unresolved["status"] == engine.TRADE_UNRESOLVED_EXIT
    # Hand literals: quantity 10, entry fill 100, entry fee 0.5.
    assert unresolved["quantity"] == pytest.approx(10.0)
    assert unresolved["entry_fee_usdt"] == pytest.approx(0.5)
    engine.build_equity_curve(run, grid)
    tail = run.equity[-1]
    assert tail["state"] == "UNRESOLVED"
    assert tail["cash"] == pytest.approx(9999.5)
    assert tail["reserved"] == pytest.approx(1000.0)
    assert tail["unrealized_pnl"] is None
    # V3 supersedes the V2 cash-floor assertion: no exact end valuation exists.
    assert tail["equity"] is None
    assert run.final_cash == pytest.approx(9999.5)


def test_missing_and_evaluation_end_paths_stay_explicit(monkeypatch) -> None:
    """MISSING_ENTRY_CANDLE, ENTRY_AFTER_EVALUATION_END, and OPEN_AT_END are distinct."""

    grid = engine.M5Grid.from_frame(_m5_frame(periods=60))
    # Tail-missing entry.
    tail_grid = engine.M5Grid.from_frame(_m5_frame(periods=8))
    tail_run = engine.simulate_policy(
        "A_emitted_alerts", [_moment("2026-01-01T00:35:00Z")], tail_grid, fee_rate=0.0, slippage_rate=0.0
    )
    assert [row["reason"] for row in tail_run.actions if row["kind"] == "ENTRY_SKIPPED"] == [
        "MISSING_ENTRY_CANDLE"
    ]
    # Entry past the window end.
    monkeypatch.setattr(engine, "WINDOW_END", _moment("2026-01-01T00:14:00Z"))
    end_run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert [row["reason"] for row in end_run.actions if row["kind"] == "ENTRY_SKIPPED"] == [
        "ENTRY_AFTER_EVALUATION_END"
    ]


def test_open_at_evaluation_end_uses_distinct_status(monkeypatch) -> None:
    """Scheduled exit past the window end with no exit candle is OPEN_AT_EVALUATION_END."""

    monkeypatch.setattr(engine, "WINDOW_END", _moment("2026-01-01T00:25:00Z"))
    grid = engine.M5Grid.from_frame(_m5_frame(periods=60, drop_positions=(16,)))
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert [row["status"] for row in run.unresolved] == [engine.TRADE_OPEN_AT_END]


# ---------------------------------------------------------------------------
# D. Full-opportunity diagnostic is separate from the account
# ---------------------------------------------------------------------------
def test_full_opportunity_diagnostic_has_no_cash_filter_and_no_equity_curve() -> None:
    """With an unaffordable wallet the account skips but the diagnostic still prices."""

    frame = _m5_frame(periods=60)
    _set_open(frame, 16, 110.0)
    grid = engine.M5Grid.from_frame(frame)
    signals = [_moment("2026-01-01T00:15:00Z")]
    diagnostic = engine.evaluate_full_opportunity(
        "A_emitted_alerts", signals, grid, fee_rate=0.0005, slippage_rate=0.0002
    )
    # Hand literals from the frozen cost arithmetic:
    # entry fill 100.02, exit fill 109.978, quantity 1000/100.02 ~= 9.9980004,
    # gross = (110-100)*(1000/100) = 100, net ~= 98.51 (costs remove ~1.49).
    assert diagnostic["label"] == "FULL_OPPORTUNITY_SET_DIAGNOSTIC_NOT_AN_ACCOUNT"
    assert diagnostic["hypothetical_trades"] == 1
    assert diagnostic["gross_pnl_usdt"] == pytest.approx(100.0)
    assert diagnostic["net_pnl_usdt"] == pytest.approx(98.5103, abs=0.01)
    assert diagnostic["not_compounded_into_equity"] is True
    assert diagnostic["coverage"]["signals"]["count"] == 1
    assert diagnostic["coverage"]["hypothetical_entries"]["first_utc"] == "2026-01-01T00:20:00Z"
