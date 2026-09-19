"""Synthetic offline packet tests; no historical data or provider prerequisites."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from research import btc_m15_reference_backtest as engine


def test_daily_last_preserves_null_and_does_not_keep_trade_events():
    rows = [{"policy": "A", "timestamp": stamp, "equity": value, "state": state}
            for stamp, value, state in [("2022-01-01T00:00:00Z", 10, "FLAT"),
                                        ("2022-01-01T01:00:00Z", 12, "OPEN"),
                                        ("2022-01-01T02:00:00Z", None, "UNRESOLVED")]]
    assert reporting().daily_last(rows) == [rows[-1]]


def test_trade_return_normalization_and_negative_breakeven():
    item = reporting().with_returns({"closed_trades": 2, "gross_pnl_usdt": -4,
                                     "net_pnl_usdt": -6})
    assert item["gross_return_per_trade"] == pytest.approx(-0.002)
    assert item["cost_adjusted_return_per_trade"] == pytest.approx(-0.003)
    assert item["break_even_round_trip_bps_approx"] == pytest.approx(-20)
    assert reporting().with_returns({"hypothetical_trades": 0})["gross_return_per_trade"] is None


def test_source_hash_check_includes_non_execution_timeframes():
    expected = {"files": {tf: {"sha256": tf} for tf in ("5m", "15m", "1h", "4h")}}
    assert reporting().verify_sources(expected, copy.deepcopy(expected)) is True
    actual = copy.deepcopy(expected)
    actual["files"]["15m"]["sha256"] = "changed"
    with pytest.raises(ValueError, match="source hash"):
        reporting().verify_sources(expected, actual)
    del actual["files"]["15m"]
    with pytest.raises(ValueError, match="source hash"):
        reporting().verify_sources(expected, actual)


def comparison_fixture(directory):
    """Small valid comparison contract, not fabricated historical performance."""
    directory.mkdir()
    protocol = copy.deepcopy(engine.PROTOCOL)
    sources = {"files": {tf: {"sha256": tf} for tf in ("5m", "15m", "1h", "4h")}}
    headline_fee = protocol["costs"]["headline_scenario"]["fee_rate_per_side"]
    headline_slip = protocol["costs"]["headline_scenario"]["slippage_rate_per_side"]
    scenarios = [{"fee_rate_per_side": fee, "slippage_rate_per_side": slip,
                  **{p: {"unresolved_trades": 0, "net_pnl_usdt": 0.0,
                         "fee_rate_per_side": fee, "slippage_rate_per_side": slip}
                     for p in engine.POLICIES}}
                 for fee in engine.FEE_RATES for slip in engine.SLIPPAGE_RATES]
    summary = {"definition_version": engine.VERSION, "window": protocol["evaluation_window"],
               "headline_scenario": protocol["costs"]["headline_scenario"],
               "funding_status": engine.FUNDING_STATUS, "cost_sensitivity": scenarios,
               "headline": {p: {"unresolved_trades": 0, "net_pnl_usdt": 0.0,
                               "fee_rate_per_side": headline_fee, "slippage_rate_per_side": headline_slip}
                            for p in engine.POLICIES},
               "full_opportunity_diagnostic": {
                   engine.scenario_key(s["fee_rate_per_side"], s["slippage_rate_per_side"]):
                   {p: {"unresolved_trades": 0, "net_pnl_usdt": 0.0,
                        "fee_rate_per_side": s["fee_rate_per_side"],
                        "slippage_rate_per_side": s["slippage_rate_per_side"]}
                     for p in engine.POLICIES} for s in scenarios}}
    manifest = {"run_id": directory.name, "completion_status": "SUCCESS", "inputs": sources,
                "definition_version": engine.VERSION}
    for name, value in (("protocol.json", protocol), ("manifest.json", manifest), ("summary.json", summary)):
        (directory / name).write_text(json.dumps(value), encoding="utf-8", newline="\n")
    import hashlib as _hashlib

    declared = _hashlib.sha256((directory / "protocol.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    manifest["protocol_sha256"] = declared
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
    return protocol, summary, manifest


@pytest.mark.parametrize("mutation", ["capital", "notional", "fees", "slippage", "window", "entry", "exit", "funding", "version", "unresolved", "scenario_missing", "source",
                                     "ordering", "while_open", "fee_rounding", "headline_fee", "headline_diverged",
                                     "protocol_hash_zero", "protocol_hash_missing"])
def test_comparison_rejects_mismatched_frozen_contract(mutation):
    with tempfile.TemporaryDirectory(prefix="m5-report-") as temporary:
        directory = Path(temporary) / "comparison"
        protocol, summary, manifest = comparison_fixture(directory)
        assert reporting().load_comparison(directory, manifest["inputs"])["summary"] == summary
        if mutation == "capital":
            protocol["accounting"]["initial_equity_usdt"] = 1
        elif mutation == "notional":
            protocol["accounting"]["fixed_entry_notional_usdt"] = 1
        elif mutation == "fees":
            protocol["costs"]["fee_rates_per_side"] = [0]
        elif mutation == "slippage":
            protocol["costs"]["slippage_rates_per_side"] = [0]
        elif mutation == "window":
            protocol["evaluation_window"]["end_utc"] = "2000-01-01"
        elif mutation == "entry":
            protocol["execution"]["entry"] = "same candle"
        elif mutation == "exit":
            protocol["execution"]["exit"] = "four hours"
        elif mutation == "funding":
            protocol["funding"]["status"] = "OBSERVED_ZERO"
        elif mutation == "version":
            manifest["definition_version"] = "btc-m15-reference-backtest-v1"
        elif mutation == "unresolved":
            summary["cost_sensitivity"][0][engine.POLICIES[0]]["unresolved_trades"] = 1
        elif mutation == "scenario_missing":
            summary["cost_sensitivity"].pop()
        elif mutation == "source":
            manifest["inputs"]["files"]["15m"]["sha256"] = "changed"
        elif mutation == "ordering":
            protocol["execution"]["same_timestamp_ordering"] = "entries before exits"
        elif mutation == "while_open":
            protocol["execution"]["while_open"] = "changed"
        elif mutation == "fee_rounding":
            # 0.0000049 formats into the zero-cost scenario_key but is not the frozen rate.
            summary["cost_sensitivity"][0]["fee_rate_per_side"] = 0.0000049
        elif mutation == "headline_fee":
            summary["headline"][engine.POLICIES[0]]["fee_rate_per_side"] = 0.004
        elif mutation == "headline_diverged":
            summary["headline"][engine.POLICIES[0]]["net_pnl_usdt"] = 12345.67
        elif mutation == "protocol_hash_zero":
            manifest["protocol_sha256"] = "0" * 64
        elif mutation == "protocol_hash_missing":
            del manifest["protocol_sha256"]
        expected = {"files": {tf: {"sha256": tf} for tf in ("5m", "15m", "1h", "4h")}}
        for name, value in (("protocol.json", protocol), ("manifest.json", manifest), ("summary.json", summary)):
            (directory / name).write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError, match="comparison|source hash|protocol hash"):
            reporting().load_comparison(directory, expected)

def synthetic_grid():
    times = pd.date_range(engine.WINDOW_START, periods=40, freq="5min")
    frame = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                          "volume": 1.0}, index=times)
    return frame, engine.M5Grid.from_frame(frame)


@pytest.mark.parametrize("mutation", [None, "entry", "exit", "cash", "missing_outcome", "deferred", "overlap"])
def test_runtime_ledger_invariants(mutation):
    _, grid = synthetic_grid()
    signals = [engine.WINDOW_START, engine.WINDOW_START + timedelta(hours=1)]
    run = engine.simulate_policy(engine.POLICIES[0], signals, grid, fee_rate=0.0005, slippage_rate=0.0001)
    engine.build_equity_curve(run, grid)
    if mutation == "entry":
        run.trades[0]["entry_at"] = signals[0].isoformat()
    elif mutation == "exit":
        run.trades[0]["exit_at"] = signals[0].isoformat()
    elif mutation == "cash":
        run.final_cash += 10
    elif mutation == "missing_outcome":
        run.actions = [a for a in run.actions if a["kind"] != "ENTRY_FILLED"]
    elif mutation == "deferred":
        run.actions.append({"kind": "ENTRY_DEFERRED"})
    elif mutation == "overlap":
        signals[1] = signals[0] + timedelta(minutes=5)
    if mutation:
        with pytest.raises(ValueError, match="invariant"):
            reporting().verify_ledger(run, signals)
    else:
        assert reporting().verify_ledger(run, signals)["passed"] is True


@pytest.fixture
def packet_inputs(monkeypatch):
    from app.backtest import btc_research_phase1 as phase1
    from research import btc_m5_reference_backtest as m5
    with tempfile.TemporaryDirectory(prefix="m5-packet-") as temporary:
        root = Path(temporary)
        comparison = root / "comparison"
        _, _, m15_manifest = comparison_fixture(comparison)
        frame, grid = synthetic_grid()
        times = [engine.WINDOW_START, engine.WINDOW_START + timedelta(hours=1)]
        populations = {policy: times for policy in engine.POLICIES}
        scenarios = engine.run_cost_grid(populations, grid)
        m15_summary = json.loads((comparison / "summary.json").read_text())
        headline_key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
        m15_summary["headline"] = {p: scenarios[headline_key][p]["summary"] for p in engine.POLICIES}
        for scenario in m15_summary["cost_sensitivity"]:
            key = engine.scenario_key(scenario["fee_rate_per_side"], scenario["slippage_rate_per_side"])
            scenario.update({p: scenarios[key][p]["summary"] for p in engine.POLICIES})
        m15_summary["full_opportunity_diagnostic"] = engine.run_full_opportunity_grid(populations, grid)
        (comparison / "summary.json").write_text(json.dumps(m15_summary), encoding="utf-8")
        parent = root / "baseline"
        parent.mkdir()
        sources = copy.deepcopy(m15_manifest["inputs"])
        sources["identity"] = {"venue_instrument": phase1.VENUE_INSTRUMENT}
        manifest = {"run_id": parent.name, "definition_version": phase1.DEFINITION_VERSION,
                    "completion_status": "SUCCESS", "inputs": sources}
        (parent / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (parent / "summary.json").write_text(json.dumps({"completion_status": "SUCCESS", "signal_counts": {"5m": 2}}))
        (parent / "report.md").write_text("Synthetic fixture only\n")
        rows = [{"timeframe": "5m", "event_id": f"e{i}", "sequence": i,
                 "trigger_open_at": phase1._utc_iso(t - timedelta(minutes=5)),
                 "trigger_close_at": phase1._utc_iso(t), "trigger_close_price": 100,
                 "horizon_minutes": horizon, "outcome_status": "MISSING_FUTURE_DATA"}
                for i, t in enumerate(times, 1) for horizon in (60, 240, 720, 1440)]
        pd.DataFrame(rows).to_csv(parent / "signals.csv", index=False)
        inputs = SimpleNamespace(frames={"5m": frame}, source_report=sources)
        monkeypatch.setattr(phase1, "validate_inputs", lambda _: inputs)
        monkeypatch.setattr(m5, "reconstruct_alerts", lambda *_: (times, {"candidate_bars": 40}))
        monkeypatch.setattr(m5, "price_gate_times", lambda *_: (times, {"price_gated_bars": 2}))
        yield root, parent, comparison, inputs


def test_offline_cli_writes_reproducible_full_ledgers_and_three_charts(packet_inputs):
    root, parent, comparison, _ = packet_inputs
    module = reporting()
    output = root / "output"
    args = ["--baseline-run", str(parent), "--data-dir", str(root), "--m15-run", str(comparison),
            "--output-dir", str(output)]
    assert module.main(args) == 0
    first = next(output.iterdir())
    assert module.main([*args, "--no-charts"]) == 0
    second = next(path for path in output.iterdir() if path != first)
    manifest = json.loads((first / "manifest.json").read_text())
    summary = json.loads((first / "summary.json").read_text())
    required = ["protocol.json", "summary.json", "equity_daily.csv", "full/actions.csv",
                "full/trades.csv", "full/equity_curve.csv", "full/signals.csv"]
    for name in required:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert b"\r\n" not in (first / name).read_bytes()
    for name, details in manifest["artifacts"].items():
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == details["sha256"]
        if details["published"]:
            assert details["bytes"] < 500_000
    assert len(list((first / "charts").glob("*.png"))) == 3
    assert "/full/" in (first / ".gitignore").read_text()
    assert len(summary["cost_sensitivity"]) == len(summary["full_opportunity_diagnostic"]) == 9
    assert len(manifest["ledger_invariants"]) == 18
    assert summary["headline"][engine.POLICIES[0]]["signals"] == 2
    assert summary["headline"][engine.POLICIES[0]]["gross_return_per_trade"] == 0
    assert "research/btc_m5_reference_verification.py" in manifest["code_sha256"]
    daily = pd.read_csv(first / "equity_daily.csv")
    assert not daily.assign(day=daily.timestamp.str[:10]).duplicated(["scenario", "policy", "day"]).any()
    trades = pd.read_csv(first / "full/trades.csv")
    assert trades.scenario.nunique() == 9
    report = (first / "report.md").read_text(encoding="utf-8")
    for label in ("M5", "M15", "EXCLUDED_BY_DESIGN", "before funding", "not bankruptcy", "conditional", "not an account", "break-even"):
        assert label in report
    assert "--data-dir" in manifest["command"] and "--m15-run" in manifest["command"]


def reporting():
    return importlib.import_module("research.btc_m5_reference_reporting")


def test_population_keeps_incomplete_outcomes_and_deduplicates_only_event_id():
    start = engine.WINDOW_START
    rows = pd.DataFrame([
        {"event_id": event, "trigger_close_at": moment.isoformat(), "outcome_status": status}
        for event, moment, status in [
            ("b", start + timedelta(hours=1), "MISSING_FUTURE_DATA"),
            ("a", start, "COMPLETE"), ("a", start, "COMPLETE"),
        ]
    ])
    assert reporting().emitted_times(rows) == [start, start + timedelta(hours=1)]
