"""V3 accounting regressions: unknown equity is never a wallet-cash floor."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from research import btc_m15_reference_backtest as engine
from research import btc_m15_reference_reporting as reporting


def moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def unresolved_run(monkeypatch, *, end="2026-01-01T01:30:00Z", final_close=80.0):
    monkeypatch.setattr(engine, "WINDOW_START", moment("2026-01-01T00:00:00Z"))
    monkeypatch.setattr(engine, "WINDOW_END", moment(end))
    frame = pd.DataFrame(
        {"open": 100.0, "close": 90.0},
        index=pd.date_range("2026-01-01", periods=30, freq="5min", tz="UTC"),
    )
    frame.loc["2026-01-01T01:25:00Z", "close"] = final_close
    # The exact exit open is missing, but the prior candle's close is available.
    frame = frame.drop(pd.Timestamp("2026-01-01T01:20:00Z"))
    grid = engine.M5Grid.from_frame(frame)
    signals = [moment("2026-01-01T00:15:00Z")]
    run = engine.simulate_policy(engine.POLICIES[0], signals, grid, fee_rate=0.0005, slippage_rate=0.0)
    return run, grid, signals


def test_unknown_equity_invalidates_dependent_drawdown_not_known_prefix():
    balances = [100.0, 90.0, None, 110.0]
    assert engine.research_drawdown_curve(balances, 100.0) == [0.0, 10.0, None, None]
    result = engine.calculate_research_portfolio_drawdown(
        [{"date": str(i), "balance": value} for i, value in enumerate(balances)], 100.0
    )
    assert [row["drawdown"] for row in result["drawdown_curve"]] == [0.0, 10.0, None, None]
    assert result["valuation_complete"] is False
    for key in ("max_drawdown_pct", "max_drawdown_value", "avg_drawdown_pct", "max_dd_duration"):
        assert result[key] is None


@pytest.mark.parametrize(
    "end, price, expected",
    [
        ("2026-01-01T01:30:00Z", 80.0, 9799.5),
        ("2026-01-01T01:29:00Z", 80.0, None),  # 01:30 mark is future
        ("2026-01-01T01:31:00Z", 80.0, None),  # 01:30 mark is stale
        ("2026-01-01T01:30:00Z", np.nan, None),
        ("2026-01-01T01:30:00Z", np.inf, None),
        ("2026-01-01T01:30:00Z", -1.0, None),
    ],
)
def test_unresolved_marks_are_timestamped_not_cash_floors(monkeypatch, end, price, expected):
    run, grid, _ = unresolved_run(monkeypatch, end=end, final_close=price)
    engine.build_equity_curve(run, grid)
    tail = run.equity[-1]
    assert tail["equity"] == expected
    assert tail["timestamp"] == end
    assert tail["state"] == "UNRESOLVED"
    assert tail["cash"] == 9999.5 == run.final_cash
    assert tail["quantity"] == 10.0
    assert tail["reserved"] == 1000.0
    assert tail["valuation_at"] == (end if expected is not None else None)
    assert tail["unrealized_pnl"] == (-200.0 if expected is not None else None)
    assert tail["mark_price"] == (80.0 if expected is not None else None)
    assert run.trades == []  # a valuation is not a replacement exit
    missing_exit = next(row for row in run.equity if row["timestamp"] == "2026-01-01T01:20:00Z")
    assert missing_exit["state"] == "UNRESOLVED"
    assert missing_exit["valuation_at"] == "2026-01-01T01:20:00Z"
    assert missing_exit["equity"] == 9899.5
    stamps = [row["timestamp"] for row in run.equity]
    assert stamps == sorted(stamps)


@pytest.mark.parametrize("end, expected", [("2026-01-01T01:30:00Z", 9799.5), ("2026-01-01T01:31:00Z", None)])
def test_summary_separates_final_cash_equity_last_valuation_and_paid_fees(monkeypatch, end, expected):
    run, grid, signals = unresolved_run(monkeypatch, end=end)
    engine.build_equity_curve(run, grid)
    item = engine.summarize_run(run, signals)
    assert item["final_equity_usdt"] == expected
    assert item["final_cash_usdt"] == 9999.5
    assert item["final_unrealized_pnl_usdt"] == (-200.0 if expected is not None else None)
    assert item["final_equity_at"] == end
    assert item["last_valuation_at"] == "2026-01-01T01:30:00Z"
    assert item["last_valued_equity_usdt"] == 9799.5
    assert item["final_valuation_complete"] is (expected is not None)
    assert item["valuation_complete"] is (expected is not None)
    assert item["total_return_pct"] == (pytest.approx(-2.005) if expected is not None else None)
    assert item["max_drawdown_pct"] == (pytest.approx(2.005) if expected is not None else None)
    assert item["unresolved_entry_fees_usdt"] == 0.5
    assert item["paid_fees_usdt"] == 0.5
    assert item["final_quantity"] == 10.0
    assert item["final_reserved_usdt"] == 1000.0
    assert item["final_state"] == "UNRESOLVED"
    assert item["entered_trades"] == 1
    assert item["closed_trades"] == 0
    assert item["net_pnl_usdt"] == 0.0  # closed-trade result, not wallet change
    assert item["total_turnover_usdt"] == 1000.0  # actual entry, no invented exit
    assert item["time_in_market_fraction"] > 0.0
    assert item["average_deployed_notional_usdt"] > 0.0
    assert item["coverage"]["account_entries"]["count"] == 1


def test_unbuilt_unresolved_summary_never_falls_back_to_wallet(monkeypatch):
    run, _, signals = unresolved_run(monkeypatch)
    item = engine.summarize_run(run, signals)
    assert item["final_equity_usdt"] is None
    assert item["total_return_pct"] is None
    assert item["max_drawdown_pct"] is None
    assert item["valuation_complete"] is False
    assert item["final_quantity"] == 10.0
    assert item["final_reserved_usdt"] == 1000.0


def reporting_inputs(monkeypatch):
    _, grid, signals = unresolved_run(monkeypatch, end="2026-01-01T01:31:00Z")
    scenarios = engine.run_cost_grid({policy: signals for policy in engine.POLICIES}, grid)
    key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    summary = {
        "headline_scenario": engine.PROTOCOL["costs"]["headline_scenario"],
        "headline": {policy: scenarios[key][policy]["summary"] for policy in engine.POLICIES},
        "cost_sensitivity": [
            {"fee_rate_per_side": fee, "slippage_rate_per_side": slip,
             **{policy: scenarios[engine.scenario_key(fee, slip)][policy]["summary"] for policy in engine.POLICIES}}
            for fee in engine.FEE_RATES for slip in engine.SLIPPAGE_RATES
        ],
    }
    manifest = {
        "protocol_sha256": "0" * 64, "gate_bars_before_cooldown": 1,
        "policy_a_reconstruction": {"cross_and_gate_bars_before_cooldown": 1, "matches": True,
                                    "emitted_count": 1, "reconstructed_count": 1},
        "source_hash_parity": True, "command": "offline test fixture",
    }
    return scenarios, summary, manifest


def test_report_labels_incomplete_equity_without_claiming_flat_or_known_performance(monkeypatch):
    _, summary, manifest = reporting_inputs(monkeypatch)
    report = reporting.render_report(summary, manifest)
    assert "| Final equity (USDT) | n/a | n/a |" in report
    assert "Last valued equity" in report
    assert "Last valuation timestamp" in report
    assert "INCOMPLETE" in report
    assert "Paid fees including unresolved entries" in report
    assert "there are no unresolved trades" not in report
    assert "fee-adjusted cash floor" not in report
    assert "Why both policies lose" not in report
    assert "Closed-trade" in report


def test_null_equity_survives_daily_csv_json_and_real_chart_rendering(monkeypatch, tmp_path):
    import csv
    import io
    import json

    scenarios, _, _ = reporting_inputs(monkeypatch)
    key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    rows = scenarios[key][engine.POLICIES[0]]["run"].equity
    assert reporting._daily_series(rows)[1][-1] is None
    csv_rows = list(csv.DictReader(io.StringIO(reporting._csv_text(engine.EQUITY_FIELDS, rows))))
    assert csv_rows[-1]["equity"] == ""
    assert csv_rows[-1]["valuation_at"] == ""
    assert json.loads(reporting._json_text(rows))[-1]["equity"] is None
    # A reporting consumer can supply incomplete cost-sensitivity metrics too.
    scenarios[key][engine.POLICIES[0]]["summary"]["net_pnl_usdt"] = None
    files = reporting.render_charts(scenarios, tmp_path)
    assert len(files) == 3
    for name in files:
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_report_cost_sensitivity_accepts_unavailable_numbers(monkeypatch):
    _, summary, manifest = reporting_inputs(monkeypatch)
    for scenario in summary["cost_sensitivity"]:
        for policy in engine.POLICIES:
            for key in ("net_pnl_usdt", "gross_pnl_usdt", "fee_pnl_usdt", "friction_pnl_usdt"):
                scenario[policy][key] = None
    assert "| n/a | n/a | n/a | n/a |" in reporting.render_report(summary, manifest)


def test_four_year_chart_date_labels_are_bounded(monkeypatch, tmp_path):
    from matplotlib.figure import Figure

    scenarios, _, _ = reporting_inputs(monkeypatch)
    days = pd.date_range("2022-08-28", "2026-08-27", freq="D", tz="UTC")
    key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    for value in scenarios[key].values():
        if "run" not in value:
            continue
        run = value["run"]
        row = run.equity[0]
        run.equity = [{**row, "timestamp": day.isoformat()} for day in days]
    counts = []
    save = Figure.savefig

    def capture(figure, path, **kwargs):
        if path.name in ("equity_gross_vs_cost.png", "drawdown.png"):
            counts.extend(len(axis.get_xticks()) for axis in figure.axes)
        return save(figure, path, **kwargs)

    monkeypatch.setattr(Figure, "savefig", capture)
    reporting.render_charts(scenarios, tmp_path)
    assert len(counts) == 4
    assert all(2 <= count <= 12 for count in counts)


def test_v3_explicitly_supersedes_v2_without_rewriting_evidence():
    assert engine.VERSION == "btc-m15-reference-backtest-v3"
    assert engine.PREVIOUS_VERSION == "btc-m15-reference-backtest-v2"
    supersedes = engine.PROTOCOL["supersedes"]
    assert supersedes["definition_version"] == engine.PREVIOUS_VERSION
    assert supersedes["preserved_unchanged"] is True
    assert "run_20260918T125747028014Z_991fd4d1" in supersedes["packet"]
    assert "cash is not an equity floor" in engine.PROTOCOL["accounting"]["unresolved"].lower()
    assert "Version 3" in engine.PROTOCOL["accounting"]["unresolved_correction_note"]


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -1.0])
def test_invalid_interim_mark_does_not_poison_known_final_equity(monkeypatch, invalid):
    run, grid, signals = unresolved_run(monkeypatch)
    # Resolve the same trade normally using a complete, explicitly priced grid.
    frame = pd.DataFrame(
        {"open": 100.0, "close": 100.0},
        index=pd.date_range("2026-01-01", periods=30, freq="5min", tz="UTC"),
    )
    frame.loc["2026-01-01T00:25:00Z", "close"] = invalid
    grid = engine.M5Grid.from_frame(frame)
    run = engine.simulate_policy(engine.POLICIES[0], signals, grid, fee_rate=0.0005, slippage_rate=0.0)
    engine.build_equity_curve(run, grid)
    invalid_row = next(row for row in run.equity if row["timestamp"] == "2026-01-01T00:30:00Z")
    assert invalid_row["equity"] is None
    assert invalid_row["unrealized_pnl"] is None
    assert invalid_row["valuation_at"] is None
    assert invalid_row["valuation_source"] is None
    item = engine.summarize_run(run, signals)
    assert item["final_equity_usdt"] == 9999.0
    assert item["final_valuation_complete"] is True
    assert item["valuation_complete"] is False
    assert item["max_drawdown_pct"] is None
