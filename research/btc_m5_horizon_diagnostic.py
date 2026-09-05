"""Offline descriptive M5 horizon profiling of an immutable Phase 1 population."""

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
from app.trading.strategy.btc_rsi_cross_alert.models import PREPARATION_READY

HORIZONS = (60, 120, 180, 240)
VERSION = "btc-m5-horizon-diagnostic-v1"
SEED = 20260904
REPLICATES = 2000
PARENT_FILES = ("manifest.json", "signals.csv", "summary.json", "report.md")
logger = structlog.get_logger()


def parent_identity(directory: Path) -> dict[str, str]:
    return {name: phase1._hash_file(directory / name) for name in PARENT_FILES}


def load_parent(directory: Path) -> tuple[dict, dict, pd.DataFrame]:
    """Validate packet identity and collapse only its repeated horizon rows."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    if (manifest["run_id"] != directory.name or manifest["completion_status"] != "SUCCESS"
            or summary["completion_status"] != "SUCCESS"
            or manifest["definition_version"] != phase1.DEFINITION_VERSION
            or manifest["inputs"]["identity"]["venue_instrument"] != phase1.VENUE_INSTRUMENT):
        raise ValueError("Parent packet identity or completion contract does not match Phase 1")
    all_rows = pd.read_csv(directory / "signals.csv", keep_default_na=False)
    rows = all_rows.loc[all_rows.timeframe == "5m"].copy()
    invariant = ["sequence", "trigger_open_at", "trigger_close_at", "trigger_close_price"]
    if rows.empty or rows.groupby("event_id")[invariant].nunique().gt(1).any().any():
        raise ValueError("Parent M5 population is empty or has inconsistent signal identity")
    if any(sorted(group.horizon_minutes) != [60, 240, 720, 1440] for _, group in rows.groupby("event_id")):
        raise ValueError("Each parent M5 ID must have exactly the four Phase 1 horizons")
    signals = rows.drop_duplicates("event_id").sort_values("trigger_close_at")
    times = pd.to_datetime(signals.trigger_close_at, utc=True)
    if (len(signals) != summary["signal_counts"]["5m"] or times.duplicated().any()
            or times.diff().dropna().lt(pd.Timedelta(hours=1)).any()):
        raise ValueError("Parent M5 count, timestamp identity, or one-hour cooldown is inconsistent")
    return manifest, summary, rows


def profile(frame: pd.DataFrame, times: list[datetime], ids: list[str]) -> pd.DataFrame:
    """Exact future windows; exclude the trigger candle even from excursions."""
    source = phase1._forward_index(frame, "5m")
    high = frame.high.to_numpy(dtype=float)
    low = frame.low.to_numpy(dtype=float)
    rows = []
    for close_time, event_id in zip(times, ids, strict=True):
        position = source.position_by_close[close_time]
        price = float(source.closes[position])
        for minutes in HORIZONS:
            outcome = phase1._exact_forward_outcome_from_index(
                source, "5m", trigger_close=close_time, trigger_price=price, horizon_minutes=minutes,
            )
            mfe = mae = None
            if outcome["outcome_status"] == "COMPLETE":
                # Native exact-target validation proves these future rows are contiguous.
                end = position + minutes // 5 + 1
                mfe = max(0.0, (float(high[position + 1:end].max()) / price - 1) * 100)
                mae = min(0.0, (float(low[position + 1:end].min()) / price - 1) * 100)
            rows.append((event_id, phase1._utc_iso(close_time), price, minutes,
                         outcome["target_close_at"], outcome["target_close_price"], outcome["outcome_status"],
                         outcome["return_pct"], mfe, mae))
    data = pd.DataFrame(rows, columns=["event_id", "trigger_close_at", "trigger_close_price", "horizon_minutes",
                                      "target_close_at", "target_close_price", "outcome_status", "return_pct",
                                      "mfe_pct", "mae_pct"])
    complete_ids = data.groupby("event_id").outcome_status.agg(lambda values: values.eq("COMPLETE").all())
    data["included_all_horizons"] = data.event_id.map(complete_ids)
    return data


def eligible_baseline(inputs: phase1.ValidatedInputs, start: datetime, end: datetime) -> tuple[list, dict]:
    cache = phase1._cache_for(inputs)
    events = events_for_frame(inputs.frames["5m"], "5m", start, end)
    eligible, exclusions = [], Counter()
    for event in events:
        reason = cache.prepare(event, symbol=phase1.SYMBOL).reason
        if reason == PREPARATION_READY:
            eligible.append(event.close_time)
        else:
            exclusions[reason] += 1
    return eligible, {
        "window_start_close_utc": phase1._utc_iso(start), "window_end_close_utc": phase1._utc_iso(end),
        "candidate_bar_count": len(events), "eligible_bar_count": len(eligible),
        "preparation_excluded_count": sum(exclusions.values()), "preparation_exclusion_reasons": dict(exclusions),
    }


def verify_parent_returns(parent: pd.DataFrame, signals: pd.DataFrame) -> None:
    check = parent.loc[parent.horizon_minutes.isin((60, 240))].merge(
        signals, on=["event_id", "horizon_minutes"], suffixes=("_parent", "_current"), validate="one_to_one",
    )
    for field in ("trigger_close_at", "target_close_at", "outcome_status"):
        if not check[f"{field}_parent"].eq(check[f"{field}_current"]).all():
            raise ValueError(f"Parent exact-horizon parity failed: {field}")
    for field in ("trigger_close_price", "target_close_price", "return_pct"):
        left = pd.to_numeric(check[f"{field}_parent"], errors="coerce")
        right = pd.to_numeric(check[f"{field}_current"], errors="coerce")
        if not np.allclose(left, right, rtol=0, atol=1e-10, equal_nan=True):
            raise ValueError(f"Parent exact-horizon parity failed: {field}")


def metrics(rows: pd.DataFrame) -> dict[str, Any]:
    included = rows.loc[rows.included_all_horizons]
    return {
        "n_total": len(rows), "n_complete": int(rows.outcome_status.eq("COMPLETE").sum()),
        "n_matched": len(included), "status_counts": dict(Counter(rows.outcome_status)),
        "positive_return_share": float(included.return_pct.gt(0).mean()) if len(included) else None,
        **{f"{stat}_{field}": float(getattr(included[field], stat)()) if len(included) else None
           for field in ("return_pct", "mfe_pct", "mae_pct") for stat in ("mean", "median")},
    }


def paired_bootstrap(signal: pd.DataFrame, baseline: pd.DataFrame, *, seed: int = SEED) -> dict:
    """Resample paired calendar blocks, weighting sums by observation counts."""
    signal = signal.loc[signal.included_all_horizons]
    baseline = baseline.loc[baseline.included_all_horizons]
    days = pd.date_range(pd.to_datetime(baseline.trigger_close_at, utc=True).min().floor("D"),
                         pd.to_datetime(baseline.trigger_close_at, utc=True).max().floor("D"), freq="D")
    if len(days) < 7 or signal.empty:
        return {"status": "OMITTED", "reason": "Requires at least seven calendar days and matched signals"}
    daily = []
    for data in (signal, baseline):
        grouped = data.assign(day=pd.to_datetime(data.trigger_close_at, utc=True).dt.floor("D")).groupby("day").return_pct
        daily.append(grouped.agg(["sum", "count"]).reindex(days, fill_value=0).to_numpy())
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(days), size=(REPLICATES, (len(days) + 6) // 7))
    indices = ((starts[:, :, None] + np.arange(7)) % len(days)).reshape(REPLICATES, -1)[:, :len(days)]
    estimates = []
    for aggregates in daily:
        totals = aggregates[indices].sum(axis=1)
        estimates.append(np.divide(totals[:, 0], totals[:, 1], out=np.full(REPLICATES, np.nan), where=totals[:, 1] > 0))
    valid = np.isfinite(estimates[0]) & np.isfinite(estimates[1])
    return {
        "status": "DESCRIPTIVE" if valid.all() else "INCOMPLETE",
        "seed": seed, "replicates": REPLICATES, "valid_replicates": int(valid.sum()),
        "undefined_replicates": int((~valid).sum()),
        "calendar_days": len(days), "block_days": 7, "calendar_timezone": "UTC", "percentile_level": 0.95,
        "signal_mean_ci_pct": np.quantile(estimates[0][valid], [0.025, 0.975]).tolist() if valid.any() else None,
        "signal_minus_baseline_ci_pp": np.quantile((estimates[0] - estimates[1])[valid], [0.025, 0.975]).tolist() if valid.any() else None,
    }


def summarize(signal: pd.DataFrame, baseline: pd.DataFrame, bootstrap: bool) -> dict:
    horizons, monthly = [], []
    for minutes in HORIZONS:
        populations = [data.loc[data.horizon_minutes.eq(minutes)] for data in (signal, baseline)]
        sm, bm = map(metrics, populations)
        horizons.append({"horizon_minutes": minutes, "signal": sm, "baseline": bm,
                         "signal_minus_baseline_mean_pp": sm["mean_return_pct"] - bm["mean_return_pct"]
                         if sm["n_matched"] and bm["n_matched"] else None,
                         "bootstrap": paired_bootstrap(*populations) if bootstrap else {"status": "OMITTED"}})
        for label, data in zip(("signal", "baseline"), populations, strict=True):
            for month, group in data.groupby(data.trigger_close_at.str[:7]):
                monthly.append({"population": label, "month_utc": month, "horizon_minutes": minutes, **metrics(group)})
    return {"alpha_assessment": "NOT_ASSESSED", "horizon_summaries": horizons, "monthly_summaries": monthly,
            "excluded_signal_ids": sorted(signal.loc[~signal.included_all_horizons, "event_id"].unique().tolist()),
            "excluded_baseline_count": int(baseline.loc[~baseline.included_all_horizons, "event_id"].nunique())}


def report(summary: dict, manifest: dict) -> str:
    lines = ["# BTC M5 horizon diagnostic", "", "Preliminary result for the accepted parent's current coverage. Alpha assessment: `NOT_ASSESSED`. Descriptive historical profiling; no trained or untouched evaluation.", "",
             "The same all-four-complete signal IDs and all-four-complete eligible baseline bars enter every horizon statistic. Parent IDs and cooldown are retained without replay.",
             "", f"Parent: `{manifest['parent']['run_id']}`. Source hashes and original 1h/4h arithmetic verified.",
             f"Matched UTC window: `{manifest['comparator']['window_start_close_utc']}` through `{manifest['comparator']['window_end_close_utc']}`.",
             f"Preparation exclusions: {manifest['comparator']['preparation_excluded_count']}; horizon-excluded signals: {len(summary['excluded_signal_ids'])}; horizon-excluded baseline bars: {summary['excluded_baseline_count']}.", "",
             "| Horizon | Signal n | Mean % | Median % | Positive share | Baseline n | Baseline mean % | Difference pp |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in summary["horizon_summaries"]:
        s, b = item["signal"], item["baseline"]
        lines.append(f"| {item['horizon_minutes'] // 60}h | {s['n_matched']} | {s['mean_return_pct']:.6f} | {s['median_return_pct']:.6f} | {s['positive_return_share']:.2%} | {b['n_matched']} | {b['mean_return_pct']:.6f} | {item['signal_minus_baseline_mean_pp']:.6f} |")
    lines += ["", "## Cumulative future excursions", "", "MFE=max(0, future high/entry−1); MAE=min(0, future low/entry−1), in percent. Only bars opening at or after signal close and closing at or before exact target close are used. These are hindsight bounds, not captured P&L; longer windows mechanically contain more opportunities and risks.", "",
              "| Horizon | Mean MFE % | Median MFE % | Mean MAE % | Median MAE % |",
              "|---|---:|---:|---:|---:|"]
    for item in summary["horizon_summaries"]:
        s = item["signal"]
        lines.append(f"| {item['horizon_minutes'] // 60}h | {s['mean_mfe_pct']:.6f} | {s['median_mfe_pct']:.6f} | {s['mean_mae_pct']:.6f} | {s['median_mae_pct']:.6f} |")
    lines += ["", "## Descriptive uncertainty", "", "Paired circular 7-day UTC calendar blocks use the same draws for signal and baseline, including zero-signal days. Each replicate divides sampled return sums by sampled observation counts. Percentile intervals do not adjust for prior exploration or horizon selection and support no significance or alpha claim."]
    for item in summary["horizon_summaries"]:
        ci = item["bootstrap"]
        lines.append(f"- {item['horizon_minutes'] // 60}h: {json.dumps(ci, sort_keys=True)}")
    lines += ["", "## Audit and limitations", "", "`signals.csv` and `baseline.csv` contain every eligible event/horizon, original status, and all-horizon inclusion flag. Exact statuses are COMPLETE, INCOMPLETE_TAIL, MISSING_TARGET, GAP; no later target or partial excursion is substituted. `summary.json` includes monthly UTC count/mean, statuses, and both populations' return/excursion summaries. Preparation failures are recorded separately in the manifest.", "",
              "Gross close-to-close returns omit fees, spreads, slippage, funding, fills and overlapping-position constraints. The comparator uses per-event preparation only, without signal gates or cooldown. No per-signal best-horizon choice, parameter sweep, live filter, or strategy change is made.", ""]
    return "\n".join(lines)


def run(baseline_run: Path, output_dir: Path, *, bootstrap: bool = True) -> Path:
    baseline_run = baseline_run.resolve()
    original_identity = parent_identity(baseline_run)
    parent, _, parent_rows = load_parent(baseline_run)
    files = parent["inputs"]["files"]
    inputs = phase1.validate_inputs(Path(files["5m"]["path"]).parent)
    for timeframe in phase1.TIMEFRAMES:
        if inputs.source_report["files"][timeframe]["sha256"] != files[timeframe]["sha256"]:
            raise ValueError(f"Source hash differs from parent: {timeframe}")
    unique = parent_rows.drop_duplicates("event_id").sort_values("trigger_close_at")
    times = pd.to_datetime(unique.trigger_close_at, utc=True).dt.to_pydatetime().tolist()
    signal = profile(inputs.frames["5m"], times, unique.event_id.tolist())
    verify_parent_returns(parent_rows, signal)
    logger.info("m5_horizon_signals_verified", signals=len(unique))
    eligible, comparator = eligible_baseline(inputs, min(times), max(times))
    if not set(times).issubset(eligible):
        raise ValueError("Parent signal failed current shared point-in-time preparation")
    if not eligible:
        raise ValueError("No eligible matched baseline bars")
    baseline = profile(inputs.frames["5m"], eligible, ["bar_" + phase1._utc_iso(value) for value in eligible])
    logger.info("m5_horizon_baseline_profiled", eligible_bars=len(eligible))
    if not signal.included_all_horizons.any() or not baseline.included_all_horizons.any():
        raise ValueError("No all-four-complete comparison population")
    summary = summarize(signal, baseline, bootstrap)
    timestamp = datetime.now(UTC)
    packet = output_dir.resolve() / f"run_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{files['5m']['sha256'][:8]}"
    root = Path(__file__).resolve().parents[1]
    code_paths = [Path(__file__).resolve(), root / "app/backtest/btc_research_phase1.py",
                  root / "app/backtest/signal_replay_preparation.py", root / "app/backtest/signal_replay_data.py"]
    manifest = {"definition_version": VERSION, "completion_status": "SUCCESS", "alpha_assessment": "NOT_ASSESSED",
                "run_id": packet.name, "generated_at_utc": phase1._utc_iso(timestamp),
                "command": f"python -m research.btc_m5_horizon_diagnostic --baseline-run \"{baseline_run}\" --output-dir \"{output_dir.resolve()}\"" + (" --no-bootstrap" if not bootstrap else ""),
                "parent": {"run_id": parent["run_id"], "path": str(baseline_run), "files_sha256": original_identity,
                           "source_hash_parity": True, "one_hour_four_hour_parity": True,
                           "signal_ids_sha256": hashlib.sha256("\n".join(unique.event_id).encode()).hexdigest(),
                           "signal_count": len(unique), "cooldown": "Parent emitted IDs retained; no replay or reset"},
                "inputs": inputs.source_report, "environment": phase1._environment(), "comparator": comparator,
                "code_sha256": {str(path.relative_to(root)): phase1._hash_file(path) for path in code_paths},
                "definitions": {"horizons_minutes": list(HORIZONS), "return": "Gross exact close-to-close percent",
                                "excursions": "Future native M5 bars only, first open=trigger close, last close=target; MFE >= 0, MAE <= 0; hindsight bounds, not captured P&L",
                                "population": "Fixed parent M5 IDs; same complete IDs across all four horizons. Baseline uses same first/last signal window, shared per-event READY preparation, and all-four-complete rows.",
                                "bootstrap": "Optional 2000 paired circular 7-day UTC calendar-block replicates, seed 20260904; percentile 95%; observation-weighted means; no significance claim",
                                "status_values": list(phase1.OUTCOME_STATUSES), "month_timezone": "UTC"}}
    if original_identity != parent_identity(baseline_run):
        raise ValueError("Parent packet changed during diagnostic")
    for timeframe, path in inputs.paths.items():
        if phase1._hash_file(path) != files[timeframe]["sha256"]:
            raise ValueError(f"Source changed during diagnostic: {timeframe}")
    packet.mkdir(parents=True, exist_ok=False)
    for name, data in (("signals", signal), ("baseline", baseline)):
        data.to_csv(packet / f"{name}.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    for name, data in (("manifest", manifest), ("summary", summary)):
        (packet / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (packet / "report.md").write_text(report(summary, manifest), encoding="utf-8")
    logger.info("m5_horizon_diagnostic_complete", packet=str(packet), alpha_assessment="NOT_ASSESSED")
    return packet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-bootstrap", action="store_true")
    args = parser.parse_args()
    run(args.baseline_run, args.output_dir, bootstrap=not args.no_bootstrap)
