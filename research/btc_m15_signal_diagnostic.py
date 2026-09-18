"""Offline descriptive M15 signal-and-gate comparison for the BTC RSI cross alert.

This is a read-only diagnostic over an accepted Phase 1 packet. It reuses the
existing replay preparation, the existing pure M15 evaluator, and the existing
exact close-to-close outcome arithmetic. It never re-implements a signal, never
simulates an order, and never selects a horizon or threshold.

Three frozen populations are compared over the same UTC trigger-close window
and under the same complete-outcome rule:

``m15_signal``
    M15 alerts actually emitted by the existing replay: a fresh RSI21
    EMA9/WMA45 bullish cross plus the M15, H1 and H4 close-above-EMA21 gates,
    with the replay's one-hour per-timeframe cooldown already applied.

``gate_ready_no_cross``
    Preparation-ready M15 bars whose M15, H1 and H4 closes are all above their
    native EMA21, with **no** RSI crossover requirement and **no** cooldown.
    ``m15_signal`` is a cooldown-thinned subset of this population.

``all_eligible_bars``
    Every preparation-ready M15 bar in the matched window: no gate and no
    cooldown. This is the existing Phase 1 all-eligible-bar comparator.

Only the 1-hour and 4-hour horizons are used. They are fixed, not searched.
Every statistic is descriptive signal research on signal-close forward returns;
it is not a fill model, a trading policy, a P&L statement, or a claim of edge.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from app.backtest import btc_research_phase1 as phase1
from app.backtest.signal_replay_data import events_for_frame
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import evaluate_m15_cross
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
    DECISION_NO_FRESH_BULLISH_CROSS,
    PREPARATION_READY,
    BtcRsiCrossInput,
)
from research.btc_m5_horizon_diagnostic import paired_bootstrap

VERSION = "btc-m15-signal-diagnostic-v1"
TIMEFRAME = "15m"
HORIZONS: tuple[tuple[str, int], ...] = (("1h", 60), ("4h", 240))
GROUPS = ("m15_signal", "gate_ready_no_cross", "all_eligible_bars")
PARENT_FILES = ("manifest.json", "signals.csv", "summary.json", "report.md")
PARENT_HORIZON_MINUTES = (60, 240, 720, 1440)
#: Cross present **and** all three price gates passed; the bar is an emitted alert.
CROSS_AND_GATES_ALERT_REASONS = (DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,)
#: Cross present but a price gate failed, in the checker's locked precedence order.
CROSS_WITH_GATE_FAILED_REASONS = (
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_H1_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
)
OBSERVATION_FIELDS = (
    "group",
    "event_id",
    "trigger_close_at",
    "trigger_close_price",
    "horizon",
    "horizon_minutes",
    "target_close_at",
    "target_close_price",
    "outcome_status",
    "return_pct",
    "included_both_horizons",
)
logger = structlog.get_logger()


def price_gates(data: BtcRsiCrossInput) -> dict[str, bool]:
    """The three price-above-EMA21 gates exactly as the live checkers apply them.

    ``m15_checker.evaluate_m15_cross`` rejects on ``<=`` for each of these three
    comparisons, so the strict ``>`` used here is the identical predicate.
    """

    return {
        "m15_close_above_ema21": bool(data.trigger_close_price > data.trigger_price_ema21),
        "h1_close_above_ema21": bool(data.h1_close_price > data.h1_price_ema21),
        "h4_close_above_ema21": bool(data.h4_close_price > data.h4_price_ema21),
    }


def fresh_bullish_cross(decision_reason: str) -> bool:
    """Derive cross presence from the locked decision precedence.

    ``evaluate_btc_rsi_cross`` returns ``NO_FRESH_BULLISH_CROSS`` only when the
    cross test itself failed; every other reason is reached after it passed.
    """

    return decision_reason != DECISION_NO_FRESH_BULLISH_CROSS


def parent_identity(directory: Path) -> dict[str, str]:
    return {name: phase1._hash_file(directory / name) for name in PARENT_FILES}


def load_parent(directory: Path) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    """Validate one accepted Phase 1 packet and return its M15 rows."""

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if (
        manifest["run_id"] != directory.name
        or manifest["completion_status"] != "SUCCESS"
        or summary["completion_status"] != "SUCCESS"
        or manifest["definition_version"] != phase1.DEFINITION_VERSION
        or manifest["inputs"]["identity"]["venue_instrument"] != phase1.VENUE_INSTRUMENT
    ):
        raise ValueError("Parent packet identity or completion contract does not match Phase 1")
    all_rows = pd.read_csv(directory / "signals.csv", keep_default_na=False)
    rows = all_rows.loc[all_rows.timeframe == TIMEFRAME].copy()
    invariant = ["sequence", "trigger_open_at", "trigger_close_at", "trigger_close_price"]
    if rows.empty or rows.groupby("event_id")[invariant].nunique().gt(1).any().any():
        raise ValueError("Parent M15 population is empty or has inconsistent signal identity")
    for _, group in rows.groupby("event_id"):
        if sorted(group.horizon_minutes) != list(PARENT_HORIZON_MINUTES):
            raise ValueError("Each parent M15 ID must have exactly the four Phase 1 horizons")
    signals = rows.drop_duplicates("event_id").sort_values("trigger_close_at")
    times = pd.to_datetime(signals.trigger_close_at, utc=True)
    if (
        len(signals) != summary["signal_counts"][TIMEFRAME]
        or times.duplicated().any()
        or times.diff().dropna().lt(pd.Timedelta(hours=1)).any()
    ):
        raise ValueError("Parent M15 count, timestamp identity, or one-hour cooldown is inconsistent")
    return manifest, summary, rows


def signal_close_times(parent_rows: pd.DataFrame) -> list[str]:
    """Unique emitted M15 trigger closes in deterministic order."""

    unique = parent_rows.drop_duplicates("event_id").sort_values("trigger_close_at")
    return unique.trigger_close_at.tolist()


def source_inputs(manifest: dict[str, Any]) -> phase1.ValidatedInputs:
    """Reload the parent's native sources and refuse any hash drift."""

    files = manifest["inputs"]["files"]
    inputs = phase1.validate_inputs(Path(files[TIMEFRAME]["path"]).parent)
    for timeframe in phase1.TIMEFRAMES:
        if inputs.source_report["files"][timeframe]["sha256"] != files[timeframe]["sha256"]:
            raise ValueError(f"Source hash differs from parent: {timeframe}")
    return inputs


def scan_population(
    inputs: phase1.ValidatedInputs,
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Prepare and evaluate every M15 trigger bar in one matched window."""

    cache = phase1._cache_for(inputs)
    events = events_for_frame(inputs.frames[TIMEFRAME], TIMEFRAME, start, end)
    records: list[dict[str, Any]] = []
    exclusions: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for event in events:
        preparation = cache.prepare(event, symbol=phase1.SYMBOL)
        record: dict[str, Any] = {
            "trigger_close_at": phase1._utc_iso(event.close_time),
            "position": int(event.position),
            "preparation_reason": preparation.reason,
            "trigger_close_price": None,
            "h1_close_at": None,
            "h4_close_at": None,
            "m15_decision_reason": None,
            "fresh_bullish_cross": None,
            "m15_close_above_ema21": None,
            "h1_close_above_ema21": None,
            "h4_close_above_ema21": None,
            "price_gates_pass": None,
            "should_alert": None,
        }
        if preparation.input is None:
            exclusions[preparation.reason] += 1
            records.append(record)
            continue
        decision = evaluate_m15_cross(preparation.input)
        gates = price_gates(preparation.input)
        decisions[decision.reason] += 1
        record.update(
            {
                "trigger_close_price": float(preparation.input.trigger_close_price),
                "h1_close_at": phase1._utc_iso(preparation.input.h1_close_time),
                "h4_close_at": phase1._utc_iso(preparation.input.h4_close_time),
                "m15_decision_reason": decision.reason,
                "fresh_bullish_cross": fresh_bullish_cross(decision.reason),
                **gates,
                "price_gates_pass": all(gates.values()),
                "should_alert": bool(decision.should_alert),
            }
        )
        records.append(record)
    frame = pd.DataFrame.from_records(records)
    audit = {
        "timeframe": TIMEFRAME,
        "window_start_close_utc": phase1._utc_iso(events[0].close_time) if events else None,
        "window_end_close_utc": phase1._utc_iso(events[-1].close_time) if events else None,
        "window_semantics": "Inclusive exact M15 trigger closes, identical to the Phase 1 matched 15m comparator window.",
        "candidate_bar_count": len(events),
        "eligible_bar_count": int(frame.preparation_reason.eq(PREPARATION_READY).sum()) if len(frame) else 0,
        "preparation_excluded_count": int(sum(exclusions.values())),
        "preparation_exclusion_reasons": dict(sorted(exclusions.items())),
        "eligible_decision_reason_counts": dict(sorted(decisions.items())),
    }
    audit["price_gates_pass_bar_count"] = (
        int(frame.price_gates_pass.fillna(False).astype(bool).sum()) if len(frame) else 0
    )
    audit["price_gates_pass_share_of_eligible"] = (
        audit["price_gates_pass_bar_count"] / audit["eligible_bar_count"] if audit["eligible_bar_count"] else 0.0
    )
    if len(frame):
        ready = frame.preparation_reason.eq(PREPARATION_READY)
        gates = frame.price_gates_pass.fillna(False).astype(bool) & ready
        crossed = frame.fresh_bullish_cross.fillna(False).astype(bool) & ready
        audit["cross_and_gates_bar_count"] = int((gates & crossed).sum())
        audit["cross_without_gates_bar_count"] = int((crossed & ~gates).sum())
        audit["no_cross_bar_count"] = int((ready & ~crossed).sum())
    else:
        audit["cross_and_gates_bar_count"] = 0
        audit["cross_without_gates_bar_count"] = 0
        audit["no_cross_bar_count"] = 0
    logger.info(
        "m15_signal_diagnostic_scanned",
        candidate_bars=len(events),
        eligible_bars=audit["eligible_bar_count"],
        price_gates_pass=audit["price_gates_pass_bar_count"],
    )
    return frame, audit


def verify_gate_consistency(scan: pd.DataFrame) -> None:
    """The documented gate predicate must agree with the locked decision reasons."""

    eligible = scan.loc[scan.preparation_reason.eq(PREPARATION_READY)]
    if eligible.empty:
        return
    reason = eligible.m15_decision_reason
    crossed = eligible.fresh_bullish_cross.fillna(False).astype(bool)
    gates = eligible.price_gates_pass.fillna(False).astype(bool)
    if not reason.loc[~crossed].eq(DECISION_NO_FRESH_BULLISH_CROSS).all():
        raise ValueError("A bar without a fresh bullish cross did not report NO_FRESH_BULLISH_CROSS")
    passing_reasons = set(CROSS_AND_GATES_ALERT_REASONS)
    allowed_reasons = passing_reasons | set(CROSS_WITH_GATE_FAILED_REASONS)
    implied_gates = reason.isin(passing_reasons)
    if not reason.loc[crossed].isin(allowed_reasons).all():
        raise ValueError("A crossed bar reported a decision reason inconsistent with the gate order")
    if not implied_gates.loc[crossed].eq(gates.loc[crossed]).all():
        raise ValueError("The price-gate predicate disagrees with the locked M15 decision reasons")


def group_membership(scan: pd.DataFrame, signals: list[str]) -> dict[str, pd.Series]:
    """Documented eligibility masks for the three frozen populations."""

    eligible = scan.preparation_reason.eq(PREPARATION_READY)
    gates = scan.price_gates_pass.fillna(False).astype(bool)
    emitted = scan.trigger_close_at.isin(set(signals))
    missing = scan.loc[emitted & ~(eligible & gates), "trigger_close_at"].tolist()
    if missing:
        raise ValueError(f"Emitted M15 alerts fail the documented gate rules: {missing[:5]}")
    return {
        "m15_signal": emitted,
        "gate_ready_no_cross": eligible & gates,
        "all_eligible_bars": eligible,
    }


def bar_identity(scan: pd.DataFrame) -> list[str]:
    """Deterministic per-bar identity; the signal group keeps the emitted ID."""

    return ["m15_bar_" + value for value in scan.trigger_close_at.tolist()]


def observations(
    scan: pd.DataFrame,
    membership: dict[str, pd.Series],
    source: phase1._ForwardIndex,
) -> pd.DataFrame:
    """Exact fixed-horizon outcomes for every population member."""

    close_times = pd.to_datetime(scan.trigger_close_at, utc=True).dt.to_pydatetime().tolist()
    prices = scan.trigger_close_price.to_numpy(dtype=float)
    identifiers = bar_identity(scan)
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        for position in np.flatnonzero(membership[group].to_numpy(dtype=bool)):
            close_time = close_times[position]
            price = float(prices[position])
            for horizon, minutes in HORIZONS:
                outcome = phase1._exact_forward_outcome_from_index(
                    source,
                    TIMEFRAME,
                    trigger_close=close_time,
                    trigger_price=price,
                    horizon_minutes=minutes,
                )
                rows.append(
                    {
                        "group": group,
                        "event_id": identifiers[position],
                        "trigger_close_at": scan.trigger_close_at.iat[position],
                        "trigger_close_price": price,
                        "horizon": horizon,
                        "horizon_minutes": minutes,
                        **outcome,
                    }
                )
    frame = pd.DataFrame.from_records(rows)
    frame["return_pct"] = pd.to_numeric(frame["return_pct"], errors="coerce")
    frame["included_both_horizons"] = False
    for _, group in frame.groupby(["group", "event_id"], sort=False):
        if len(group) == len(HORIZONS) and group.outcome_status.eq("COMPLETE").all():
            frame.loc[group.index, "included_both_horizons"] = True
    return frame


def verify_parent_returns(parent_rows: pd.DataFrame, computed: pd.DataFrame) -> None:
    """The two fixed horizons must reproduce the parent's own arithmetic."""

    minutes = [value for _, value in HORIZONS]
    current = computed.loc[computed["group"].eq("m15_signal")].drop(columns=["group", "included_both_horizons"])
    parent = parent_rows.loc[parent_rows.horizon_minutes.isin(minutes)]
    check = parent.merge(
        current,
        on=["trigger_close_at", "horizon_minutes"],
        suffixes=("_parent", "_current"),
        validate="one_to_one",
    )
    if len(check) != len(parent):
        raise ValueError("Parent 1h/4h parity could not be joined one-to-one")
    for field in ("target_close_at", "outcome_status"):
        if not check[f"{field}_parent"].eq(check[f"{field}_current"]).all():
            raise ValueError(f"Parent exact-horizon parity failed: {field}")
    for field in ("trigger_close_price", "target_close_price", "return_pct"):
        left = pd.to_numeric(check[f"{field}_parent"], errors="coerce")
        right = pd.to_numeric(check[f"{field}_current"], errors="coerce")
        if not np.allclose(left, right, rtol=0, atol=1e-10, equal_nan=True):
            raise ValueError(f"Parent exact-horizon parity failed: {field}")


def metrics(rows: pd.DataFrame) -> dict[str, Any]:
    """Summarize one population-horizon cell on its fixed complete population."""

    included = rows.loc[rows.included_both_horizons]
    returns = included.return_pct
    return {
        "n_total": len(rows),
        "n_complete": int(rows.outcome_status.eq("COMPLETE").sum()),
        "n_included": len(included),
        "status_counts": dict(Counter(rows.outcome_status)),
        "mean_return_pct": float(returns.mean()) if len(included) else None,
        "median_return_pct": float(returns.median()) if len(included) else None,
        "positive_return_share": float(returns.gt(0).mean()) if len(included) else None,
    }


def monthly_summaries(observations_frame: pd.DataFrame) -> pd.DataFrame:
    """Monthly UTC means and observation counts on the fixed complete population."""

    included = observations_frame.loc[observations_frame.included_both_horizons].copy()
    included["month_utc"] = included["trigger_close_at"].str.slice(0, 7)
    rows: list[dict[str, Any]] = []
    for (group, horizon, minutes, month), chunk in included.groupby(
        ["group", "horizon", "horizon_minutes", "month_utc"], sort=True
    ):
        rows.append(
            {
                "group": group,
                "horizon": horizon,
                "horizon_minutes": int(minutes),
                "month_utc": month,
                "n_included": len(chunk),
                "mean_return_pct": float(chunk.return_pct.mean()),
                "median_return_pct": float(chunk.return_pct.median()),
                "positive_return_share": float(chunk.return_pct.gt(0).mean()),
            }
        )
    return pd.DataFrame.from_records(rows)


def horizon_summaries(observations_frame: pd.DataFrame) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for horizon, minutes in HORIZONS:
        cell: dict[str, Any] = {"horizon": horizon, "horizon_minutes": minutes, "populations": {}}
        for group in GROUPS:
            rows = observations_frame.loc[
                observations_frame["group"].eq(group) & observations_frame.horizon_minutes.eq(minutes)
            ]
            cell["populations"][group] = metrics(rows)
        summaries.append(cell)
    return summaries


def contrast_uncertainty(observations_frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Reuse the existing paired 7-day circular calendar-block calculation."""

    results: list[dict[str, Any]] = []
    for horizon, minutes in HORIZONS:
        scoped = observations_frame.loc[observations_frame.horizon_minutes.eq(minutes)]
        by_group = {
            group: scoped.loc[scoped["group"].eq(group)].rename(
                columns={"included_both_horizons": "included_all_horizons"}
            )
            for group in GROUPS
        }
        for left, right in (
            ("m15_signal", "gate_ready_no_cross"),
            ("gate_ready_no_cross", "all_eligible_bars"),
            ("m15_signal", "all_eligible_bars"),
        ):
            estimate = paired_bootstrap(by_group[left], by_group[right])
            results.append(
                {
                    "horizon": horizon,
                    "horizon_minutes": minutes,
                    "contrast": f"{left}_minus_{right}",
                    "left": left,
                    "right": right,
                    **estimate,
                }
            )
    return results


def render_report(summary: dict[str, Any], manifest: dict[str, Any], monthly: pd.DataFrame) -> str:
    eligible = manifest["scan"]
    lines = [
        "# BTC M15 signal-and-gate diagnostic",
        "",
        "Descriptive signal research. Every number below is a gross signal-close",
        "forward return on overlapping historical observations. This is not realized",
        "P&L, not a fill or fee model, and not evidence of a trading edge.",
        "Alpha assessment: `NOT_ASSESSED`.",
        "",
        f"- Parent packet: `{manifest['parent']['run_id']}` (emitted M15 alerts `{manifest['parent']['signal_count']}`)",
        f"- Matched M15 window (UTC): `{eligible['window_start_close_utc']}` → `{eligible['window_end_close_utc']}`",
        f"- Candidate M15 bars: `{eligible['candidate_bar_count']}`; preparation-ready: `{eligible['eligible_bar_count']}`; preparation exclusions: `{eligible['preparation_excluded_count']}`",
        "- Fixed horizons: `1h` and `4h` (fixed, not searched)",
        "",
        "## Populations and cooldown policy",
        "",
        "| Group | Rule | Cooldown | n |",
        "|---|---|---|---:|",
        f"| `m15_signal` | Emitted replay alerts: fresh RSI21 EMA9/WMA45 bullish cross **and** M15, H1, H4 closes above native EMA21 | Replay one-hour per-timeframe cooldown applied | {manifest['population_counts']['m15_signal']} |",
        f"| `gate_ready_no_cross` | Preparation-ready M15 bars with M15, H1, H4 closes above native EMA21; RSI crossover not required | None | {manifest['population_counts']['gate_ready_no_cross']} |",
        f"| `all_eligible_bars` | Every preparation-ready M15 bar in the matched window; no gate | None | {manifest['population_counts']['all_eligible_bars']} |",
        "",
        "`m15_signal` is a cooldown-thinned subset of `gate_ready_no_cross`, which is a",
        "subset of `all_eligible_bars`. Two M15 bars are never more than 15 minutes apart,",
        "so all three populations contain heavily overlapping observations; the 1h and 4h",
        "windows of adjacent observations also overlap. These are not independent trades",
        "and are never compounded into an equity curve.",
        "",
        "Signal funnel over the matched window: "
        f"`{eligible['candidate_bar_count']}` candidate bars → "
        f"`{eligible['eligible_bar_count']}` preparation-ready → "
        f"`{eligible['price_gates_pass_bar_count']}` passing all three price gates → "
        f"`{eligible['cross_and_gates_bar_count']}` also showing a fresh RSI crossover → "
        f"`{manifest['population_counts']['m15_signal']}` emitted after the one-hour cooldown. "
        f"`{eligible['cross_without_gates_bar_count']}` further bars crossed but failed at least one price gate, "
        f"and `{eligible['cooldown_suppressed_bar_count']}` gate-and-cross bars were suppressed by the one-hour cooldown.",
        "",
        "## Mean and median forward returns",
        "",
        "Only observations whose **both** fixed horizons are `COMPLETE` enter every",
        "statistic, so the three populations are compared on one complete basis.",
        "",
        "| Horizon | Group | n included / total | Mean % | Median % | Positive share |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for cell in summary["horizon_summaries"]:
        for group in GROUPS:
            item = cell["populations"][group]
            lines.append(
                f"| {cell['horizon']} | `{group}` | {item['n_included']} / {item['n_total']} | "
                f"{_fmt(item['mean_return_pct'])} | {_fmt(item['median_return_pct'])} | "
                f"{_pct(item['positive_return_share'])} |"
            )
    lines += [
        "",
        "## Descriptive time-block uncertainty",
        "",
        "Reused from the existing M5 horizon diagnostic: paired circular 7-day UTC",
        "calendar blocks, 2,000 replicates, NumPy `default_rng(20260904)`, identical",
        "draws for both populations, observation-weighted means, 2.5th/97.5th",
        "percentiles. These are post-selection descriptive sensitivity intervals over",
        "already-examined history. They are not significance tests and do not correct",
        "for prior exploration, overlapping observations, or horizon choice.",
        "",
        "| Horizon | Contrast | Difference pp | Interval pp | Valid replicates |",
        "|---|---|---:|---|---:|",
    ]
    for item in summary["contrast_uncertainty"]:
        lines.append(
            f"| {item['horizon']} | `{item['contrast']}` | {_fmt(_contrast_difference(summary, item))} | "
            f"{_fmt_interval(item.get('signal_minus_baseline_ci_pp'))} | {item.get('valid_replicates', 'n/a')} |"
        )
    lines += [
        "",
        "## Monthly 1-hour means and observation counts",
        "",
        "| Month (UTC) | Group | n | Mean 1h % |",
        "|---|---|---:|---:|",
    ]
    one_hour = monthly.loc[monthly.horizon_minutes.eq(60)].sort_values(["month_utc", "group"])
    for row in one_hour.itertuples():
        lines.append(f"| {row.month_utc} | `{row.group}` | {row.n_included} | {_fmt(row.mean_return_pct)} |")
    lines += [
        "",
        "## Charts",
        "",
        "- `charts/mean_returns_by_group.png` — mean forward return by horizon and group.",
        "- `charts/monthly_1h_returns_and_counts.png` — monthly 1h means with monthly observation counts.",
        "- `charts/m15_alert_1h_distribution.png` — distribution of 1h returns after M15 alerts, with the other two populations shown for context.",
        "",
        "## Limitations",
        "",
        "- Signal-candle closes are bookkeeping reference points, not guaranteed execution prices.",
        "- No fee, spread, slippage, funding, fill, or position-size model is applied.",
        "- Overlapping observations are not independent; the reported `n` overstates independent evidence.",
        "- The populations were defined after the four-year history had already been examined, so this is development evidence.",
        "- No threshold, horizon, cooldown, or strategy rule was searched or changed.",
        "",
    ]
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.6f}"


def _pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2%}"


def _fmt_interval(value: Any) -> str:
    return "n/a" if not value else f"[{float(value[0]):.6f}, {float(value[1]):.6f}]"


def _contrast_difference(summary: dict[str, Any], contrast: dict[str, Any]) -> float | None:
    for cell in summary["horizon_summaries"]:
        if cell["horizon_minutes"] != contrast["horizon_minutes"]:
            continue
        left = cell["populations"][contrast["left"]]["mean_return_pct"]
        right = cell["populations"][contrast["right"]]["mean_return_pct"]
        if left is None or right is None:
            return None
        return float(left) - float(right)
    return None


def render_charts(
    observations_frame: pd.DataFrame,
    monthly: pd.DataFrame,
    chart_dir: Path,
) -> list[str]:
    """Three separate, explicitly descriptive charts."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    footer = "Descriptive signal research on signal-close forward returns. Not realized P&L."
    included = observations_frame.loc[observations_frame.included_both_horizons]

    figure, axis = plt.subplots(figsize=(9, 5))
    width = 0.26
    positions = np.arange(len(HORIZONS), dtype=float)
    for offset, group in enumerate(GROUPS):
        means: list[float] = []
        counts: list[int] = []
        for _, minutes in HORIZONS:
            cell = included.loc[included["group"].eq(group) & included.horizon_minutes.eq(minutes)]
            means.append(float(cell.return_pct.mean()) if len(cell) else np.nan)
            counts.append(len(cell))
        bars = axis.bar(positions + (offset - 1) * width, means, width, label=group)
        for bar, count in zip(bars, counts, strict=True):
            height = bar.get_height()
            axis.annotate(
                f"n={count}",
                (bar.get_x() + bar.get_width() / 2, height),
                textcoords="offset points",
                xytext=(0, 3 if height >= 0 else -12),
                ha="center",
                fontsize=8,
            )
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.set_xticks(positions, [horizon for horizon, _ in HORIZONS])
    axis.set_xlabel("Forward horizon (fixed)")
    axis.set_ylabel("Mean gross forward return (%)")
    axis.set_title(
        "BTC M15: mean subsequent return by horizon and comparison group\n"
        "four-year Binance USD-M BTC/USDT coverage"
    )
    axis.legend(title="Population", fontsize=8)
    axis.grid(axis="y", alpha=0.3)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(chart_dir / "mean_returns_by_group.png", dpi=150)
    plt.close(figure)
    written.append("mean_returns_by_group.png")

    monthly_one_hour = monthly.loc[monthly.horizon_minutes.eq(60)]
    months = sorted(monthly_one_hour.month_utc.unique())
    figure, (top, bottom) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, height_ratios=(2, 1))
    x = np.arange(len(months), dtype=float)
    for group in GROUPS:
        series = monthly_one_hour.loc[monthly_one_hour["group"].eq(group)].set_index("month_utc").reindex(months)
        top.plot(x, series.mean_return_pct, marker="o", markersize=3, linewidth=1.2, label=group)
        bottom.plot(x, series.n_included.fillna(0), marker="o", markersize=3, linewidth=1.2, label=group)
    top.axhline(0.0, color="black", linewidth=0.8)
    top.set_ylabel("Mean 1h gross return (%)")
    top.set_title("BTC M15: monthly 1-hour mean forward return and monthly observation counts")
    top.legend(fontsize=8, title="Population")
    top.grid(alpha=0.3)
    bottom.set_ylabel("Included observations")
    bottom.set_xlabel("Month (UTC)")
    bottom.grid(alpha=0.3)
    step = max(1, len(months) // 24)
    bottom.set_xticks(x[::step], [months[index] for index in range(0, len(months), step)], rotation=90, fontsize=7)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(chart_dir / "monthly_1h_returns_and_counts.png", dpi=150)
    plt.close(figure)
    written.append("monthly_1h_returns_and_counts.png")

    alerts = included.loc[included["group"].eq("m15_signal") & included.horizon_minutes.eq(60)].return_pct
    figure, (left, right) = plt.subplots(1, 2, figsize=(12, 5))
    left.hist(alerts, bins=60, color="#3b6ea5", edgecolor="white", linewidth=0.4)
    left.axvline(float(alerts.mean()), color="#b03030", linewidth=1.4, label=f"mean {alerts.mean():.4f}%")
    left.axvline(
        float(alerts.median()), color="#207020", linewidth=1.4, linestyle="--", label=f"median {alerts.median():.4f}%"
    )
    left.axvline(0.0, color="black", linewidth=0.8)
    left.set_xlabel("Gross 1-hour forward return after an M15 alert (%)")
    left.set_ylabel("Observation count")
    left.set_title(f"Distribution of 1h returns after M15 alerts (n={len(alerts)})")
    left.legend(fontsize=8)
    left.grid(axis="y", alpha=0.3)
    box_data = [
        included.loc[included["group"].eq(group) & included.horizon_minutes.eq(60)].return_pct.to_numpy()
        for group in GROUPS
    ]
    right.boxplot(box_data, tick_labels=list(GROUPS), showfliers=False)
    right.axhline(0.0, color="black", linewidth=0.8)
    right.set_ylabel("Gross 1-hour forward return (%)")
    right.set_title("Same 1h returns, all three populations (whiskers 1.5 IQR)")
    right.tick_params(axis="x", labelrotation=12, labelsize=8)
    right.grid(axis="y", alpha=0.3)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#444444")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(chart_dir / "m15_alert_1h_distribution.png", dpi=150)
    plt.close(figure)
    written.append("m15_alert_1h_distribution.png")
    return written


def run(baseline_run: Path, output_dir: Path, *, charts: bool = True) -> Path:
    baseline_run = baseline_run.resolve()
    original_identity = parent_identity(baseline_run)
    parent, parent_summary, parent_rows = load_parent(baseline_run)
    inputs = source_inputs(parent)
    signals = signal_close_times(parent_rows)
    window_start = datetime.fromisoformat(signals[0].replace("Z", "+00:00"))
    window_end = datetime.fromisoformat(signals[-1].replace("Z", "+00:00"))
    comparator = parent_summary["baseline_comparator"]["by_timeframe"][TIMEFRAME]
    if (
        comparator["matched_window_start_close_utc"] != signals[0]
        or comparator["matched_window_end_close_utc"] != signals[-1]
    ):
        raise ValueError("Parent matched 15m comparator window does not match its emitted M15 signal span")

    scan, audit = scan_population(inputs, window_start, window_end)
    verify_gate_consistency(scan)
    membership = group_membership(scan, signals)
    source = phase1._forward_index(inputs.frames[TIMEFRAME], TIMEFRAME)
    observation_frame = observations(scan, membership, source)
    verify_parent_returns(parent_rows, observation_frame)
    populations = {group: int(membership[group].sum()) for group in GROUPS}
    if not populations["m15_signal"]:
        raise ValueError("No emitted M15 alerts in the matched window")
    if not populations["m15_signal"] <= populations["gate_ready_no_cross"] <= populations["all_eligible_bars"]:
        raise ValueError("Population nesting is inconsistent with the documented rules")
    cooldown_suppressed = audit["cross_and_gates_bar_count"] - populations["m15_signal"]
    if cooldown_suppressed < 0:
        raise ValueError("More emitted alerts than cross-and-gate bars; the populations disagree")
    audit["cooldown_suppressed_bar_count"] = cooldown_suppressed
    audit["cooldown_suppressed_note"] = (
        "Cross-and-gate bars minus emitted alerts. The parent replay's own m15_cooldown_suppressed "
        "counter covers its full requested window, which can contain a few extra boundary bars."
    )
    logger.info("m15_signal_diagnostic_populations", **populations, cooldown_suppressed=cooldown_suppressed)

    summaries = horizon_summaries(observation_frame)
    monthly = monthly_summaries(observation_frame)
    uncertainty = contrast_uncertainty(observation_frame)
    excluded = observation_frame.loc[~observation_frame.included_both_horizons]
    summary = {
        "definition_version": VERSION,
        "alpha_assessment": "NOT_ASSESSED",
        "population_counts": populations,
        "horizon_summaries": summaries,
        "contrast_uncertainty": uncertainty,
        "excluded_observation_count": int(len(excluded)),
        "excluded_event_count": int(excluded.event_id.nunique()),
        "excluded_event_ids": sorted(excluded.event_id.unique().tolist())[:50],
        "limitations": [
            "Descriptive signal-close forward returns; not fills, fees, slippage or realized P&L.",
            "Overlapping observations are not independent trades and are never compounded.",
            "Post-selection development evidence over previously examined history.",
            "No threshold, horizon, or cooldown search was performed.",
        ],
    }
    timestamp = datetime.now(UTC)
    root = Path(__file__).resolve().parents[1]
    code_paths = [
        Path(__file__).resolve(),
        root / "app/backtest/btc_research_phase1.py",
        root / "app/backtest/signal_replay_preparation.py",
        root / "app/backtest/signal_replay_data.py",
        root / "app/trading/strategy/btc_rsi_cross_alert/m15_checker.py",
        root / "app/trading/strategy/btc_rsi_cross_alert/evaluator.py",
        root / "research/btc_m5_horizon_diagnostic.py",
    ]
    manifest = {
        "definition_version": VERSION,
        "completion_status": "SUCCESS",
        "alpha_assessment": "NOT_ASSESSED",
        "run_id": "",
        "generated_at_utc": phase1._utc_iso(timestamp),
        "command": f'python -m research.btc_m15_signal_diagnostic --baseline-run "{baseline_run}" --output-dir "{output_dir.resolve()}"'
        + ("" if charts else " --no-charts"),
        "parent": {
            "run_id": parent["run_id"],
            "path": str(baseline_run),
            "files_sha256": original_identity,
            "source_hash_parity": True,
            "signal_count": len(signals),
            "signal_ids_sha256": hashlib.sha256("\n".join(signals).encode()).hexdigest(),
            "cooldown": "Parent emitted M15 IDs retained unchanged; no replay and no cooldown reset",
        },
        "inputs": inputs.source_report,
        "environment": phase1._environment(),
        "scan": audit,
        "parent_replay_counts": parent_summary.get("replay_counts"),
        "population_counts": populations,
        "population_rules": {
            "m15_signal": "Emitted replay alerts: fresh RSI21 EMA9>WMA45 bullish cross on the current M15 bar with the previous bar EMA9<=WMA45, plus M15, H1 and H4 closes all strictly above their native EMA21; one-hour per-timeframe cooldown applied.",
            "gate_ready_no_cross": "Preparation READY and M15, H1 and H4 closes all strictly above their native EMA21; no RSI crossover requirement; no cooldown.",
            "all_eligible_bars": "Preparation READY only; no gate and no cooldown.",
            "complete_outcome_rule": "An observation enters every statistic only when its 1h and 4h exact targets are both COMPLETE; exact targets are never substituted and gaps are never bridged.",
            "horizons": [f"{minutes} minutes" for _, minutes in HORIZONS],
            "cooldown_note": "Only m15_signal carries the replay's one-hour cooldown; the other populations are unthinned event sets.",
        },
        "code_sha256": {str(path.relative_to(root)): phase1._hash_file(path) for path in code_paths},
        "definitions": {
            "return": "Gross exact close-to-close percentage = (exact target close / trigger close - 1) * 100",
            "status_values": list(phase1.OUTCOME_STATUSES),
            "uncertainty": "Reused paired circular 7-day UTC calendar blocks, 2000 replicates, seed 20260904, observation-weighted means; post-selection descriptive interval only",
            "month_timezone": "UTC",
        },
    }
    if original_identity != parent_identity(baseline_run):
        raise ValueError("Parent packet changed during the diagnostic")
    for timeframe, path in inputs.paths.items():
        if phase1._hash_file(path) != parent["inputs"]["files"][timeframe]["sha256"]:
            raise ValueError(f"Source changed during the diagnostic: {timeframe}")
    packet = output_dir.resolve() / (
        f"run_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{parent['inputs']['files'][TIMEFRAME]['sha256'][:8]}"
    )
    packet.mkdir(parents=True, exist_ok=False)
    manifest["run_id"] = packet.name
    observation_frame.to_csv(
        packet / "observations.csv", index=False, columns=list(OBSERVATION_FIELDS), quoting=csv.QUOTE_MINIMAL
    )
    scan.to_csv(packet / "bars.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    monthly.to_csv(packet / "monthly.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    for name, data in (("manifest", manifest), ("summary", summary)):
        (packet / f"{name}.json").write_text(
            json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
    written = render_charts(observation_frame, monthly, packet / "charts") if charts else []
    (packet / "report.md").write_text(render_report(summary, manifest, monthly), encoding="utf-8")
    logger.info(
        "m15_signal_diagnostic_complete", packet=str(packet), charts=written, alpha_assessment="NOT_ASSESSED"
    )
    return packet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-charts", action="store_true")
    arguments = parser.parse_args()
    run(arguments.baseline_run, arguments.output_dir, charts=not arguments.no_charts)
