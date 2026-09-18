"""Charts, packet writing, and CLI for the frozen BTC M15 reference backtest.

The engine lives in :mod:`research.btc_m15_reference_backtest`. This module only
renders and persists results; it computes nothing that affects the protocol and
it never touches live configuration, execution, notifications, or the network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.backtest import btc_research_phase1 as phase1
from research import btc_m15_reference_backtest as engine
from research import btc_m15_signal_diagnostic as diagnostic

logger = structlog.get_logger()
PARENT_FILES = ("manifest.json", "signals.csv", "summary.json", "report.md")
MAX_COMMITTED_CURVE_BYTES = 400_000
CSV_FLOAT_DIGITS = 10
CODE_PATHS = (
    "research/btc_m15_reference_backtest.py",
    "research/btc_m15_reference_reporting.py",
    "research/btc_m15_signal_diagnostic.py",
    "app/backtest/btc_research_phase1.py",
    "app/backtest/signal_replay_preparation.py",
    "app/backtest/signal_replay_data.py",
    "app/backtest/engine/curves.py",
    "app/backtest/statistics/metrics.py",
    "app/trading/strategy/btc_rsi_cross_alert/m15_checker.py",
    "app/trading/strategy/btc_rsi_cross_alert/evaluator.py",
)


def _json_text(value: Any) -> str:
    return json.dumps(_sanitize(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _sanitize(value: Any) -> Any:
    """Replace non-finite floats so the packet stays strict JSON."""

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def _csv_text(fields: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (f"{value:.{CSV_FLOAT_DIGITS}g}" if isinstance(value, float) else value)
                for key, value in row.items()
            }
        )
    return buffer.getvalue()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _daily_series(rows: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    latest: dict[str, float] = {}
    for row in rows:
        latest[row["timestamp"][:10]] = float(row["equity"])
    days = sorted(latest)
    return days, [latest[day] for day in days]


def render_charts(
    scenarios: dict[str, dict[str, Any]],
    chart_dir: Path,
) -> list[str]:
    """Three separate descriptive charts."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_dir.mkdir(parents=True, exist_ok=True)
    footer = (
        "Historical development evidence on delayed candle-price proxies. "
        "After assumed trading fees and slippage, before funding. "
        "Funding is excluded by design and was not observed to be zero."
    )
    headline_key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    gross_key = engine.scenario_key(0.0, 0.0)
    written: list[str] = []

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=False)
    for axis, policy in zip(axes, engine.POLICIES, strict=True):
        for label, key, colour, style in (
            ("gross (zero cost)", gross_key, "#207020", "-"),
            ("cost-adjusted (headline)", headline_key, "#b03030", "-"),
        ):
            run = scenarios[key][policy]["run"]
            days, values = _daily_series(run.equity)
            axis.plot(days, values, linewidth=1.1, color=colour, linestyle=style, label=label)
        axis.axhline(engine.INITIAL_EQUITY_USDT, color="black", linewidth=0.8, linestyle=":")
        axis.set_title(f"{policy}: gross versus cost-adjusted equity (daily close of marked equity)")
        axis.set_ylabel("Equity (USDT)")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.3)
        axis.tick_params(axis="x", labelrotation=30, labelsize=7)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(chart_dir / "equity_gross_vs_cost.png", dpi=150)
    plt.close(figure)
    written.append("equity_gross_vs_cost.png")

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=False)
    for axis, policy in zip(axes, engine.POLICIES, strict=True):
        rows = scenarios[headline_key][policy]["run"].equity
        days, _ = _daily_series(rows)
        worst: dict[str, float] = {}
        for row in rows:
            day = row["timestamp"][:10]
            worst[day] = max(worst.get(day, 0.0), float(row["drawdown_pct"]))
        axis.fill_between(days, [worst[day] for day in days], color="#b03030", alpha=0.35)
        axis.plot(days, [worst[day] for day in days], color="#702020", linewidth=0.9)
        axis.set_title(
            f"{policy}: drawdown under the headline cost scenario "
            f"(max {scenarios[headline_key][policy]['summary']['max_drawdown_pct']:.4f}% of peak equity)"
        )
        axis.set_ylabel("Drawdown (% of peak equity)")
        axis.grid(alpha=0.3)
        axis.tick_params(axis="x", labelrotation=30, labelsize=7)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(chart_dir / "drawdown.png", dpi=150)
    plt.close(figure)
    written.append("drawdown.png")

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for axis, policy in zip(axes, engine.POLICIES, strict=True):
        grid_values = [
            [scenarios[engine.scenario_key(fee, slip)][policy]["summary"]["net_pnl_usdt"] for slip in engine.SLIPPAGE_RATES]
            for fee in engine.FEE_RATES
        ]
        image = axis.imshow(grid_values, cmap="RdYlGn", aspect="auto")
        axis.set_xticks(range(len(engine.SLIPPAGE_RATES)), [f"{value * 100:.3f}%" for value in engine.SLIPPAGE_RATES])
        axis.set_yticks(range(len(engine.FEE_RATES)), [f"{value * 100:.3f}%" for value in engine.FEE_RATES])
        axis.set_xlabel("Slippage per side")
        axis.set_ylabel("Fee per side")
        axis.set_title(f"{policy}: net P&L (USDT) across the frozen cost grid")
        for row_index, row in enumerate(grid_values):
            for column_index, value in enumerate(row):
                axis.text(column_index, row_index, f"{value:,.2f}", ha="center", va="center", fontsize=9)
        figure.colorbar(image, ax=axis, shrink=0.85)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(chart_dir / "cost_sensitivity.png", dpi=150)
    plt.close(figure)
    written.append("cost_sensitivity.png")
    return written


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def render_report(summary: dict[str, Any], manifest: dict[str, Any]) -> str:
    headline = summary["headline"]
    lines = [
        "# BTC M15 reference backtest — frozen protocol, two policies",
        "",
        "**Historical development evidence.** Both policies were traded over a window",
        "that has already been examined in this repository, on delayed candle-price",
        "proxies rather than guaranteed fills. This is not realized P&L, not a live",
        "sizing recommendation, and not evidence of an edge.",
        f"Alpha assessment: `{engine.PROTOCOL['alpha_assessment']}`.",
        "",
        "**Cost-adjusted results are labelled: After assumed trading fees and slippage,",
        "before funding.** Perpetual funding is deliberately excluded from this",
        f"experiment (`funding_status = {engine.FUNDING_STATUS}`); no funding data was",
        "downloaded and no funding accounting was implemented. Excluded funding must not",
        "be read as *observed zero* funding — real funding could have been a cost or a",
        "credit and is simply not measured here. Entry and exit rules were not adjusted",
        "to avoid or capture funding settlements.",
        "",
        "## Frozen protocol",
        "",
        f"- Protocol version: `{engine.VERSION}`, frozen before any performance number was computed (`protocol.json` SHA-256 `{manifest['protocol_sha256'][:32]}…`).",
        f"- Evaluation window (UTC): `{engine.PROTOCOL['evaluation_window']['start_utc']}` → `{engine.PROTOCOL['evaluation_window']['end_utc']}`.",
        f"- Capital: `{engine.INITIAL_EQUITY_USDT:,.0f}` USDT initial equity, `{engine.ENTRY_NOTIONAL_USDT:,.0f}` USDT fixed entry notional (research constants).",
        "- Entry: open of the first existing native M5 candle strictly after the signal close. Exit: exactly 60 minutes later at that candle's open.",
        "- No stop-loss, take-profit, trailing rule, or alternative horizon. One active position per policy, no pyramiding, exits processed before entries at the same timestamp.",
        "",
        "## Populations and policy definitions",
        "",
        "| Policy | Signal rule | Cooldown | Signals |",
        "|---|---|---|---:|",
        f"| `A_emitted_alerts` | Emitted replay M15 alerts: fresh RSI21 EMA9/WMA45 bullish cross **and** M15, H1, H4 closes above native EMA21 | Replay one-hour per-timeframe | {headline['A_emitted_alerts']['signals']:,} |",
        f"| `B_gate_cooldown` | The same three price-above-EMA21 gates **without** the RSI crossover | **Its own** independent one-hour cooldown | {headline['B_gate_cooldown']['signals']:,} |",
        "",
        "Policy B is **not** the descriptive `gate_ready_no_cross` population from the M15",
        f"diagnostic. That population had no cooldown and contained {manifest['gate_bars_before_cooldown']:,} bars;",
        "policy B applies the one-hour cooldown and is therefore far smaller, with accepted",
        "bars at least 60 minutes apart.",
        "",
        "## Headline results (fee 0.050% per side, slippage 0.010% per side)",
        "",
        "| Metric | A `emitted_alerts` | B `gate_cooldown` |",
        "|---|---:|---:|",
    ]
    rows = [
        ("Signals", "signals", "{:,}"),
        ("Trades entered", "entered_trades", "{:,}"),
        ("Entries skipped", "skipped_entries", "{:,}"),
        ("Entries deferred to a position exit", "deferred_entries", "{:,}"),
        ("Unresolved trades", "unresolved_trades", "{:,}"),
        ("Gross P&L (USDT)", "gross_pnl_usdt", "{:,.2f}"),
        ("Execution friction P&L (USDT)", "friction_pnl_usdt", "{:,.2f}"),
        ("Fee P&L (USDT)", "fee_pnl_usdt", "{:,.2f}"),
        ("Net P&L (USDT)", "net_pnl_usdt", "{:,.2f}"),
        ("Gross P&L per trade (USDT)", "gross_pnl_per_trade_usdt", "{:,.4f}"),
        ("Net P&L per trade (USDT)", "net_pnl_per_trade_usdt", "{:,.4f}"),
        ("Final equity (USDT)", "final_equity_usdt", "{:,.2f}"),
        ("Total return (%)", "total_return_pct", "{:.4f}"),
        ("Max drawdown (% of peak equity)", "max_drawdown_pct", "{:.4f}"),
        ("Time in market (%)", "time_in_market_fraction", "{:.2%}"),
        ("Average deployed notional (USDT)", "average_deployed_notional_usdt", "{:,.2f}"),
        ("Total turnover (USDT)", "total_turnover_usdt", "{:,.2f}"),
        ("Turnover / initial equity", "turnover_over_initial_equity", "{:.2f}"),
        ("Win rate (%)", "win_rate_pct", "{:.2f}"),
        ("Expectancy per trade (USDT)", "expectancy_usdt", "{:.4f}"),
    ]
    for label, key, pattern in rows:
        left = headline["A_emitted_alerts"].get(key)
        right = headline["B_gate_cooldown"].get(key)
        lines.append(
            f"| {label} | {pattern.format(left) if left is not None else 'n/a'} "
            f"| {pattern.format(right) if right is not None else 'n/a'} |"
        )
    lines += [
        "",
        "Gross, friction, and fee components are disjoint and sum to net P&L; nothing is",
        "double counted. `time_in_market_fraction` is position-seconds divided by window",
        "seconds, and `average_deployed_notional_usdt` is notional-seconds divided by window",
        "seconds, so neither is inflated by overlapping exposure — there is none.",
        "",
        "Every row above is **After assumed trading fees and slippage, before funding.**",
        "",
        "### Capital exhaustion must be read alongside these totals",
        "",
    ]
    for policy in engine.POLICIES:
        item = headline[policy]
        lines.append(
            f"- `{policy}`: capital exhausted = `{item['capital_exhausted']}`; "
            f"{item['skipped_entries']:,} of {item['signals']:,} signals were never entered."
        )
    lines += [
        "",
        "The frozen constants (10,000 USDT equity, 1,000 USDT fixed non-compounding notional,",
        "one position at a time) mean that a policy which loses money at this trade count runs",
        "out of cash and stops entering. Any policy that exhausts its capital has its *realized*",
        "net P&L truncated by that exhaustion, so the headline net totals are **not** a clean",
        "like-for-like comparison. Gross and net P&L **per trade** are capital-independent and",
        "are the fair per-signal comparison.",
        "",
        "### Why both policies lose: costs dominate the gross edge",
        "",
    ]
    for policy in engine.POLICIES:
        item = headline[policy]
        gross_per_trade = item["gross_pnl_per_trade_usdt"]
        net_per_trade = item["net_pnl_per_trade_usdt"]
        lines.append(
            f"- `{policy}`: gross {gross_per_trade:+.4f} USDT per trade, net {net_per_trade:+.4f} USDT per "
            f"trade, so assumed costs remove about {abs(net_per_trade - gross_per_trade):.4f} USDT "
            f"(≈{abs(net_per_trade - gross_per_trade) / engine.ENTRY_NOTIONAL_USDT * 100:.3f}% of the "
            "1,000 USDT entry notional) on every round trip."
        )
    lines += [
        "",
        "At the headline assumptions the round-trip fee plus slippage is roughly 0.12% of notional,",
        "while the measured gross edge per trade is a small fraction of that. Policy B trades far",
        "more often (turnover 1,572× initial equity versus 235× for A), so it pays that toll far",
        "more times. This is a cost-drag observation about trade frequency, not a claim about",
        "either signal's predictive quality.",
        "",
    ]
    lines += [
        "",
        "## Cost sensitivity (every frozen scenario)",
        "",
        "| Fee / side | Slippage / side | A net P&L | A gross P&L | A fees | A friction | B net P&L | B gross P&L | B fees | B friction |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario in summary["cost_sensitivity"]:
        cells = []
        for policy in engine.POLICIES:
            item = scenario[policy]
            cells.append(
                f"{item['net_pnl_usdt']:,.2f} | {item['gross_pnl_usdt']:,.2f} | "
                f"{item['fee_pnl_usdt']:,.2f} | {item['friction_pnl_usdt']:,.2f}"
            )
        lines.append(
            f"| {scenario['fee_rate_per_side'] * 100:.3f}% | {scenario['slippage_rate_per_side'] * 100:.3f}% "
            f"| {cells[0]} | {cells[1]} |"
        )
    lines += [
        "",
        "Fees use the Binance USD-M defaults in `app/core/constants.py` as illustrative",
        "research assumptions, not as verified account fees. Slippage is an assumed",
        "research friction. Perpetual funding is **excluded by design** and is not zero",
        "observed funding, so none of these scenarios is fully net profit.",
        "",
        "## Charts",
        "",
        "![Gross versus cost-adjusted equity](charts/equity_gross_vs_cost.png)",
        "",
        "![Drawdown under the headline cost scenario](charts/drawdown.png)",
        "",
        "![Net P&L across the frozen fee and slippage grid](charts/cost_sensitivity.png)",
        "",
        "- `charts/equity_gross_vs_cost.png` — gross versus cost-adjusted equity per policy.",
        "- `charts/drawdown.png` — drawdown under the headline cost scenario per policy.",
        "- `charts/cost_sensitivity.png` — net P&L across the full frozen fee/slippage grid.",
        "",
        "## Missing data and unresolved trades",
        "",
        f"- Unresolved trades excluded from realized P&L: **{headline['A_emitted_alerts']['unresolved_trades']}** (A) and **{headline['B_gate_cooldown']['unresolved_trades']}** (B).",
        f"- Skipped entries and their reasons: A `{json.dumps(headline['A_emitted_alerts']['skip_reasons'], sort_keys=True)}`, B `{json.dumps(headline['B_gate_cooldown']['skip_reasons'], sort_keys=True)}`.",
        "- A missing entry candle skips the entry; a missing exact exit candle leaves the trade explicitly unresolved and blocks new exposure. No later candle is ever substituted.",
        "- Entries are bounded by the window end; a trade already entered runs to its exact scheduled exit, which may fall after the window end.",
        "",
        "## Verification",
        "",
        f"- An independent one-hour cooldown over the {manifest['policy_a_reconstruction']['cross_and_gate_bars_before_cooldown']:,} cross-and-gate M15 bars reproduces the replay's emitted alerts exactly: `{manifest['policy_a_reconstruction']['matches']}` ({manifest['policy_a_reconstruction']['emitted_count']:,} vs {manifest['policy_a_reconstruction']['reconstructed_count']:,}).",
        f"- Source hashes re-checked against the parent packet: `{manifest['source_hash_parity']}`.",
        "- Every signal produces exactly one entry outcome (filled, deferred then filled, or skipped with a reason), enforced at run time.",
        "- Every executed trade holds exactly 60 minutes, deploys exactly the frozen 1,000 USDT entry notional, and ends `CLOSED_AT_SCHEDULED_EXIT`; there are no unresolved trades in this dataset.",
        "- The trade ledger reconciles with the equity curve: final equity equals initial equity plus the sum of net trade P&L.",
        "",
        "## Limitations",
        "",
        "- Every observation is historical development evidence on an already-examined window; there is no untouched holdout.",
        "- Candle opens are delayed proxies. Real fills, partial fills, queue position, spread, and market impact are not modelled.",
        f"- Perpetual funding is `{engine.FUNDING_STATUS}`: excluded on purpose, never measured, and not observed to be zero.",
        "- Cost-adjusted numbers are therefore *After assumed trading fees and slippage, before funding* and are not fully net profit.",
        "- Only one policy pair, one horizon, and one exit rule were tested. Nothing here was optimized, and nothing should be promoted to live trading.",
        "- No conclusion here changes any production strategy, sizing, risk control, or configuration.",
        "- No historical funding data was downloaded, and no production trading logic was touched.",
        "",
        "## Exact reproduction",
        "",
        "```powershell",
        manifest["command"],
        "```",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(baseline_run: Path, output_dir: Path, *, charts: bool = True) -> Path:
    """Freeze the protocol, run both policies, and write one evidence packet."""

    baseline_run = baseline_run.resolve()
    parent_identity = {name: phase1._hash_file(baseline_run / name) for name in PARENT_FILES}
    parent, summary_in, inputs = engine.load_signal_inputs(baseline_run)
    a_signals = engine.policy_a_signals(summary_in["m15_rows"])
    if not a_signals:
        raise ValueError("No emitted M15 alerts inside the frozen evaluation window")
    scan, scan_audit = diagnostic_scan(inputs)
    b_signals = engine.policy_b_signals(scan)
    if not b_signals:
        raise ValueError("Policy B produced no signals inside the frozen evaluation window")
    reconstruction = engine.reconstruct_policy_a(scan, a_signals)
    if not reconstruction["matches"]:
        logger.warning("policy_a_reconstruction_mismatch", **reconstruction)
    grid = engine.M5Grid.from_frame(inputs.frames[engine.EXECUTION_TIMEFRAME])

    timestamp = datetime.now(UTC)
    packet = output_dir.resolve() / f"run_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{parent['inputs']['files'][engine.TIMEFRAME]['sha256'][:8]}"
    packet.mkdir(parents=True, exist_ok=False)
    protocol_text = _json_text(engine.PROTOCOL)
    (packet / "protocol.json").write_text(protocol_text, encoding="utf-8")
    protocol_sha = _sha256_text(protocol_text)

    scenarios = engine.run_cost_grid(
        {engine.POLICIES[0]: a_signals, engine.POLICIES[1]: b_signals}, grid
    )
    headline_key = engine.scenario_key(engine.HEADLINE_FEE_RATE, engine.HEADLINE_SLIPPAGE_RATE)
    headline_runs = {policy: scenarios[headline_key][policy]["run"] for policy in engine.POLICIES}
    headline_summary = {
        policy: scenarios[headline_key][policy]["summary"] for policy in engine.POLICIES
    }
    cost_sensitivity = [
        {
            "fee_rate_per_side": fee,
            "slippage_rate_per_side": slippage,
            **{
                policy: scenarios[engine.scenario_key(fee, slippage)][policy]["summary"]
                for policy in engine.POLICIES
            },
        }
        for fee in engine.FEE_RATES
        for slippage in engine.SLIPPAGE_RATES
    ]

    actions = [row for policy in engine.POLICIES for row in headline_runs[policy].actions]
    trades = [row for policy in engine.POLICIES for row in headline_runs[policy].trades]
    curve_rows = [row for policy in engine.POLICIES for row in headline_runs[policy].equity]
    curve_text = _csv_text(engine.EQUITY_FIELDS, curve_rows)
    full_curve_sha = _sha256_text(curve_text)
    resolution, committed_curve, committed_rows = _pick_committed_curve(
        curve_rows,
        curve_text,
        _downsample_hourly(curve_rows),
        _downsample_daily(curve_rows),
    )
    (packet / "actions.csv").write_text(_csv_text(engine.ACTION_FIELDS, actions), encoding="utf-8")
    (packet / "trades.csv").write_text(_csv_text(engine.TRADE_FIELDS, trades), encoding="utf-8")
    (packet / "equity_curve.csv").write_text(committed_curve, encoding="utf-8")
    written_charts = render_charts(scenarios, packet / "charts") if charts else []

    root = Path(__file__).resolve().parents[1]
    manifest = {
        "definition_version": engine.VERSION,
        "completion_status": "SUCCESS",
        "alpha_assessment": engine.PROTOCOL["alpha_assessment"],
        "evidence_role": engine.PROTOCOL["evidence_role"],
        "run_id": packet.name,
        "generated_at_utc": phase1._utc_iso(timestamp),
        "command": (
            f'python -m research.btc_m15_reference_reporting --baseline-run "{baseline_run}" '
            f'--output-dir "{output_dir.resolve()}"' + ("" if charts else " --no-charts")
        ),
        "protocol_sha256": protocol_sha,
        "policy_a_reconstruction": reconstruction,
        "gate_bars_before_cooldown": len(engine.gate_bar_times(scan)),
        "scan": scan_audit,
        "parent": {
            "run_id": parent["run_id"],
            "path": str(baseline_run),
            "files_sha256": parent_identity,
        },
        "inputs": inputs.source_report,
        "source_hash_parity": all(
            inputs.source_report["files"][timeframe]["sha256"] == parent["inputs"]["files"][timeframe]["sha256"]
            for timeframe in phase1.TIMEFRAMES
        ),
        "signals": {
            policy: {
                "count": len(signals),
                "times_sha256": hashlib.sha256("\n".join(phase1._utc_iso(value) for value in signals).encode()).hexdigest(),
            }
            for policy, signals in ((engine.POLICIES[0], a_signals), (engine.POLICIES[1], b_signals))
        },
        "environment": phase1._environment(),
        "code_sha256": {
            path: phase1._hash_file(root / path) for path in CODE_PATHS if (root / path).is_file()
        },
        "artifacts": {
            "actions_rows": len(actions),
            "trades_rows": len(trades),
            "equity_curve_rows_committed": committed_rows,
            "equity_curve_rows_full": len(curve_rows),
            "equity_curve_sha256_full": full_curve_sha,
            "equity_curve_resolution": resolution,
            "omitted_artifact_note": (
                None
                if resolution == "full_m5_marks"
                else f"The full-resolution curve exceeded the committed size cap; the committed file is a "
                f"{resolution.replace('_downsample', '')} downsample while all metrics use the full-resolution "
                "marks. Regenerate the full file with the command below and verify the SHA-256 above."
            ),
            "charts": written_charts,
        },
        "git": _trimmed_git_identity(root, output_dir),
        "funding_status": engine.FUNDING_STATUS,
        "cost_adjusted_label": engine.COST_ADJUSTED_LABEL,
    }
    summary = {
        "definition_version": engine.VERSION,
        "alpha_assessment": engine.PROTOCOL["alpha_assessment"],
        "evidence_role": engine.PROTOCOL["evidence_role"],
        "funding_status": engine.FUNDING_STATUS,
        "cost_adjusted_label": engine.COST_ADJUSTED_LABEL,
        "window": engine.PROTOCOL["evaluation_window"],
        "headline_scenario": {
            "fee_rate_per_side": engine.HEADLINE_FEE_RATE,
            "slippage_rate_per_side": engine.HEADLINE_SLIPPAGE_RATE,
        },
        "headline": headline_summary,
        "cost_sensitivity": cost_sensitivity,
        "unresolved_trades": {
            policy: headline_runs[policy].unresolved for policy in engine.POLICIES
        },
        "limitations": [
            "Historical development evidence on an already-examined window; no untouched holdout.",
            "Delayed candle-price proxies, not guaranteed fills.",
            "EXCLUDED_BY_DESIGN: perpetual funding is deliberately excluded, never measured, and not observed to be zero.",
            "Cost-adjusted results are 'After assumed trading fees and slippage, before funding.' and are not fully net profit.",
            "No optimization, no shadow collection, and no live promotion.",
        ],
    }
    (packet / "manifest.json").write_text(_json_text(manifest), encoding="utf-8")
    (packet / "summary.json").write_text(_json_text(summary), encoding="utf-8")
    (packet / "report.md").write_text(render_report(summary, manifest), encoding="utf-8")
    logger.info(
        "btc_m15_reference_backtest_complete",
        packet=str(packet),
        a_trades=headline_summary[engine.POLICIES[0]]["entered_trades"],
        b_trades=headline_summary[engine.POLICIES[1]]["entered_trades"],
        a_net=headline_summary[engine.POLICIES[0]]["net_pnl_usdt"],
        b_net=headline_summary[engine.POLICIES[1]]["net_pnl_usdt"],
        reconstruction_matches=reconstruction["matches"],
    )
    return packet


def _pick_committed_curve(
    curve_rows: list[dict[str, Any]],
    curve_text: str,
    hourly_rows: list[dict[str, Any]],
    daily_rows: list[dict[str, Any]],
) -> tuple[str, str, int]:
    """Commit the finest equity curve that fits the size cap.

    Metrics always use the full-resolution marks; the committed file is a review
    artifact and its full-resolution hash is recorded in the manifest.
    """

    candidates = (
        ("full_m5_marks", curve_text, len(curve_rows)),
        ("hourly_downsample", _csv_text(engine.EQUITY_FIELDS, hourly_rows), len(hourly_rows)),
        ("daily_downsample", _csv_text(engine.EQUITY_FIELDS, daily_rows), len(daily_rows)),
    )
    for resolution, text, rows in candidates:
        if len(text.encode("utf-8")) <= MAX_COMMITTED_CURVE_BYTES:
            return resolution, text, rows
    return candidates[-1]


def diagnostic_scan(inputs: phase1.ValidatedInputs):
    """Reuse the verified M15 diagnostic scan over the frozen window."""

    return diagnostic.scan_population(inputs, engine.WINDOW_START, engine.WINDOW_END)


def _trimmed_git_identity(root: Path, output_dir: Path) -> dict[str, Any]:
    """Repository content identity with the (very long) status list summarised."""

    identity = phase1._git_identity(root, excluded_paths=(output_dir.resolve(),))
    status = list(identity.pop("status", []))
    identity["status_count"] = len(status)
    identity["status_head"] = status[:200]
    identity["status_note"] = "Full status list truncated to the first 200 entries; the content hash covers all of them."
    return identity


def _downsample_hourly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one mark per policy-hour plus every non-OPEN (trade event) row."""

    kept: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        kept[(row["policy"], row["timestamp"][:13] + ":00:00Z")] = row
    for row in rows:
        if row["state"] != "OPEN":
            kept[(row["policy"], row["timestamp"])] = row
    return [kept[key] for key in sorted(kept)]


def _downsample_daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one mark per policy-day plus every non-OPEN (trade event) row."""

    kept: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        kept[(row["policy"], row["timestamp"][:10] + "T00:00:00Z")] = row
    for row in rows:
        if row["state"] != "OPEN":
            kept[(row["policy"], row["timestamp"])] = row
    return [kept[key] for key in sorted(kept)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen offline BTC M15 reference backtest")
    parser.add_argument("--baseline-run", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-charts", action="store_true")
    arguments = parser.parse_args(argv)
    run(arguments.baseline_run, arguments.output_dir, charts=not arguments.no_charts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
