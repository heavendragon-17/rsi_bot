"""Novel M5 diagnostic: UTC hour-of-day seasonality in 60-minute returns.

Absent from the existing catalog (four-horizon profiling, regime review,
monthly summaries): this diagnostic splits eligible 5-minute bars by UTC
hour of decision close into a pre-declared target window (13-16 UTC, US
cash open) versus all other hours, using the exact 60-minute forward
close-to-close return. Point-in-time rule: available_at_utc equals
decision_time_utc (the candle close is known at its close; no later
information is used). Missing exact horizons never substitute a later
candle; gapped or missing targets are excluded with retained counts.

The script follows the fixed runner template: ``argv = [interpreter,
script_path, parameters_path, output_dir]`` with ``shell=False``. It reads
a typed JSON parameters file and writes ``candidate.csv``,
``baseline.csv``, ``summary.json`` and ``result.json`` into the assigned
output directory. No network, provider, trading or deployment action
occurs here.

Parameters JSON schema::

    {"candles_path": "<absolute 5m CSV>",
     "horizon_minutes": 60,
     "target_hours_utc": [13, 14, 15, 16],
     "available_lag_minutes": 0}

Output ``result.json`` carries ``{"verdict": "succeeded"|"rejected"}``
where ``succeeded`` means candidate mean exceeds baseline mean.
Scientific validity is assessed only by the frozen
``research.m5_checks`` verifier; process success alone is insufficient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "m5-hour-seasonality-v1"
REQUIRED_HORIZON = 60
REQUIRED_HOURS = (13, 14, 15, 16)
WINDOW_START = pd.Timestamp("2022-08-28T00:00:00Z")
WINDOW_END = pd.Timestamp("2026-08-28T00:00:00Z")


def load_candles(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, encoding="utf-8-sig")
    strings = frame["timestamp"].astype(str)
    if not strings.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError("candles.timestamp must carry explicit timezone offsets")
    stamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True, format="mixed"))
    if not stamps.is_unique or not stamps.is_monotonic_increasing:
        raise ValueError("candles must be unique and ordered")
    if not ((stamps.minute % 5 == 0) & (stamps.second == 0) & (stamps.microsecond == 0)).all():
        raise ValueError("candles are off the 5-minute grid")
    closes = frame["close"].to_numpy(dtype=float)
    if not np.isfinite(closes).all() or (closes <= 0).any():
        raise ValueError("closes must be finite and positive")
    frame = frame.copy()
    frame["_close_time"] = stamps + pd.Timedelta(minutes=5)
    return frame.sort_values("_close_time").reset_index(drop=True)


def diagnose(candles_path: Path, horizon_minutes: int, target_hours: tuple[int, ...],
               window_start: pd.Timestamp = WINDOW_START,
               window_end: pd.Timestamp = WINDOW_END) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if horizon_minutes != REQUIRED_HORIZON:
        raise ValueError(f"frozen horizon is {REQUIRED_HORIZON}, got {horizon_minutes}")
    if tuple(target_hours) != REQUIRED_HOURS:
        raise ValueError(f"frozen target hours are {REQUIRED_HOURS}")
    if not (pd.Timestamp(window_start).tz_convert("UTC") == WINDOW_START
            and pd.Timestamp(window_end).tz_convert("UTC") == WINDOW_END):
        raise ValueError("frozen population window must not change without a new linked identity")
    frame = load_candles(candles_path)
    close_times = pd.DatetimeIndex(frame["_close_time"])
    closes = frame["close"].to_numpy(dtype=float)
    position_of = {t: i for i, t in enumerate(close_times)}
    breaks = np.zeros(len(close_times), dtype=np.int64)
    breaks[1:] = np.asarray(close_times[1:] - close_times[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    candidate_rows: list[dict] = []
    baseline_rows: list[dict] = []
    excluded = {"missing_target": 0, "gap": 0, "outside_window": 0}
    steps = horizon_minutes // 5
    for i, close_time in enumerate(close_times):
        if not (WINDOW_START <= close_time < WINDOW_END):
            excluded["outside_window"] += 1
            continue
        target_time = close_time + pd.Timedelta(minutes=horizon_minutes)
        if target_time not in position_of:
            excluded["missing_target"] += 1
            continue
        j = position_of[target_time]
        if j - i != steps or prefix[j] != prefix[i]:
            excluded["gap"] += 1
            continue
        decision_close = float(closes[i])
        target_close = float(closes[j])
        ret = (target_close / decision_close - 1) * 100
        hour = close_time.hour
        group = candidate_rows if hour in target_hours else baseline_rows
        event_id = f"bar-{close_time.strftime('%Y%m%dT%H%M')}"
        close_iso = close_time.isoformat().replace("+00:00", "Z")
        target_iso = target_time.isoformat().replace("+00:00", "Z")
        group.append({
            "event_id": event_id,
            "decision_time_utc": close_iso,
            "available_at_utc": close_iso,
            "horizon_minutes": horizon_minutes,
            "target_time_utc": target_iso,
            "decision_close_price": decision_close,
            "target_close_price": target_close,
            "outcome_status": "COMPLETE",
            "return_pct": ret,
            "included": "true"})
    candidate = pd.DataFrame(candidate_rows)
    baseline = pd.DataFrame(baseline_rows)

    def _metrics(rows: pd.DataFrame) -> dict:
        values = pd.to_numeric(rows["return_pct"]).to_numpy(dtype=float) if len(rows) else np.array([])
        return {"n": int(len(rows)),
                "mean": float(np.mean(values)) if len(values) else None,
                "median": float(np.median(values)) if len(values) else None,
                "positive_share": float(np.mean(values > 0)) if len(values) else None}

    cand_m, base_m = _metrics(candidate), _metrics(baseline)
    difference = (cand_m["mean"] - base_m["mean"]) if cand_m["mean"] is not None and base_m["mean"] is not None else None
    summary = {"version": VERSION, "horizon_minutes": horizon_minutes,
               "target_hours_utc": list(target_hours),
               "window_start_close_utc": "2022-08-28T00:00:00Z",
               "window_end_close_utc": "2026-08-28T00:00:00Z",
               "candles": {"path": Path(candles_path).as_posix(),
                           "sha256": hashlib.sha256(Path(candles_path).read_bytes()).hexdigest(),
                           "rows": len(frame)},
               "candidate": cand_m, "baseline": base_m,
               "difference_pp": difference,
               "verdict": ("succeeded" if difference is not None and difference > 0 else "rejected"),
               "excluded": excluded}
    return candidate, baseline, summary


def main(argv: list[str] | None = None) -> int:
    # Runner template: script_path is argv[0]; caller supplies params + outdir.
    if argv is None:
        argv = sys.argv
    if len(argv) == 3 and not argv[1].startswith("-"):
        params_path, output_dir = Path(argv[1]), Path(argv[2])
    else:
        parser = argparse.ArgumentParser(prog="hour_seasonality")
        parser.add_argument("--params", required=True)
        parser.add_argument("--output-dir", required=True)
        args = parser.parse_args(argv[1:])
        params_path, output_dir = Path(args.params), Path(args.output_dir)
    params = json.loads(params_path.read_text(encoding="utf-8-sig"))
    candidate, baseline, summary = diagnose(
        Path(params["candles_path"]),
        int(params.get("horizon_minutes", 60)),
        tuple(params.get("target_hours_utc", list(REQUIRED_HOURS))))
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate.to_csv(output_dir / "candidate.csv", index=False)
    baseline.to_csv(output_dir / "baseline.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "result.json").write_text(
        json.dumps({"verdict": summary["verdict"]}) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": summary["verdict"],
                      "difference_pp": summary["difference_pp"],
                      "candidate_n": summary["candidate"]["n"],
                      "baseline_n": summary["baseline"]["n"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
