"""Focused tests for the frozen BTC M15 reference backtest engine.

Covers the required verification obligations: entry and exit timestamps,
independent cooldowns and position-overlap handling, same-timestamp exit/entry
ordering, capital constraints and cost arithmetic, funding status and
missing-data behaviour, future-data invariance, and hand-checked ledger
reconciliation against equity.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.backtest import btc_research_phase1 as phase1
from research import btc_m15_reference_backtest as engine
from research import btc_m15_reference_reporting as reporting


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


def _iso(values) -> list[str]:
    return [phase1._utc_iso(value) for value in values]


def _actions(run: engine.PolicyRun, kind: str) -> list[dict]:
    return [row for row in run.actions if row["kind"] == kind]


def _set_open(frame: pd.DataFrame, position: int, value: float) -> None:
    frame.iloc[position, frame.columns.get_loc("open")] = value
    frame.iloc[position, frame.columns.get_loc("close")] = value


# ---------------------------------------------------------------------------
# Entry and exit timestamps
# ---------------------------------------------------------------------------
def test_entry_is_the_first_m5_open_strictly_after_the_signal_close() -> None:
    frame = _m5_frame(opens=np.arange(200, dtype=float) + 100.0)
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(
        "A_emitted_alerts", [_moment("2026-01-01T00:15:00Z")], grid, fee_rate=0.0, slippage_rate=0.0
    )
    trade = run.trades[0]
    # The candle opening exactly at 00:15 is not "strictly after" the signal close.
    assert trade["entry_at"] == "2026-01-01T00:20:00Z"
    assert trade["exit_at"] == "2026-01-01T01:20:00Z"
    assert trade["hold_minutes"] == pytest.approx(60.0)
    assert trade["entry_open_price"] == pytest.approx(104.0)
    assert trade["exit_open_price"] == pytest.approx(116.0)
    assert trade["exit_open_price"] == pytest.approx(
        float(grid.open_prices[grid.open_index(_moment("2026-01-01T01:20:00Z"))])
    )
    assert trade["status"] == engine.TRADE_OK


def test_signal_inside_a_candle_uses_the_next_existing_open() -> None:
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:17:30Z")],
        engine.M5Grid.from_frame(_m5_frame()),
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert run.trades[0]["entry_at"] == "2026-01-01T00:20:00Z"
    assert run.trades[0]["exit_at"] == "2026-01-01T01:20:00Z"


# ---------------------------------------------------------------------------
# Independent cooldowns
# ---------------------------------------------------------------------------
def test_independent_one_hour_cooldown_rule() -> None:
    times = [
        _moment("2026-01-01T00:00:00Z"),
        _moment("2026-01-01T00:30:00Z"),
        _moment("2026-01-01T01:00:00Z"),
        _moment("2026-01-01T01:00:00Z"),
        _moment("2026-01-01T02:00:00Z"),
    ]
    assert _iso(engine.apply_cooldown(times, engine.SIGNAL_COOLDOWN)) == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T01:00:00Z",
        "2026-01-01T02:00:00Z",
    ]


def test_policy_b_applies_its_own_cooldown_which_the_descriptive_population_did_not() -> None:
    scan = pd.DataFrame(
        {
            "trigger_close_at": [
                "2026-01-01T00:15:00Z",
                "2026-01-01T00:30:00Z",
                "2026-01-01T00:45:00Z",
                "2026-01-01T02:00:00Z",
            ],
            "preparation_reason": [engine.PREPARATION_READY] * 4,
            "price_gates_pass": [True, True, False, True],
        }
    )
    # The descriptive gate_ready_no_cross population keeps every gated bar.
    assert len(engine.gate_bar_times(scan)) == 3
    assert _iso(engine.policy_b_signals(scan)) == ["2026-01-01T00:15:00Z", "2026-01-01T02:00:00Z"]


# ---------------------------------------------------------------------------
# Position overlap and same-timestamp ordering
# ---------------------------------------------------------------------------
def test_position_overlap_is_never_created_and_one_signal_may_be_deferred() -> None:
    grid = engine.M5Grid.from_frame(_m5_frame())
    signals = [
        _moment("2026-01-01T00:15:00Z"),  # entry 00:20, exit 01:20
        _moment("2026-01-01T00:30:00Z"),  # position open -> deferred to 01:20
        _moment("2026-01-01T00:45:00Z"),  # deferral slot already taken -> skipped
    ]
    run = engine.simulate_policy("A_emitted_alerts", signals, grid, fee_rate=0.0, slippage_rate=0.0)
    assert [trade["entry_at"] for trade in run.trades] == [
        "2026-01-01T00:20:00Z",
        "2026-01-01T01:20:00Z",
    ]
    assert [trade["exit_at"] for trade in run.trades] == [
        "2026-01-01T01:20:00Z",
        "2026-01-01T02:20:00Z",
    ]
    entries = [_moment(trade["entry_at"]) for trade in run.trades]
    exits = [_moment(trade["exit_at"]) for trade in run.trades]
    assert all(later >= earlier for earlier, later in zip(exits, entries[1:], strict=False))
    assert len(_actions(run, "ENTRY_DEFERRED")) == 1
    assert [row["reason"] for row in _actions(run, "ENTRY_SKIPPED")] == [
        "POSITION_OPEN_AND_DEFERRAL_SLOT_OCCUPIED"
    ]


def test_exits_are_processed_before_entries_at_the_same_timestamp() -> None:
    grid = engine.M5Grid.from_frame(_m5_frame())
    signals = [_moment("2026-01-01T00:15:00Z"), _moment("2026-01-01T00:30:00Z")]
    run = engine.simulate_policy("A_emitted_alerts", signals, grid, fee_rate=0.0, slippage_rate=0.0)
    assert len(run.trades) == 2
    assert run.trades[0]["exit_at"] == run.trades[1]["entry_at"] == "2026-01-01T01:20:00Z"
    kinds = [row["kind"] for row in run.actions]
    assert kinds.index("EXIT_FILLED") < kinds.index("ENTRY_FILLED", kinds.index("ENTRY_FILLED") + 1)


def test_signal_arriving_exactly_at_the_scheduled_exit_enters_immediately() -> None:
    # The signal's own scheduled entry (01:20) equals the open position's exit.
    grid = engine.M5Grid.from_frame(_m5_frame())
    signals = [_moment("2026-01-01T00:15:00Z"), _moment("2026-01-01T01:15:00Z")]
    run = engine.simulate_policy("A_emitted_alerts", signals, grid, fee_rate=0.0, slippage_rate=0.0)
    assert [trade["entry_at"] for trade in run.trades] == [
        "2026-01-01T00:20:00Z",
        "2026-01-01T01:20:00Z",
    ]
    assert _actions(run, "ENTRY_DEFERRED") == []


# ---------------------------------------------------------------------------
# Capital constraints and cost arithmetic
# ---------------------------------------------------------------------------
def test_insufficient_free_cash_skips_the_entry_explicitly(monkeypatch) -> None:
    monkeypatch.setattr(engine, "INITIAL_EQUITY_USDT", 500.0)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        engine.M5Grid.from_frame(_m5_frame()),
        fee_rate=engine.HEADLINE_FEE_RATE,
        slippage_rate=engine.HEADLINE_SLIPPAGE_RATE,
    )
    assert run.trades == []
    assert [row["reason"] for row in _actions(run, "ENTRY_SKIPPED")] == ["INSUFFICIENT_FREE_CASH"]


def test_cost_components_are_disjoint_and_match_a_hand_calculation() -> None:
    frame = _m5_frame()
    _set_open(frame, 16, 110.0)  # exact exit candle of the 00:20 entry
    grid = engine.M5Grid.from_frame(frame)
    fee_rate, slippage = 0.0005, 0.0002
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        grid,
        fee_rate=fee_rate,
        slippage_rate=slippage,
    )
    trade = run.trades[0]
    entry_open, exit_open = 100.0, 110.0
    entry_fill = entry_open * (1 + slippage)
    exit_fill = exit_open * (1 - slippage)
    quantity = engine.ENTRY_NOTIONAL_USDT / entry_fill
    entry_fee = quantity * entry_fill * fee_rate
    exit_fee = quantity * exit_fill * fee_rate
    gross = (exit_open - entry_open) * (engine.ENTRY_NOTIONAL_USDT / entry_open)
    friction = (exit_fill - entry_fill) * quantity - gross
    fees = -(entry_fee + exit_fee)

    assert trade["entry_fill_price"] == pytest.approx(entry_fill)
    assert trade["exit_fill_price"] == pytest.approx(exit_fill)
    assert trade["quantity"] == pytest.approx(quantity)
    assert trade["entry_notional"] == pytest.approx(engine.ENTRY_NOTIONAL_USDT)
    assert trade["gross_pnl"] == pytest.approx(gross)
    assert trade["friction_pnl"] == pytest.approx(friction)
    assert trade["fee_pnl"] == pytest.approx(fees)
    assert trade["net_pnl"] == pytest.approx(gross + friction + fees)
    assert trade["entry_fee_usdt"] + trade["exit_fee_usdt"] == pytest.approx(-fees)
    assert gross > 0 > friction > fees
    assert trade["net_return_pct"] == pytest.approx(trade["net_pnl"] / engine.ENTRY_NOTIONAL_USDT * 100)


def test_zero_cost_scenario_makes_net_equal_gross() -> None:
    frame = _m5_frame()
    _set_open(frame, 16, 104.0)
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        engine.M5Grid.from_frame(frame),
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    trade = run.trades[0]
    assert trade["friction_pnl"] == pytest.approx(0.0)
    assert trade["fee_pnl"] == pytest.approx(0.0)
    assert trade["net_pnl"] == pytest.approx(trade["gross_pnl"])
    assert trade["gross_pnl"] == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------
def test_missing_entry_candle_is_skipped_without_substitution() -> None:
    grid = engine.M5Grid.from_frame(_m5_frame(periods=8))  # last M5 open is 00:35
    run = engine.simulate_policy(
        "A_emitted_alerts", [_moment("2026-01-01T00:35:00Z")], grid, fee_rate=0.0, slippage_rate=0.0
    )
    assert run.trades == []
    assert [row["reason"] for row in _actions(run, "ENTRY_SKIPPED")] == ["MISSING_ENTRY_CANDLE"]


def test_entry_after_the_evaluation_end_is_skipped(monkeypatch) -> None:
    monkeypatch.setattr(engine, "WINDOW_END", _moment("2026-01-01T00:14:00Z"))
    run = engine.simulate_policy(
        "A_emitted_alerts",
        [_moment("2026-01-01T00:15:00Z")],
        engine.M5Grid.from_frame(_m5_frame()),
        fee_rate=0.0,
        slippage_rate=0.0,
    )
    assert run.trades == []
    assert [row["reason"] for row in _actions(run, "ENTRY_SKIPPED")] == ["ENTRY_AFTER_EVALUATION_END"]


def test_missing_exit_candle_leaves_the_trade_unresolved_and_blocks_new_exposure() -> None:
    grid = engine.M5Grid.from_frame(_m5_frame(drop_positions=(16,)))
    assert grid.open_index(_moment("2026-01-01T01:20:00Z")) is None
    signals = [_moment("2026-01-01T00:15:00Z"), _moment("2026-01-01T00:30:00Z")]
    run = engine.simulate_policy("A_emitted_alerts", signals, grid, fee_rate=0.0, slippage_rate=0.0)
    assert run.trades == []
    assert [row["status"] for row in run.unresolved] == [engine.TRADE_UNRESOLVED_EXIT]
    assert "exit_open_price" not in run.unresolved[0]
    reasons = {row["reason"] for row in run.actions if row["reason"]}
    assert engine.TRADE_UNRESOLVED_EXIT in reasons
    assert "DEFERRED_ENTRY_NOT_REALIZED" in reasons


def test_funding_is_excluded_by_design_and_the_protocol_is_frozen() -> None:
    assert engine.FUNDING_STATUS == "EXCLUDED_BY_DESIGN"
    assert engine.PROTOCOL["funding"]["status"] == "EXCLUDED_BY_DESIGN"
    assert engine.COST_ADJUSTED_LABEL == "After assumed trading fees and slippage, before funding."
    assert engine.PROTOCOL["funding"]["cost_adjusted_label"] == engine.COST_ADJUSTED_LABEL
    # Excluded funding must never be presented as observed zero funding.
    assert "observed zero funding" in engine.PROTOCOL["funding"]["not_zero"]
    assert "not fully net profit" in engine.PROTOCOL["funding"]["consequence"]
    assert "not adjusted" in engine.PROTOCOL["funding"]["entry_exit_unchanged"]
    assert engine.PROTOCOL["frozen_before_performance"] is True
    assert engine.PROTOCOL["costs"]["grid_size"] == len(engine.FEE_RATES) * len(engine.SLIPPAGE_RATES)
    assert engine.PROTOCOL["policies"]["difference_from_diagnostic_population"].startswith(
        "The M15 diagnostic's gate_ready_no_cross population"
    )


# ---------------------------------------------------------------------------
# Future-data invariance
# ---------------------------------------------------------------------------
def test_every_signal_produces_exactly_one_entry_outcome() -> None:
    grid = engine.M5Grid.from_frame(_m5_frame(periods=400))
    signals = [
        _moment("2026-01-01T00:15:00Z"),  # filled
        _moment("2026-01-01T00:30:00Z"),  # deferred to the open position's exit
        _moment("2026-01-01T00:45:00Z"),  # skipped: deferral slot occupied
        _moment("2026-01-01T02:15:00Z"),  # filled after the second position
    ]
    run = engine.simulate_policy("A_emitted_alerts", signals, grid, fee_rate=0.0, slippage_rate=0.0)
    filled = _actions(run, "ENTRY_FILLED")
    skipped = _actions(run, "ENTRY_SKIPPED")
    assert len(filled) + len(skipped) == len(signals)
    assert len(filled) == len(run.trades)
    assert [row["sequence"] for row in filled] == [trade["sequence"] for trade in run.trades]


def test_future_candles_cannot_change_earlier_trades() -> None:
    frame = _m5_frame(opens=np.linspace(100.0, 120.0, 200))
    signals = [_moment("2026-01-01T00:15:00Z")]
    full = engine.simulate_policy(
        "A_emitted_alerts",
        signals,
        engine.M5Grid.from_frame(frame),
        fee_rate=0.0005,
        slippage_rate=0.0001,
    )
    exit_at = _moment(full.trades[0]["exit_at"])
    # Keep every candle opening at or before the scheduled exit, and nothing later.
    cut = engine.simulate_policy(
        "A_emitted_alerts",
        signals,
        engine.M5Grid.from_frame(frame.loc[frame.index <= exit_at]),
        fee_rate=0.0005,
        slippage_rate=0.0001,
    )
    assert full.trades == cut.trades
    assert full.actions == cut.actions


# ---------------------------------------------------------------------------
# Ledger reconciliation and the cost grid
# ---------------------------------------------------------------------------
def test_ledger_reconciles_with_equity_and_respects_the_frozen_notional() -> None:
    frame = _m5_frame(periods=400)
    for position, value in ((16, 102.0), (40, 98.0), (52, 103.0), (76, 99.0), (88, 105.0)):
        _set_open(frame, position, value)
    grid = engine.M5Grid.from_frame(frame)
    signals = [
        _moment("2026-01-01T00:15:00Z"),
        _moment("2026-01-01T03:15:00Z"),
        _moment("2026-01-01T06:15:00Z"),
    ]
    run = engine.simulate_policy(
        "A_emitted_alerts",
        signals,
        grid,
        fee_rate=engine.HEADLINE_FEE_RATE,
        slippage_rate=engine.HEADLINE_SLIPPAGE_RATE,
    )
    engine.build_equity_curve(run, grid)
    assert len(run.trades) == 3
    assert [trade["entry_at"] for trade in run.trades] == [
        "2026-01-01T00:20:00Z",
        "2026-01-01T03:20:00Z",
        "2026-01-01T06:20:00Z",
    ]
    for trade in run.trades:
        assert trade["entry_notional"] == pytest.approx(engine.ENTRY_NOTIONAL_USDT)
        assert trade["hold_minutes"] == pytest.approx(60.0)
        assert trade["gross_pnl"] + trade["friction_pnl"] + trade["fee_pnl"] == pytest.approx(trade["net_pnl"])
    total_net = sum(trade["net_pnl"] for trade in run.trades)
    assert run.final_cash == pytest.approx(engine.INITIAL_EQUITY_USDT + total_net)
    assert run.equity[0]["equity"] == pytest.approx(engine.INITIAL_EQUITY_USDT)
    assert run.equity[-1]["equity"] == pytest.approx(run.final_cash)
    for row in run.equity:
        if row["state"] == "OPEN":
            assert row["equity"] == pytest.approx(row["cash"] + row["reserved"] + row["unrealized_pnl"])
            assert row["reserved"] == pytest.approx(engine.ENTRY_NOTIONAL_USDT)
        if row["state"] == "FLAT":
            assert row["reserved"] == 0.0
    peak = engine.INITIAL_EQUITY_USDT
    worst = 0.0
    for row in run.equity:
        peak = max(peak, row["equity"])
        worst = max(worst, (peak - row["equity"]) / peak * 100.0)
    assert max(row["drawdown_pct"] for row in run.equity) == pytest.approx(worst, abs=1e-4)
    assert reporting._daily_series(run.equity)[1][-1] == pytest.approx(run.final_cash)


def test_cost_grid_is_complete_gross_is_invariant_and_net_weakly_decreases() -> None:
    frame = _m5_frame(opens=np.linspace(100.0, 130.0, 200))
    signals = [_moment("2026-01-01T00:15:00Z")]
    scenarios = engine.run_cost_grid(
        {policy: signals for policy in engine.POLICIES}, engine.M5Grid.from_frame(frame)
    )
    assert len(scenarios) == len(engine.FEE_RATES) * len(engine.SLIPPAGE_RATES)
    for policy in engine.POLICIES:
        summary = {
            (fee, slip): scenarios[engine.scenario_key(fee, slip)][policy]["summary"]
            for fee in engine.FEE_RATES
            for slip in engine.SLIPPAGE_RATES
        }
        assert len({item["gross_pnl_usdt"] for item in summary.values()}) == 1
        assert len({item["entered_trades"] for item in summary.values()}) == 1
        zero, low_fee, high_fee = engine.FEE_RATES
        zero_slip, low_slip, high_slip = engine.SLIPPAGE_RATES
        assert summary[(high_fee, low_slip)]["net_pnl_usdt"] <= summary[(zero, low_slip)]["net_pnl_usdt"]
        assert summary[(low_fee, high_slip)]["net_pnl_usdt"] <= summary[(low_fee, zero_slip)]["net_pnl_usdt"]
        assert summary[(zero, zero_slip)]["net_pnl_usdt"] == pytest.approx(summary[(zero, zero_slip)]["gross_pnl_usdt"])
        assert summary[(high_fee, high_slip)]["net_pnl_usdt"] == min(
            item["net_pnl_usdt"] for item in summary.values()
        )
        assert summary[(zero, zero_slip)]["net_pnl_usdt"] == max(
            item["net_pnl_usdt"] for item in summary.values()
        )
