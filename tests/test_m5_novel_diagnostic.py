"""Tests for the novel hour-of-day diagnostic: synthetic fixtures only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.experiments.m5 import hour_seasonality as diag


def _synthetic_candles(path: Path, n: int = 288) -> None:
    # Two full UTC days of 5-minute bars, rising 0.01 per bar.
    index = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    closes = [100.0 + 0.01 * i for i in range(n)]
    pd.DataFrame({"timestamp": index.tz_convert(None).tz_localize(None),
                  "open": closes, "high": closes, "low": closes,
                  "close": closes, "volume": 1.0}).assign(
        timestamp=index.map(lambda t: t.isoformat().replace("+00:00", "Z"))
    ).to_csv(path, index=False)


def test_frozen_contract_rejects_alternate_hours_and_horizons(tmp_path: Path) -> None:
    candles = tmp_path / "candles.csv"
    _synthetic_candles(candles)
    with pytest.raises(ValueError):
        diag.diagnose(candles, 120, (13, 14, 15, 16))
    with pytest.raises(ValueError):
        diag.diagnose(candles, 60, (9, 10))


def test_groups_are_disjoint_and_cover_the_window(tmp_path: Path) -> None:
    candles = tmp_path / "candles.csv"
    _synthetic_candles(candles)
    candidate, baseline, summary = diag.diagnose(candles, 60, (13, 14, 15, 16))
    assert len(candidate) > 0 and len(baseline) > 0
    assert set(candidate["event_id"]).isdisjoint(set(baseline["event_id"]))
    assert set(candidate["decision_time_utc"]).isdisjoint(set(baseline["decision_time_utc"]))
    assert summary["candidate"]["n"] == len(candidate)
    assert summary["verdict"] in ("succeeded", "rejected")
    # Exact-horizon and point-in-time rules hold by construction.
    for rows in (candidate, baseline):
        decisions = pd.to_datetime(rows["decision_time_utc"], utc=True)
        targets = pd.to_datetime(rows["target_time_utc"], utc=True)
        available = pd.to_datetime(rows["available_at_utc"], utc=True)
        assert ((targets - decisions) == pd.Timedelta(minutes=60)).all()
        assert (available <= decisions).all()


def test_runner_template_argv_shape(tmp_path: Path) -> None:
    candles = tmp_path / "candles.csv"
    _synthetic_candles(candles)
    params = tmp_path / "params.json"
    outdir = tmp_path / "out"
    params.write_text(json.dumps({"candles_path": str(candles),
                                  "horizon_minutes": 60,
                                  "target_hours_utc": [13, 14, 15, 16]}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", str(Path(diag.__file__)), str(params), str(outdir)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert (outdir / "candidate.csv").is_file()
    assert (outdir / "baseline.csv").is_file()
    assert json.loads((outdir / "result.json").read_text(encoding="utf-8"))["verdict"] in (
        "succeeded", "rejected")
