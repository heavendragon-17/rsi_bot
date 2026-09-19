"""Offline, fail-closed M5 reference packets; no live configuration or providers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import structlog

from app.backtest import btc_research_phase1 as phase1
from research import btc_m5_horizon_diagnostic as parent_loader
from research import btc_m5_reference_backtest as signals_engine
from research import btc_m15_reference_backtest as engine
from research import btc_m15_reference_reporting as shared

logger = structlog.get_logger()

CODE_PATHS = (
    "research/btc_m5_reference_reporting.py", "tests/test_btc_m5_reference_reporting.py",
    "research/btc_m5_reference_backtest.py", "research/btc_m5_reference_verification.py",
    "research/btc_m5_horizon_diagnostic.py", "research/btc_m15_reference_backtest.py",
    "research/btc_m15_reference_reporting.py", "research/btc_m15_signal_diagnostic.py",
    "app/backtest/btc_research_phase1.py", "app/backtest/signal_replay.py",
    "app/backtest/signal_replay_preparation.py", "app/backtest/signal_replay_indicators.py",
    "app/backtest/signal_replay_data.py", "app/backtest/statistics/metrics.py",
    "app/trading/strategy/btc_rsi_cross_alert/m5_checker.py",
    "app/trading/strategy/btc_rsi_cross_alert/evaluator.py",
    "app/trading/strategy/btc_rsi_cross_alert/models.py",
    "app/trading/strategy/core_v2_1/indicators.py", "app/core/constants.py",
)


def daily_last(rows: list[dict]) -> list[dict]:
    """One LAST row per policy-day, including null terminal valuations."""
    latest = {}
    for row in rows:
        latest[(row["policy"], row["timestamp"][:10])] = row
    return [latest[key] for key in sorted(latest)]


def with_returns(item: dict) -> dict:
    """Normalize closed/hypothetical trade means by fixed notional, not equity."""
    result = dict(item)
    count = item.get("closed_trades", item.get("hypothetical_trades", item.get("entered_trades", 0)))
    for prefix, source in (("gross", "gross_pnl_usdt"), ("cost_adjusted", "net_pnl_usdt")):
        value = engine._finite(item.get(source))
        result[f"{prefix}_return_per_trade"] = value / count / engine.ENTRY_NOTIONAL_USDT if count and value is not None else None
    gross = result["gross_return_per_trade"]
    result["break_even_round_trip_bps_approx"] = gross * 10_000 if gross is not None else None
    return result


def verify_sources(expected: dict, actual: dict) -> bool:
    """Compare ALL native source files; a missing identity is never a match."""
    left, right = expected.get("files", {}), actual.get("files", {})
    if (not left or set(left) != set(right)
            or any(not left[tf].get("sha256") or left[tf]["sha256"] != right[tf].get("sha256") for tf in left)):
        raise ValueError("Native source hash mismatch; performance run refused")
    return True


def load_comparison(directory: Path, sources: dict) -> dict:
    """Accept corrected M15 v2/v3 only with matching frozen trade assumptions."""
    names = ("manifest.json", "protocol.json", "summary.json")
    manifest, protocol, summary = [json.loads((directory / name).read_text(encoding="utf-8")) for name in names]
    try:
        version = manifest["definition_version"]
        if (manifest["completion_status"] != "SUCCESS" or manifest["run_id"] != directory.name
                or version not in (engine.VERSION, engine.PREVIOUS_VERSION)
                or summary["definition_version"] != version or protocol["protocol_version"] != version):
            raise ValueError("M15 comparison identity/version mismatch")
        declared_hash = manifest.get("protocol_sha256")
        normalized = (directory / "protocol.json").read_bytes().replace(b"\r\n", b"\n")
        if (not isinstance(declared_hash, str) or len(declared_hash) != 64
                or hashlib.sha256(normalized).hexdigest() != declared_hash.lower()):
            raise ValueError("M15 comparison protocol hash mismatch; historical identity unverified")
        for section, keys in {
            "accounting": ("initial_equity_usdt", "fixed_entry_notional_usdt"),
            "costs": ("fee_rates_per_side", "slippage_rates_per_side", "headline_scenario"),
            "evaluation_window": ("start_utc", "end_utc", "entry_bounded_by_window_end", "exit_may_complete_past_window_end"),
            "execution": ("entry", "exit", "no_stop_loss_take_profit_trailing_or_alternative_horizon",
                          "one_active_position_per_policy", "pyramiding", "same_timestamp_ordering",
                          "while_open", "overlapping_exposure"),
            "funding": ("status",),
        }.items():
            if any(protocol[section][key] != engine.PROTOCOL[section][key] for key in keys):
                raise ValueError(f"M15 comparison frozen {section} mismatch")
        if (summary["funding_status"] != engine.FUNDING_STATUS
                or summary["headline_scenario"] != engine.PROTOCOL["costs"]["headline_scenario"]
                or any(summary["window"][key] != engine.PROTOCOL["evaluation_window"][key] for key in ("start_utc", "end_utc"))):
            raise ValueError("M15 comparison summary contract mismatch")
        # Exact numeric rates: scenario_key rounds to 5 decimals, so near-zero
        # impostors (e.g. 0.0000049) would alias the zero-cost key. Match each
        # row against the frozen grid with tight tolerance instead.
        expected_pairs = [(fee, slip) for fee in engine.FEE_RATES for slip in engine.SLIPPAGE_RATES]

        def _matches(pair: tuple[float, float], fee: float, slip: float) -> bool:
            return (math.isclose(pair[0], fee, rel_tol=1e-12, abs_tol=1e-15)
                    and math.isclose(pair[1], slip, rel_tol=1e-12, abs_tol=1e-15))

        rows = summary["cost_sensitivity"]
        if len(rows) != len(expected_pairs):
            raise ValueError("M15 comparison must contain all nine scenarios in both views")
        seen: list[tuple[float, float]] = []
        for row in rows:
            pair = next((p for p in expected_pairs
                         if _matches(p, row["fee_rate_per_side"], row["slippage_rate_per_side"]) and p not in seen), None)
            if pair is None:
                raise ValueError("M15 comparison scenario rate is not a frozen grid rate")
            seen.append(pair)
            for policy in engine.POLICIES:
                item = row[policy]
                if (not _matches(pair, item["fee_rate_per_side"], item["slippage_rate_per_side"])):
                    raise ValueError("M15 comparison policy rate diverges from its scenario rate")
        diagnostic = summary["full_opportunity_diagnostic"]
        if len(diagnostic) != len(expected_pairs):
            raise ValueError("M15 comparison must contain all nine scenarios in both views")
        for pair in expected_pairs:
            key = engine.scenario_key(*pair)
            if key not in diagnostic:
                raise ValueError("M15 comparison must contain all nine scenarios in both views")
            for policy in engine.POLICIES:
                item = diagnostic[key][policy]
                if not _matches(pair, item["fee_rate_per_side"], item["slippage_rate_per_side"]):
                    raise ValueError("M15 comparison diagnostic rate diverges from its scenario rate")
        headline_key = engine.scenario_key(summary["headline_scenario"]["fee_rate_per_side"],
                                           summary["headline_scenario"]["slippage_rate_per_side"])
        headline_row = next(row for row in rows
                            if engine.scenario_key(row["fee_rate_per_side"], row["slippage_rate_per_side"]) == headline_key)
        for policy in engine.POLICIES:
            if summary["headline"][policy] != headline_row[policy]:
                raise ValueError("M15 comparison headline diverges from its cost-grid scenario")
        # Legacy v2 is comparable only when its unresolved-valuation defect cannot apply.
        cohorts = [summary["headline"], *rows, *diagnostic.values()]
        if any(cohort[policy]["unresolved_trades"] != 0 for cohort in cohorts for policy in engine.POLICIES):
            raise ValueError("M15 comparison requires zero unresolved trades across all scenarios")
        verify_sources(sources, manifest["inputs"])
    except (KeyError, TypeError) as exc:
        raise ValueError("M15 comparison incomplete contract") from exc
    return {"summary": summary, "definition_version": version,
            "files_sha256": {name: phase1._hash_file(directory / name) for name in names},
            "source_hashes": {tf: row["sha256"] for tf, row in manifest["inputs"]["files"].items()}}


def verify_ledger(run: engine.PolicyRun, signals: list[datetime]) -> dict:
    """Fail closed on schedules, overlap, outcomes, fixed notional and wallet identity."""
    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(f"M5 ledger invariant failed: {reason}")

    require(all(b - a >= engine.SIGNAL_COOLDOWN for a, b in zip(signals, signals[1:], strict=False)), "cooldown")
    require(not any(row["kind"] == "ENTRY_DEFERRED" for row in run.actions), "no deferred entries")
    outcomes = [row for row in run.actions if row["kind"] in ("ENTRY_FILLED", "ENTRY_SKIPPED")]
    require(Counter(row["sequence"] for row in outcomes) == Counter(range(1, len(signals) + 1)), "every signal outcome")
    for row in outcomes:
        signal = signals[row["sequence"] - 1]
        require(pd.Timestamp(row["signal_close_at"]) == signal, "signal identity")
        require(pd.Timestamp(row["scheduled_at"]) == engine.scheduled_m5_open_after(signal), "scheduled entry")
        if row["kind"] == "ENTRY_FILLED":
            require(row["actual_at"] == row["scheduled_at"], "no delayed entry")
    trades = sorted([*run.executed, *run.unresolved], key=lambda row: row["entry_at"])
    require(len(trades) == sum(row["kind"] == "ENTRY_FILLED" for row in outcomes), "every fill has trade")
    previous_exit = None
    blocked = False
    for trade in trades:
        entry, exit_at = pd.Timestamp(trade["entry_at"]), pd.Timestamp(trade["exit_at"])
        require(not blocked and (previous_exit is None or entry >= previous_exit), "one active exposure")
        require(entry == engine.scheduled_m5_open_after(signals[trade["sequence"] - 1]), "exact entry boundary")
        require(exit_at - entry == engine.SCHEDULED_HOLD, "exact 60 minute exit")
        require(math.isclose(trade["entry_notional"], engine.ENTRY_NOTIONAL_USDT, abs_tol=1e-8), "fixed notional")
        blocked = trade["status"] != engine.TRADE_OK
        previous_exit = exit_at
    closed_net = sum(row["net_pnl"] for row in run.executed)
    unresolved_fees = sum(row["entry_fee_usdt"] for row in run.unresolved)
    require(math.isclose(run.final_cash, engine.INITIAL_EQUITY_USDT + closed_net - unresolved_fees,
                         rel_tol=1e-12, abs_tol=1e-7), "cash identity")
    for row in run.equity:
        require(-1e-8 <= row["reserved"] <= engine.ENTRY_NOTIONAL_USDT + 1e-8, "one reserved exposure")
        if row["equity"] is not None:
            require(row["unrealized_pnl"] is not None and math.isclose(row["equity"], row["cash"] + row["unrealized_pnl"], abs_tol=1e-7), "equity identity")
    return {"passed": True, "signals": len(signals), "trades": len(trades), "deferred_entries": 0}


def emitted_times(rows: pd.DataFrame) -> list:
    """Keep every emitted event regardless of forward-outcome completeness."""
    times = pd.to_datetime(rows.drop_duplicates("event_id").trigger_close_at, utc=True)
    return sorted(time.to_pydatetime() for time in times
                  if engine.WINDOW_START <= time <= engine.WINDOW_END)


def _fmt(value, pattern=",.2f") -> str:
    return "n/a" if value is None else format(value, pattern)


def render_report(summary: dict, manifest: dict) -> str:
    """Describe accounts and independent diagnostics without promoting either."""
    headline = summary["headline"]
    key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    full = summary["full_opportunity_diagnostic"][key]
    lines = [
        "# Frozen BTC M5 reference backtest", "",
        "**Historical development evidence. Alpha NOT_ASSESSED. No optimization or untouched holdout.**", "",
        "Funding: **EXCLUDED_BY_DESIGN**, not observed zero. Every cost-adjusted figure is "
        "**after assumed trading fees and slippage, before funding**; it is not fully net profit.", "",
        "## Frozen protocol", "",
        "- A: unchanged emitted M5 RSI alignment/state alerts, evaluated by `evaluate_m5_cross`; no fresh crossover is required.",
        "- B: only M5/H1/H4 native close > EMA21(price), with 21 contiguous price candles on each timeframe; no RSI conditions or readiness. B has its own independent one-hour cooldown.",
        "- Window: 2022-08-28 inclusive to 2026-08-28 exclusive (UTC); full earlier native history supplies indicator warmup.",
        "- Entry: next exact M5 boundary strictly after signal close; missing exact candles never jump forward. Exit: exact entry + 60 minutes at native open, even past the signal window when available.",
        "- One position per policy, exits before simultaneous entries, no deferred M5 entries, no stops/targets/new filters/parameter search. Missing exits leave unresolved exposure and block new entries.",
        f"- Capital {_fmt(engine.INITIAL_EQUITY_USDT)} USDT; fixed notional {_fmt(engine.ENTRY_NOTIONAL_USDT)} USDT. Headline fee {_fmt(engine.HEADLINE_FEE_RATE * 100, '.3f')}%/side and slippage {_fmt(engine.HEADLINE_SLIPPAGE_RATE * 100, '.3f')}%/side (approximately 12 bps round trip).",
        "- Candle-price proxies, not guaranteed executable fills. All nine frozen cost scenarios are reported, never selected for performance.", "",
        "## Capital-constrained accounts — headline costs", "",
        "| Metric | A emitted alerts | B price gates |", "|---|---:|---:|",
    ]
    metrics = [
        ("Signals", "signals", ",.0f"), ("Entered trades", "entered_trades", ",.0f"),
        ("Closed trades", "closed_trades", ",.0f"), ("Skipped entries", "skipped_entries", ",.0f"),
        ("Unresolved trades", "unresolved_trades", ",.0f"),
        ("Gross P&L, admitted trades (USDT)", "gross_pnl_usdt", ",.2f"),
        ("Slippage P&L (USDT)", "friction_pnl_usdt", ",.2f"),
        ("Fee P&L, closed trades (USDT)", "fee_pnl_usdt", ",.2f"),
        ("Cost-adjusted P&L, closed trades (USDT)", "net_pnl_usdt", ",.2f"),
        ("Final wallet cash (USDT)", "final_cash_usdt", ",.2f"),
        ("Final equity (USDT)", "final_equity_usdt", ",.2f"),
        ("Account return (%)", "total_return_pct", ".4f"),
        ("Gross return / closed trade", "gross_return_per_trade", ".5%"),
        ("Cost-adjusted return / closed trade", "cost_adjusted_return_per_trade", ".5%"),
        ("Approx. break-even round-trip cost (bps)", "break_even_round_trip_bps_approx", ".4f"),
        ("Max drawdown (% of peak marked equity)", "max_drawdown_pct", ".4f"),
        ("Time in market", "time_in_market_fraction", ".4%"),
        ("Average deployed notional (USDT)", "average_deployed_notional_usdt", ",.2f"),
        ("Turnover, entry + exit notionals (USDT)", "total_turnover_usdt", ",.2f"),
        ("Turnover / initial equity", "turnover_over_initial_equity", ",.2f"),
    ]
    for label, field, pattern in metrics:
        lines.append(f"| {label} | " + " | ".join(_fmt(headline[p].get(field), pattern) for p in engine.POLICIES) + " |")
    lines += ["", "Per-trade account averages are **conditional on affordability and timing**, not capital-independent. "
              "INSUFFICIENT_FREE_CASH means inability to afford the next fixed entry, **not bankruptcy**.", ""]
    for p in engine.POLICIES:
        item = headline[p]
        lines.append(f"- {p}: skips `{json.dumps(item['skip_reasons'], sort_keys=True)}`; account entry coverage "
                     f"`{item['coverage']['account_entries']}`; valuation `{item.get('valuation_status', 'COMPLETE')}`; "
                     f"final equity timestamp `{item.get('final_equity_at')}`; last valuation "
                     f"`{item.get('last_valuation_at')}` = {_fmt(item.get('last_valued_equity_usdt'))} USDT.")
    lines += ["", "Wallet cash is not an equity floor. Unavailable equity/unrealized P&L is null, not flat or zero; "
              "paid fees and known exposure are retained. COMPLETE means all reported mark/event rows are valued, "
              "not uninterrupted M5 coverage or continuous-price drawdown. Drawdown uses full-resolution available marks, "
              "not the compact daily CSV. Missing valuations make dependent metrics incomplete.", "",
              "## Full-opportunity diagnostics — NOT accounts", "",
              "Every signal is priced independently at fixed notional with the same execution/cost rules, no cash admission "
              "or overlap blocking. This is **not an account**, is not compounded into equity, and has no account drawdown.", "",
              "| Metric | A emitted alerts | B price gates |", "|---|---:|---:|"]
    for label, field, pattern in [
        ("Hypothetical trades", "hypothetical_trades", ",.0f"),
        ("Skipped or unresolved", "skipped_or_unresolved", ",.0f"),
        ("Gross P&L sum (USDT)", "gross_pnl_usdt", ",.2f"),
        ("Cost-adjusted P&L sum (USDT)", "net_pnl_usdt", ",.2f"),
        ("Gross return / hypothetical trade", "gross_return_per_trade", ".5%"),
        ("Cost-adjusted return / hypothetical trade", "cost_adjusted_return_per_trade", ".5%"),
        ("Approx. break-even round-trip cost (bps)", "break_even_round_trip_bps_approx", ".4f"),
    ]:
        lines.append(f"| {label} | " + " | ".join(_fmt(full[p].get(field), pattern) for p in engine.POLICIES) + " |")
    lines += ["", "Approximate break-even round-trip cost = mean gross return on fixed entry notional × 10,000. "
              "It ignores nonlinear fee/slippage interactions; a negative value cannot support any nonnegative cost. "
              "Diagnostic drawdown/equity are not defined; account values must not be substituted.", "",
              "## Entire frozen cost grid", "",
              "All P&L values below are USDT, after assumed fees/slippage and before funding.", "",
              "| Fee/side (%) | Slip/side (%) | A account P&L | B account P&L | A diagnostic P&L | B diagnostic P&L |",
              "|---:|---:|---:|---:|---:|---:|"]
    for row in summary["cost_sensitivity"]:
        diag = summary["full_opportunity_diagnostic"][engine.scenario_key(row["fee_rate_per_side"], row["slippage_rate_per_side"])]
        values = [row[p]["net_pnl_usdt"] for p in engine.POLICIES] + [diag[p]["net_pnl_usdt"] for p in engine.POLICIES]
        lines.append(f"| {row['fee_rate_per_side'] * 100:.3f} | {row['slippage_rate_per_side'] * 100:.3f} | " + " | ".join(_fmt(v) for v in values) + " |")
    lines += ["", "## M5 versus M15 — matching trading assumptions", "",
              "Same sources/window, capital, fixed notional, execution delay, holding time, fee/slippage grid and excluded funding. "
              "Signals differ by definition; M5 B uses price-only readiness, whereas historical M15 B used shared preparation. "
              "The comparison is historical, not an isolated causal estimate of timeframe or RSI value.", "",
              "| Timeframe/policy | Signals | Account trades | Account net (USDT) | Account max DD (%) | Full-opportunity gross/trade | Full-opportunity net (USDT) |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for label, result in (("M5", summary), ("M15", summary["m15_comparison"])):
        for p in engine.POLICIES:
            account = result["headline"][p]
            diagnostic = with_returns(result["full_opportunity_diagnostic"][key][p])
            lines.append(f"| {label} {p[0]} | {account['signals']:,} | {account['entered_trades']:,} | {_fmt(account['net_pnl_usdt'])} | "
                         f"{_fmt(account['max_drawdown_pct'], '.4f')} | {_fmt(diagnostic['gross_return_per_trade'], '.5%')} | {_fmt(diagnostic['net_pnl_usdt'])} |")
    lines += ["", "## Verification and reproduction", "",
              f"- Ordered M5 signal parity: `{manifest['signal_parity']}`.",
              f"- Price-only B scan: `{manifest['price_gate_scan']}`.",
              f"- Runtime ledger checks passed for all {len(manifest['ledger_invariants'])} policy/scenario combinations.",
              "- All native source hashes match the accepted parent and M15 comparison. Historical packets are read-only.",
              "- Full ledgers are local under `full/`; manifest records physical SHA-256 hashes and counts. Regenerate with the command below. "
              "Compact daily rows use the LAST row per day (including nulls); they are not used to calculate maximum drawdown.", "",
              "```text", manifest["command"], "```", ""]
    for name in manifest["charts"]:
        lines += [f"![{name}](charts/{name})", ""]
    return "\n".join(lines)


def run(baseline_run: Path, data_dir: Path, m15_run: Path, output_dir: Path, *, charts=True) -> Path:
    protocol = signals_engine.frozen_protocol()
    parent, _, parent_rows = parent_loader.load_parent(baseline_run)
    parent_hashes = parent_loader.parent_identity(baseline_run)
    inputs = phase1.validate_inputs(data_dir)
    verify_sources(parent["inputs"], inputs.source_report)
    comparison = load_comparison(m15_run, inputs.source_report)
    a = emitted_times(parent_rows)
    rebuilt, scan = signals_engine.reconstruct_alerts(inputs, engine.WINDOW_START, engine.WINDOW_END)
    parity = signals_engine.verify_parity(a, rebuilt)
    gates, gate_audit = signals_engine.price_gate_times(inputs, engine.WINDOW_START, engine.WINDOW_END)
    b = engine.apply_cooldown(gates, engine.SIGNAL_COOLDOWN)
    populations = dict(zip(engine.POLICIES, (a, b), strict=True))
    grid = engine.M5Grid.from_frame(inputs.frames["5m"])
    timestamp = datetime.now(UTC)
    packet = output_dir.resolve() / f"run_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{parent['inputs']['files']['5m']['sha256'][:8]}"
    (packet / "full").mkdir(parents=True, exist_ok=False)

    def write(name, text):
        (packet / name).write_text(text, encoding="utf-8", newline="\n")

    write("protocol.json", shared._json_text(protocol))
    write(".gitignore", "/full/\n")
    scenarios, costs, full, invariants = {}, [], {}, []
    fields = {"actions": engine.ACTION_FIELDS, "trades": engine.TRADE_FIELDS, "equity_curve": engine.EQUITY_FIELDS}
    row_counts = dict.fromkeys(fields, 0)
    daily = []
    with ExitStack() as stack:
        handles = {name: stack.enter_context((packet / "full" / f"{name}.csv").open("w", encoding="utf-8", newline="\n")) for name in fields}
        for name, columns in fields.items():
            handles[name].write(shared._csv_text(("scenario", *columns), []))
        for fee in engine.FEE_RATES:
            for slip in engine.SLIPPAGE_RATES:
                key = engine.scenario_key(fee, slip)
                scenarios[key], full[key] = {}, {}
                cost = {"fee_rate_per_side": fee, "slippage_rate_per_side": slip}
                for policy in engine.POLICIES:
                    outcome = engine.simulate_policy(policy, populations[policy], grid, fee_rate=fee, slippage_rate=slip)
                    engine.build_equity_curve(outcome, grid)
                    invariants.append({"scenario": key, "policy": policy, **verify_ledger(outcome, populations[policy])})
                    item = with_returns(engine.summarize_run(outcome, populations[policy]))
                    cost[policy] = item
                    scenarios[key][policy] = {"summary": item}
                    if (fee, slip) in ((0.0, 0.0), (engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)):
                        scenarios[key][policy]["run"] = outcome
                    if (fee, slip) == (engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE):
                        daily.extend({"scenario": key, **row} for row in daily_last(outcome.equity))
                    full[key][policy] = with_returns(engine.evaluate_full_opportunity(policy, populations[policy], grid, fee_rate=fee, slippage_rate=slip))
                    for name, rows in (("actions", outcome.actions), ("trades", [*outcome.trades, *outcome.unresolved]), ("equity_curve", outcome.equity)):
                        text = shared._csv_text(("scenario", *fields[name]), [{"scenario": key, **row} for row in rows])
                        handles[name].write(text.split("\n", 1)[1])
                        row_counts[name] += len(rows)
                costs.append(cost)
    signal_rows = [{"policy": p, "sequence": i, "signal_close_at": phase1._utc_iso(t)}
                   for p in engine.POLICIES for i, t in enumerate(populations[p], 1)]
    write("full/signals.csv", shared._csv_text(("policy", "sequence", "signal_close_at"), signal_rows))
    write("equity_daily.csv", shared._csv_text(("scenario", "policy", "timestamp", "state", "equity", "drawdown_pct"), daily))
    headline_key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    summary = {
        "definition_version": signals_engine.VERSION, "accounting_engine_version": engine.VERSION,
        "evidence_role": "HISTORICAL_DEVELOPMENT_EVIDENCE", "alpha_assessment": "NOT_ASSESSED",
        "funding_status": engine.FUNDING_STATUS, "cost_adjusted_label": engine.COST_ADJUSTED_LABEL,
        "window": protocol["evaluation_window"], "headline_scenario": protocol["costs"]["headline_scenario"],
        "headline": {p: scenarios[headline_key][p]["summary"] for p in engine.POLICIES},
        "cost_sensitivity": costs, "full_opportunity_diagnostic": full,
        "m15_comparison": {"headline": comparison["summary"]["headline"],
                           "full_opportunity_diagnostic": comparison["summary"]["full_opportunity_diagnostic"]},
    }
    write("summary.json", shared._json_text(summary))
    written_charts = shared.render_charts(scenarios, packet / "charts") if charts else []
    root = Path(__file__).resolve().parents[1]
    manifest = {
        "definition_version": signals_engine.VERSION, "completion_status": "SUCCESS", "run_id": packet.name,
        "generated_at_utc": phase1._utc_iso(timestamp), "protocol_sha256": phase1._hash_file(packet / "protocol.json"),
        "signal_parity": parity, "state_scan": scan, "price_gate_scan": gate_audit,
        "source_hash_parity": True, "inputs": inputs.source_report,
        "parent": {"run_id": parent["run_id"], "files_sha256": parent_hashes},
        "m15_comparison": {k: v for k, v in comparison.items() if k != "summary"},
        "code_sha256": {name: phase1._hash_file(root / name) for name in CODE_PATHS},
        "git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip(),
        "code_identity_note": "SHA-256 describes working-tree implementation bytes, including any uncommitted research changes; git revision alone is not code identity.",
        "environment": phase1._environment(), "ledger_invariants": invariants,
        "charts": written_charts,
        "command": f'python -m research.btc_m5_reference_reporting --baseline-run "{baseline_run}" --data-dir "{data_dir}" --m15-run "{m15_run}" --output-dir "{output_dir}"' + ("" if charts else " --no-charts"),
        "artifacts": {},
    }
    write("report.md", render_report(summary, manifest))
    artifact_names = ["protocol.json", "summary.json", "equity_daily.csv", "report.md", "full/signals.csv",
                      *[f"full/{name}.csv" for name in fields], *[f"charts/{name}" for name in written_charts]]
    for name in artifact_names:
        manifest["artifacts"][name] = {"sha256": phase1._hash_file(packet / name), "bytes": (packet / name).stat().st_size,
                                       "published": not name.startswith("full/")}
    manifest["full_ledger_row_counts"] = {**row_counts, "signals": len(signal_rows)}
    if parent_hashes != parent_loader.parent_identity(baseline_run):
        raise ValueError("Parent packet changed during M5 run")
    write("manifest.json", shared._json_text(manifest))
    logger.info("btc_m5_reference_complete", packet=str(packet), a_signals=len(a), b_signals=len(b))
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--m15-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("research/results/m5_reference_backtest_runs"))
    parser.add_argument("--no-charts", action="store_true")
    args = parser.parse_args(argv)
    run(args.baseline_run, args.data_dir, args.m15_run, args.output_dir, charts=not args.no_charts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
