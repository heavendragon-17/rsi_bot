"""Describe an M5 horizon packet by year and causally available daily regimes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from app.backtest import btc_research_phase1 as phase1
from app.backtest.signal_replay_data import load_ohlcv_csv

VERSION = "btc-m5-regime-review-v1"
START = pd.Timestamp("2022-08-28T00:00:00Z")
END = pd.Timestamp("2026-08-28T00:00:00Z")
logger = structlog.get_logger()


def daily_context(h1: pd.DataFrame) -> pd.DataFrame:
    """Use only complete UTC days; each row becomes available at its close."""
    close_index = pd.DatetimeIndex(h1.index).tz_convert("UTC") + pd.Timedelta(hours=1)
    if not close_index.is_unique or not close_index.is_monotonic_increasing:
        raise ValueError("H1 timestamps must be sorted and unique")
    if len(close_index) > 1 and not ((close_index[1:] - close_index[:-1]) == pd.Timedelta(hours=1)).all():
        raise ValueError("Regime input has an H1 cadence gap")
    hourly = pd.Series(h1.close.to_numpy(dtype=float), index=close_index)
    daily = hourly.resample("1D", closed="right", label="right").agg(["last", "count"])
    close = daily["last"].where(daily["count"].eq(24))
    returns = close.pct_change(fill_method=None)
    trend_return = close.pct_change(90, fill_method=None) * 100
    vol = returns.rolling(30, min_periods=30).std(ddof=1) * np.sqrt(365) * 100
    ready = close.notna().rolling(91, min_periods=91).sum().eq(91) & vol.notna()
    result = pd.DataFrame({"daily_close": close, "return_90d_pct": trend_return,
                           "volatility_30d_annualized_pct": vol})
    result["trend"] = np.select([trend_return.gt(10), trend_return.lt(-10)], ["UP", "DOWN"], default="SIDEWAYS")
    result["volatility"] = np.where(vol.ge(60), "HIGH", "LOW")
    result.loc[~ready, ["trend", "volatility"]] = "UNAVAILABLE"
    result.index.name = "available_at"
    return result.reset_index()


def attach_labels(rows: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    result = rows.copy()
    result["trigger_close_at"] = pd.to_datetime(result.trigger_close_at, utc=True)
    if not result.trigger_close_at.ge(START).all() or not result.trigger_close_at.lt(END).all():
        raise ValueError("Horizon packet contains triggers outside the frozen four-year window")
    result = pd.merge_asof(result.sort_values("trigger_close_at"), context.sort_values("available_at"),
                           left_on="trigger_close_at", right_on="available_at", direction="backward")
    for column in ("trend", "volatility"):
        result[column] = result[column].fillna("UNAVAILABLE")
    result["regime"] = result.trend + " / " + result.volatility
    result["calendar_year"] = result.trigger_close_at.dt.year.astype(str)
    boundaries = [START + pd.DateOffset(years=year) for year in range(5)]
    result["study_year"] = pd.cut(result.trigger_close_at, boundaries, right=False,
                                  labels=["2022-08 to 2023-08", "2023-08 to 2024-08",
                                          "2024-08 to 2025-08", "2025-08 to 2026-08"]).astype(str)
    return result


def grouped_metrics(rows: pd.DataFrame, population: str) -> list[dict]:
    complete = rows.loc[rows.included_all_horizons.eq(True)]
    output = []
    for grouping in ("calendar_year", "study_year", "trend", "volatility", "regime"):
        for (group, horizon), sample in complete.groupby([grouping, "horizon_minutes"], observed=True):
            output.append({"population": population, "grouping": grouping, "group": str(group),
                           "horizon_minutes": int(horizon), "n": len(sample),
                           "mean_return_pct": float(sample.return_pct.mean()),
                           "median_return_pct": float(sample.return_pct.median()),
                           "positive_return_share": float(sample.return_pct.gt(0).mean()),
                           "mean_mfe_pct": float(sample.mfe_pct.mean()),
                           "mean_mae_pct": float(sample.mae_pct.mean())})
    return output


def run(horizon_run: Path, output_dir: Path) -> Path:
    parent = json.loads((horizon_run / "manifest.json").read_text(encoding="utf-8"))
    identities = {name: phase1._hash_file(horizon_run / name)
                  for name in ("manifest.json", "signals.csv", "baseline.csv", "summary.json")}
    h1_facts = parent["inputs"]["files"]["1h"]
    h1_path = Path(h1_facts["path"])
    if phase1._hash_file(h1_path) != h1_facts["sha256"]:
        raise ValueError("H1 source changed since horizon profiling")
    context = daily_context(load_ohlcv_csv(h1_path, "1h"))
    summaries, signal_labels, unavailable = [], None, {}
    for name in ("signals", "baseline"):
        rows = pd.read_csv(horizon_run / f"{name}.csv")
        labels = attach_labels(rows, context)
        if labels.duplicated(["event_id", "horizon_minutes"]).any():
            raise ValueError("Duplicate event/horizon rows")
        unavailable[name] = int(labels.loc[labels.trend.eq("UNAVAILABLE"), "event_id"].nunique())
        summaries.extend(grouped_metrics(labels, name))
        if name == "signals":
            signal_labels = labels
        del rows, labels
    grouped = pd.DataFrame(summaries)
    baseline = grouped.loc[grouped.population.eq("baseline")].set_index(["grouping", "group", "horizon_minutes"])
    table = grouped.loc[grouped.population.eq("signals")].copy()
    table["baseline_mean_return_pct"] = [baseline.loc[(r.grouping, r.group, r.horizon_minutes), "mean_return_pct"]
                                          for r in table.itertuples()]
    table["signal_minus_baseline_pp"] = table.mean_return_pct - table.baseline_mean_return_pct
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    packet = output_dir.resolve() / f"run_{stamp}"
    manifest = {"definition_version": VERSION, "completion_status": "SUCCESS",
                "operational_status": "INCOMPLETE" if any(unavailable.values()) else "VALID",
                "alpha_assessment": "NOT_ASSESSED", "unavailable_regime_event_counts": unavailable,
                "parent_path": str(horizon_run.resolve()), "parent_sha256": identities,
                "h1_sha256": h1_facts["sha256"], "code_sha256": phase1._hash_file(Path(__file__)),
                "environment": phase1._environment(), "signal_window": {"start_inclusive": str(START), "end_exclusive": str(END)},
                "regimes": {"trend": "Last complete UTC day close / close 90 days earlier: >10% UP, <-10% DOWN, otherwise SIDEWAYS",
                            "volatility": "30 daily simple returns sample standard deviation * sqrt(365): >=60% HIGH, otherwise LOW"},
                "limitations": ["Fixed descriptive labels, not optimized filters or proof of a complete market cycle",
                                "2022 and 2026 calendar years are partial; study years are August-to-August",
                                "Subgroups overlap, sample sizes vary, and no subgroup confidence/significance claim is made",
                                "Gross signal-close returns and hindsight excursions are not executable P&L"]}
    for name, digest in identities.items():
        if phase1._hash_file(horizon_run / name) != digest:
            raise ValueError("Parent packet changed during regime review")
    packet.mkdir(parents=True, exist_ok=False)
    signal_labels.to_csv(packet / "signals_with_regimes.csv", index=False)
    grouped.to_csv(packet / "population_summaries.csv", index=False)
    table.to_csv(packet / "comparison.csv", index=False)
    (packet / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# BTC M5 four-year regime review", "", "Alpha: NOT_ASSESSED. Gross event-return diagnostics; no executable P&L.",
             "Regimes use only the last complete UTC day available when the signal closes.",
             "2022/2026 calendar years are partial. August-to-August study years cover the requested four-year interval.", ""]
    for grouping in ("calendar_year", "study_year", "regime"):
        lines += [f"## {grouping.replace('_', ' ').title()}", "",
                  "| Group | Horizon | N | Mean % | Median % | Positive | Baseline mean % | Difference pp |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for row in table.loc[table.grouping.eq(grouping)].itertuples():
            lines.append(f"| {row.group} | {row.horizon_minutes // 60}h | {row.n} | {row.mean_return_pct:.6f} | {row.median_return_pct:.6f} | {row.positive_return_share:.1%} | {row.baseline_mean_return_pct:.6f} | {row.signal_minus_baseline_pp:.6f} |")
        lines.append("")
    lines += ["## Limitations", "", *[f"- {value}" for value in manifest["limitations"]],
              f"- Unavailable regime events: {unavailable}.", ""]
    (packet / "report.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("m5_regime_review_complete", packet=str(packet), status=manifest["operational_status"])
    return packet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.horizon_run, args.output_dir)
