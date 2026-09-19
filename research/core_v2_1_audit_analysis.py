"""Core V2.1 rule/data audit analysis and chart generation (research-only).

Consumes a completed point-in-time replay ledger produced by the *existing*
:mod:`app.backtest.core_v2_1` engine plus the same validated M15 source
frames, and produces signal counts (immediate-long vs pullback-long
families), coverage exclusions, and representative point-in-time decision
charts (closed candles only). It never places orders, never calls a data
provider, and never computes P&L.

Usage (repo root, project conda env), paths abbreviated:

    python research/core_v2_1_audit_analysis.py
        --run-dir research/results/core_v2_1_audit_replay
        --data-dir app/backtest/data
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.backtest.core_v2_1.coverage import scan_local_coverage  # noqa: E402
from app.trading.strategy.core_v2_1 import (  # noqa: E402
    FEATURE_ANCHOR_M15_OPEN,
    first_fully_covered_close,
)

EXPECTED_CSV_COLUMNS = (
    "sequence",
    "trigger_closed_at",
    "symbol",
    "venue",
    "status",
    "event_type",
    "decision_kind",
    "reasons",
    "context_closed_at_json",
    "state_before_json",
    "decision_json",
    "state_after_json",
)

PUBLIC_EVENT_TYPES = (
    "A_PLUS_LONG",
    "WAIT_FOR_PULLBACK",
    "PULLBACK_LONG",
    "WAIT_CANCELLED",
    "WAIT_EXPIRED",
)
IMMEDIATE_LONG_FAMILY = ("A_PLUS_LONG",)
PULLBACK_LONG_FAMILY = (
    "WAIT_FOR_PULLBACK",
    "PULLBACK_LONG",
    "WAIT_CANCELLED",
    "WAIT_EXPIRED",
)

EVENT_CHART_COLOR = {
    "A_PLUS_LONG": "#1a7f37",
    "PULLBACK_LONG": "#0a6ed1",
    "WAIT_CANCELLED": "#cf222e",
    "WAIT_EXPIRED": "#9a6700",
    "WAIT_FOR_PULLBACK": "#8250df",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()

def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_CSV_COLUMNS:
            raise ValueError(
                f"{path.name} header drifted from the expected replay ledger columns: "
                f"{reader.fieldnames!r}"
            )
        return list(reader)


def _counts(rows: Iterable[dict[str, str]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = row[key] or "(none)"
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda item: (-item[1], item[0])))


def _coverage_exclusions(data_dir: Path) -> dict[str, Any]:
    report = scan_local_coverage(data_dir, validate=True)
    universe = set(report.available_symbols) | set(report.missing_symbols) | set(
        report.invalid_symbols
    )
    excluded_csvs: list[str] = []
    for csv_path in sorted(data_dir.glob("*.csv")):
        stem = csv_path.stem.upper()
        symbol = stem.rsplit("_", 1)[0] if "_" in stem else stem
        if symbol in universe or symbol == "BTCUSDT":
            continue
        reason = (
            "non-M15 timeframe file (replay derives H1/H4 from M15)"
            if stem.endswith(("_5M", "_1H", "_4H"))
            else "symbol not in the locked Core V2.1 trade-candidate universe"
        )
        excluded_csvs.append(f"{csv_path.name}: {reason}")
    return {
        "required_candidates": report.required_count,
        "available_count": len(report.available_symbols),
        "available_symbols": list(report.available_symbols),
        "missing_symbols": list(report.missing_symbols),
        "invalid_symbols": list(report.invalid_symbols),
        "benchmark_available": report.benchmark_available,
        "benchmark_valid": report.benchmark_valid,
        "common_first_open_at": report.common_first_open_at,
        "common_last_closed_at": report.common_last_closed_at,
        "excluded_csv_files": excluded_csvs,
        "files": [
            {
                "symbol": item.symbol,
                "venue": item.venue,
                "present": item.present,
                "valid": item.valid,
                "rows": item.rows,
                "first_open_at": item.first_open_at,
                "last_closed_at": item.last_closed_at,
                "error": item.error,
            }
            for item in report.files
        ],
    }


def _verify_metadata(metadata_path: Path, event_counts: dict[str, int]) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    recorded = metadata.get("event_counts") or metadata.get("public_event_counts") or {}
    mismatches = {
        key: {"metadata": recorded.get(key, 0), "recount": event_counts.get(key, 0)}
        for key in set(recorded) | set(event_counts)
        if recorded.get(key, 0) != event_counts.get(key, 0)
    }
    return {
        "metadata_path": str(metadata_path),
        "metadata_sha256": _sha256_file(metadata_path),
        "window_mode": metadata.get("window_mode"),
        "run_start": metadata.get("run_start"),
        "run_end": metadata.get("run_end"),
        "ledger_records": metadata.get("ledger_records"),
        "event_counts_match_recount": not mismatches,
        "event_count_mismatches": mismatches,
    }


def _csv_frame(frame: pd.DataFrame, digits: int = 10) -> str:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n", float_format=f"%.{digits}g")
    return buffer.getvalue()

def _representative_events(events: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Pick deterministic representative events (no randomness, stable order)."""

    picks: dict[str, dict[str, str]] = {}
    a_plus = events[events["event_type"] == "A_PLUS_LONG"].sort_values(
        ["trigger_closed_at", "symbol"]
    )
    if not a_plus.empty:
        row = a_plus.iloc[len(a_plus) // 2]
        picks["a_plus_long"] = {
            "symbol": str(row["symbol"]),
            "trigger_closed_at": str(row["trigger_closed_at"]),
        }
    pullback = events[events["event_type"] == "PULLBACK_LONG"].sort_values(
        ["trigger_closed_at", "symbol"]
    )
    if not pullback.empty:
        first = pullback.iloc[0]
        last = pullback.iloc[-1]
        picks["pullback_long_first"] = {
            "symbol": str(first["symbol"]),
            "trigger_closed_at": str(first["trigger_closed_at"]),
        }
        picks["pullback_long_last"] = {
            "symbol": str(last["symbol"]),
            "trigger_closed_at": str(last["trigger_closed_at"]),
        }
    return picks


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    return plt, mdates


def _render_event_chart(
    *,
    m15: pd.DataFrame,
    center: pd.Timestamp,
    symbol: str,
    title: str,
    event_markers: pd.DataFrame,
    out_path: Path,
    window_before: int = 36,
    window_after: int = 20,
    level_lines: dict[str, float] | None = None,
    level_note: str | None = None,
) -> None:
    plt, mdates = _matplotlib()
    index = m15.index
    loc = index.searchsorted(center)
    window = m15.iloc[max(0, loc - window_before) : loc + window_after]
    if window.empty:
        raise ValueError(f"{symbol}: empty chart window around {center}")

    figure, axis = plt.subplots(figsize=(11, 5.2))
    axis.plot(window.index, window["close"], color="#1f2328", lw=1.2, label="M15 close")
    axis.plot(window.index, window["ema21"], color="#0a6ed1", lw=1.0, label="EMA21")
    axis.plot(window.index, window["ema200"], color="#6e7781", lw=0.9, ls="--", label="EMA200")

    for _, marker in event_markers.iterrows():
        ts = pd.Timestamp(marker["trigger_closed_at"])
        if ts < window.index[0] or ts > window.index[-1]:
            continue
        etype = marker["event_type"]
        color = EVENT_CHART_COLOR.get(etype, "#57606a")
        price = m15.loc[ts, "close"] if ts in m15.index else float(window["close"].iloc[-1])
        axis.scatter([ts], [price], color=color, zorder=5, s=46)
        axis.annotate(
            etype,
            (ts, price),
            textcoords="offset points",
            xytext=(0, 8),
            fontsize=7,
            color=color,
        )
    if level_lines:
        for label, value in level_lines.items():
            axis.axhline(value, color="#9a6700", lw=0.8, ls=":")
            axis.text(
                window.index[0], value, f" {label}", fontsize=7, color="#9a6700", va="bottom"
            )
    if level_note:
        axis.text(0.01, 0.02, level_note, transform=axis.transAxes, fontsize=7, color="#57606a")
    axis.set_title(title, fontsize=10)
    axis.legend(loc="upper left", fontsize=8)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=window.index.tz))
    figure.autofmt_xdate()
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=150)
    plt.close(figure)

def _render_event_timeline(events: pd.DataFrame, out_path: Path) -> None:
    plt, _mdates = _matplotlib()
    figure, axis = plt.subplots(figsize=(11, 4.4))
    for etype in PUBLIC_EVENT_TYPES:
        subset = events[events["event_type"] == etype]
        if subset.empty:
            continue
        axis.scatter(
            pd.to_datetime(subset["trigger_closed_at"], utc=True),
            [etype] * len(subset),
            s=10,
            color=EVENT_CHART_COLOR[etype],
            label=etype,
        )
    axis.set_title("Core V2.1 public events over the common replay window (UTC)", fontsize=10)
    axis.legend(loc="upper right", fontsize=7, markerscale=1.6)
    axis.grid(axis="x", alpha=0.25)
    figure.autofmt_xdate()
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=150)
    plt.close(figure)


def _build_events_frame(ledger: pd.DataFrame) -> pd.DataFrame:
    event_rows = ledger[ledger["event_type"] != ""].copy()
    events = event_rows[["sequence", "trigger_closed_at", "symbol", "venue", "event_type"]].copy()
    events["family"] = events["event_type"].map(
        lambda et: "immediate_long"
        if et in IMMEDIATE_LONG_FAMILY
        else ("pullback_long" if et in PULLBACK_LONG_FAMILY else "other")
    )
    trade_levels: list[dict[str, Any]] = []
    wait_bars: list[Any] = []
    for raw in event_rows["decision_json"]:
        decision = json.loads(raw)
        event = decision.get("event") or {}
        levels = event.get("trade_levels")
        trade_levels.append(levels if isinstance(levels, dict) else {})
        wait_bars.append(event.get("wait_bars_elapsed"))
    for key in ("reference_entry", "reference_stop", "risk_1r", "tp1", "tp2", "tp3"):
        events[key] = [levels.get(key) for levels in trade_levels]
    events["wait_bars_elapsed"] = wait_bars
    return events.sort_values("sequence").reset_index(drop=True)

def _render_charts(run_dir: Path, data_dir: Path, events: pd.DataFrame) -> list[str]:
    from app.backtest.core_v2_1.replay import build_replay_frames, load_available_universe

    source = load_available_universe(data_dir, require_all=True)
    frames = build_replay_frames(source)
    picks = _representative_events(events)
    charts_dir = run_dir / "charts"
    rendered: list[str] = []

    timeline_path = charts_dir / "event_timeline.png"
    _render_event_timeline(events, timeline_path)
    rendered.append(str(timeline_path))

    for name, pick in picks.items():
        symbol = pick["symbol"]
        center = pd.Timestamp(pick["trigger_closed_at"])
        symbol_events = events[events["symbol"] == symbol].copy()
        start = center - pd.Timedelta(hours=12)
        finish = center + pd.Timedelta(hours=6)
        event_ts = pd.to_datetime(symbol_events["trigger_closed_at"], utc=True)
        window_events = symbol_events[(event_ts >= start) & (event_ts <= finish)]
        level_lines: dict[str, float] = {}
        level_note = (
            "Reference levels are advisory signal outputs; no order or fill is modeled."
        )
        if name == "a_plus_long":
            row = symbol_events[
                (symbol_events["event_type"] == "A_PLUS_LONG")
                & (symbol_events["trigger_closed_at"] == pick["trigger_closed_at"])
            ]
            if not row.empty:
                record = row.iloc[0]
                for key, label in (
                    ("reference_entry", "ref entry"),
                    ("reference_stop", "ref stop"),
                    ("tp1", "TP1 (1R)"),
                    ("tp2", "TP2 (2R)"),
                    ("tp3", "TP3 (3R)"),
                ):
                    if record.get(key):
                        level_lines[label] = float(record[key])
        _render_event_chart(
            m15=frames.alt_m15[symbol],
            center=center,
            symbol=symbol,
            title=(
                f"{symbol} - {name} at {pick['trigger_closed_at']} "
                "(point-in-time, closed candles)"
            ),
            event_markers=window_events,
            out_path=charts_dir / f"{name}.png",
            level_lines=level_lines or None,
            level_note=level_note,
        )
        rendered.append(str(charts_dir / f"{name}.png"))
    return rendered

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    run_dir: Path = args.run_dir
    csv_path = run_dir / "core_v2_1_replay.csv"
    metadata_path = run_dir / "core_v2_1_replay.metadata.json"
    if not csv_path.is_file() or not metadata_path.is_file():
        raise SystemExit(f"replay outputs missing under {run_dir}; run the replay first")

    rows = _read_csv_rows(csv_path)
    ledger = pd.DataFrame(rows)
    not_ready = ledger[ledger["status"] == "not_ready"]
    evaluated = ledger[ledger["status"] == "evaluated"]
    events = _build_events_frame(ledger)

    event_counts = _counts(events.to_dict("records"), "event_type")
    decision_counts = _counts(evaluated.to_dict("records"), "decision_kind")
    not_ready_reasons: dict[str, int] = {}
    for raw in not_ready["decision_json"]:
        for reason in json.loads(raw).get("reasons", []):
            not_ready_reasons[reason] = not_ready_reasons.get(reason, 0) + 1

    coverage = _coverage_exclusions(args.data_dir)
    metadata_check = _verify_metadata(metadata_path, event_counts)

    per_symbol = (
        events.groupby(["symbol", "event_type"]).size().unstack(fill_value=0).reset_index()
    )
    family_summary = {
        "immediate_long": int((events["family"] == "immediate_long").sum()),
        "pullback_long_family_events": int((events["family"] == "pullback_long").sum()),
        "pullback_cycles_opened": int((events["event_type"] == "WAIT_FOR_PULLBACK").sum()),
        "pullback_confirmed": int((events["event_type"] == "PULLBACK_LONG").sum()),
        "pullback_cancelled": int((events["event_type"] == "WAIT_CANCELLED").sum()),
        "pullback_expired": int((events["event_type"] == "WAIT_EXPIRED").sum()),
    }

    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "input_csv_sha256": _sha256_file(csv_path),
        "ledger_rows": len(ledger),
        "evaluated_rows": len(evaluated),
        "not_ready_rows": len(not_ready),
        "public_event_rows": len(events),
        "event_counts": event_counts,
        "family_summary": family_summary,
        "decision_kind_counts": decision_counts,
        "not_ready_reasons": dict(
            sorted(not_ready_reasons.items(), key=lambda item: (-item[1], item[0]))
        ),
        "events_per_symbol": {
            str(row["symbol"]): {
                key: int(row[key]) for key in row.index if key != "symbol" and row[key]
            }
            for _, row in per_symbol.iterrows()
        },
        "coverage": coverage,
        "metadata_check": metadata_check,
        "feature_anchor_m15_open": pd.Timestamp(FEATURE_ANCHOR_M15_OPEN).isoformat(),
        "first_complete_closes": {
            tf: pd.Timestamp(first_fully_covered_close(tf)).isoformat()
            for tf in ("15m", "1h", "4h")
        },
    }

    rendered = _render_charts(run_dir, args.data_dir, events)
    summary["charts"] = rendered
    summary_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    _atomic_write(run_dir / "analysis_summary.json", summary_text)
    _atomic_write(run_dir / "events.csv", _csv_frame(events))
    _atomic_write(
        run_dir / "coverage_exclusions.json",
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(
        run_dir / "manifest.json",
        json.dumps(
            {
                "outputs": {
                    "analysis_summary.json": _sha256_text(summary_text),
                    "events.csv": _sha256_file(run_dir / "events.csv"),
                    "coverage_exclusions.json": _sha256_file(run_dir / "coverage_exclusions.json"),
                    "charts": {Path(p).name: _sha256_file(Path(p)) for p in rendered},
                },
                "inputs": {
                    "core_v2_1_replay.csv": _sha256_file(csv_path),
                    "core_v2_1_replay.metadata.json": _sha256_file(metadata_path),
                },
                "code": {
                    "research/core_v2_1_audit_analysis.py": _sha256_file(Path(__file__).resolve()),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    print(
        json.dumps(
            {"event_counts": event_counts, "family_summary": family_summary},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())