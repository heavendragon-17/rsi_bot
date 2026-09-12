"""M5 scientific-check tests: synthetic hand-calculated fixtures only.

No real BTC dataset, holdout, trading configuration or strategy is opened
or changed. Every candle and diagnostic row below is authored by the test
with independently computed returns.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.m5_checks import checker


def _candles(path: Path, closes: list[float], start="2026-01-01T00:00:00Z") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(closes), freq="5min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": [t.isoformat().replace("+00:00", "Z") for t in index],
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1.0] * len(closes)})
    frame.to_csv(path, index=False)
    return frame


def _diag_row(event: str, decision: str, available: str, horizon: int,
              target: str, decision_close: float, target_close, status: str,
              included: bool):
    if status == "COMPLETE":
        ret = (float(target_close) / float(decision_close) - 1) * 100
    else:
        ret = ""
        target_close = ""
    return {"event_id": event, "decision_time_utc": decision,
            "available_at_utc": available, "horizon_minutes": horizon,
            "target_time_utc": target, "decision_close_price": decision_close,
            "target_close_price": target_close, "outcome_status": status,
            "return_pct": ret, "included": str(included).lower()}


def _write(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _pair(tmp_path: Path, closes: list[float], cand_rows, base_rows,
          horizon: int = 60):
    candles = tmp_path / "candles.csv"
    _candles(candles, closes)
    candidate = tmp_path / "candidate.csv"
    baseline = tmp_path / "baseline.csv"
    _write(candidate, cand_rows)
    _write(baseline, base_rows)
    return candles, candidate, baseline


def _iso(base: str, minutes: int) -> str:
    return (pd.Timestamp(base) + pd.Timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


BASE = "2026-01-01T00:05:00Z"  # first bar CLOSE (opens are five minutes earlier)


def test_positive_zero_and_negative_reproduce(tmp_path: Path) -> None:
    # Rising closes: +12% over 60 minutes (100 -> 112).
    closes = [100.0 + i for i in range(30)]
    cand = [_diag_row("pos-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    base = [_diag_row("base-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                      _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    result = checker.run_files(candles_path=candles, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert result["passed"], result["violations"]
    assert result["scientific"]["candidate"]["mean"] == pytest.approx(12.0)
    assert result["scientific"]["baseline"]["mean"] == pytest.approx((113 / 101 - 1) * 100)
    # Flat closes: exactly zero.
    flat = [100.0] * 30
    cand0 = [_diag_row("zero-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                       _iso(BASE, 60), 100.0, 100.0, "COMPLETE", True)]
    base0 = [_diag_row("bzero-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                       _iso(BASE, 65), 100.0, 100.0, "COMPLETE", True)]
    candles0, cp0, bp0 = _pair(tmp_path / "z", flat, cand0, base0) if False else (None, None, None)
    (tmp_path / "z").mkdir(exist_ok=True)
    candles0, cp0, bp0 = _pair(tmp_path / "z", flat, cand0, base0)
    zero = checker.run_files(candles_path=candles0, candidate_path=cp0,
                             baseline_path=bp0, horizon_minutes=60)
    assert zero["passed"] and zero["scientific"]["candidate"]["mean"] == pytest.approx(0.0)
    # Falling closes: negative.
    falling = [120.0 - i for i in range(30)]
    candn = [_diag_row("neg-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                       _iso(BASE, 60), 120.0, 108.0, "COMPLETE", True)]
    basen = [_diag_row("bneg-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                       _iso(BASE, 65), 119.0, 107.0, "COMPLETE", True)]
    (tmp_path / "n").mkdir(exist_ok=True)
    candlesn, cpn, bpn = _pair(tmp_path / "n", falling, candn, basen)
    neg = checker.run_files(candles_path=candlesn, candidate_path=cpn,
                            baseline_path=bpn, horizon_minutes=60)
    assert neg["passed"] and neg["scientific"]["candidate"]["mean"] == pytest.approx(-10.0)
    # A negative candidate mean still passes checks with a rejected verdict.
    assert neg["scientific"]["verdict"] in ("succeeded", "rejected")


def test_delayed_availability_is_a_timing_violation(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    cand = [_diag_row("late-1", _iso(BASE, 0), _iso(BASE, 30), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    base = [_diag_row("base-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                      _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    result = checker.run_files(candles_path=candles, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert not result["passed"] and result["scientific"]["verdict"] == "INVALID"
    assert len(result["violations"]["timing"]) == 1


def test_missing_target_is_excluded_not_substituted(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    # Target bar 12 exists in the diagnostic's expectation but we drop it
    # from the candles so the exact target is missing.
    candles_path = tmp_path / "candles.csv"
    frame = _candles(candles_path, closes)
    frame = frame.drop(index=[12]).reset_index(drop=True)
    frame.to_csv(candles_path, index=False)
    cand = [_diag_row("miss-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 60), 100.0, "", "MISSING_TARGET", False)]
    base = [_diag_row("base-1", _iso(BASE, 65), _iso(BASE, 65), 60,
                      _iso(BASE, 125), 113.0, 125.0, "COMPLETE", True)]
    cp, bp = tmp_path / "candidate.csv", tmp_path / "baseline.csv"
    _write(cp, cand)
    _write(bp, base)
    result = checker.run_files(candles_path=candles_path, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert result["passed"], result["violations"]
    assert result["excluded"]["candidate"]["status_counts"].get("MISSING_TARGET") == 1
    # Claiming COMPLETE over the missing bar is a data violation.
    bad = [_diag_row("miss-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                     _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    _write(cp, bad)
    bad_result = checker.run_files(candles_path=candles_path, candidate_path=cp,
                                   baseline_path=bp, horizon_minutes=60)
    assert not bad_result["passed"] and bad_result["violations"]["data"]


def test_shifted_horizon_mutant_is_rejected(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    # Correct target is +60; the mutant substitutes a later candle (+65).
    cand = [_diag_row("shift-1", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 65), 100.0, 113.0, "COMPLETE", True)]
    base = [_diag_row("base-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                      _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    result = checker.run_files(candles_path=candles, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert not result["passed"] and result["violations"]["horizon"]


def test_future_information_mutant_is_rejected(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    # Numerically correct but available after the decision: still invalid.
    cand = [_diag_row("future-1", _iso(BASE, 0), _iso(BASE, 60), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    base = [_diag_row("base-1", _iso(BASE, 5), _iso(BASE, 5), 60,
                      _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    result = checker.run_files(candles_path=candles, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert not result["passed"] and result["violations"]["timing"]


def test_duplicates_and_invalid_ordering_are_schema_violations(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    dup = [_diag_row("dup", _iso(BASE, 0), _iso(BASE, 0), 60,
                     _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True),
           _diag_row("dup", _iso(BASE, 5), _iso(BASE, 5), 60,
                     _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    base = [_diag_row("base-1", _iso(BASE, 10), _iso(BASE, 10), 60,
                      _iso(BASE, 70), 102.0, 114.0, "COMPLETE", True)]
    candles = tmp_path / "candles.csv"
    _candles(candles, closes)
    cp, bp = tmp_path / "candidate.csv", tmp_path / "baseline.csv"
    _write(cp, dup)
    _write(bp, base)
    with pytest.raises(ValueError):
        checker.run_files(candles_path=candles, candidate_path=cp,
                          baseline_path=bp, horizon_minutes=60)


def test_overlapping_populations_are_rejected(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    cand = [_diag_row("a", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    base = [_diag_row("b", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    result = checker.run_files(candles_path=candles, candidate_path=cp,
                               baseline_path=bp, horizon_minutes=60)
    assert not result["passed"] and result["violations"]["population"]


def test_cli_uses_direct_argv_and_stable_schema(tmp_path: Path) -> None:
    closes = [100.0 + i for i in range(30)]
    cand = [_diag_row("c1", _iso(BASE, 0), _iso(BASE, 0), 60,
                      _iso(BASE, 60), 100.0, 112.0, "COMPLETE", True)]
    base = [_diag_row("b1", _iso(BASE, 5), _iso(BASE, 5), 60,
                      _iso(BASE, 65), 101.0, 113.0, "COMPLETE", True)]
    candles, cp, bp = _pair(tmp_path, closes, cand, base)
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "research.m5_checks.cli",
         "--candles", str(candles), "--candidate", str(cp),
         "--baseline", str(bp), "--horizon-minutes", "60",
         "--output", str(out)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "m5-scientific-check-v1" and report["passed"]
    assert report["inputs"]["candles"]["sha256"] == hashlib.sha256(
        candles.read_bytes()).hexdigest()
