"""M5 acceptance tests: synthetic hand-calculated fixtures only.

Exercises the diagnostic-specific acceptance layer (population
reconstruction plus metric/verdict binding) over tiny synthetic candle
files with a custom declaration. No real BTC dataset, holdout, trading
configuration or strategy is opened or changed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.m5_checks.acceptance import Declaration, accept

REPO = Path(__file__).resolve().parents[1]


def _candles(path: Path, start="2026-01-01T00:00:00Z", periods=576) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    closes = [100.0 + 0.01 * i for i in range(periods)]
    frame = pd.DataFrame({
        "timestamp": [t.isoformat().replace("+00:00", "Z") for t in index],
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1.0] * periods})
    frame.to_csv(path, index=False)
    return frame


def _declaration(candles: Path) -> Declaration:
    return Declaration(
        candles_sha256=hashlib.sha256(candles.read_bytes()).hexdigest(),
        window_start_close_utc="2026-01-01T00:05:00Z",
        window_end_close_utc="2026-01-02T12:00:00Z",
        horizon_minutes=60,
        target_hours_utc=(0,))


def _split(candles: Path, declaration: Declaration):
    """Independent test-local grouping under the declaration's rule."""
    frame = pd.read_csv(candles, encoding="utf-8-sig")
    opens = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True, format="mixed"))
    closes = frame["close"].to_numpy(dtype=float)
    close_times = opens + pd.Timedelta(minutes=5)
    position_of = {t: i for i, t in enumerate(close_times)}
    start = pd.Timestamp(declaration.window_start_close_utc)
    end = pd.Timestamp(declaration.window_end_close_utc)
    horizon = pd.Timedelta(minutes=declaration.horizon_minutes)
    candidate_rows, baseline_rows = [], []
    for i, close_time in enumerate(close_times):
        if not start <= close_time < end:
            continue
        target_time = close_time + horizon
        j = position_of[target_time]
        ret = (closes[j] / closes[i] - 1) * 100
        iso = lambda t: pd.Timestamp(t).isoformat().replace("+00:00", "Z")
        row = {"event_id": f"bar-{close_time.strftime('%Y%m%dT%H%M')}",
               "decision_time_utc": iso(close_time),
               "available_at_utc": iso(close_time),
               "horizon_minutes": declaration.horizon_minutes,
               "target_time_utc": iso(target_time),
               "decision_close_price": closes[i],
               "target_close_price": closes[j],
               "outcome_status": "COMPLETE",
               "return_pct": ret,
               "included": "true"}
        (candidate_rows if close_time.hour in declaration.target_hours_utc
         else baseline_rows).append(row)
    return pd.DataFrame(candidate_rows), pd.DataFrame(baseline_rows)


def _fixture(tmp_path: Path):
    candles = tmp_path / "candles.csv"
    _candles(candles)
    declaration = _declaration(candles)
    candidate, baseline = _split(candles, declaration)
    candidate_path, baseline_path = tmp_path / "candidate.csv", tmp_path / "baseline.csv"
    candidate.to_csv(candidate_path, index=False)
    baseline.to_csv(baseline_path, index=False)
    return candles, candidate_path, baseline_path, declaration


def _group_stats(frame: pd.DataFrame) -> dict:
    values = frame["return_pct"].to_numpy(dtype=float)
    return {"n": int(len(frame)), "mean": float(values.mean()),
            "median": float(pd.Series(values).median()),
            "positive_share": float((values > 0).mean())}


def _summary(tmp_path: Path, candidate_path: Path, baseline_path: Path) -> Path:
    candidate = pd.read_csv(candidate_path, encoding="utf-8-sig")
    baseline = pd.read_csv(baseline_path, encoding="utf-8-sig")
    candidate_stats, baseline_stats = _group_stats(candidate), _group_stats(baseline)
    difference = candidate_stats["mean"] - baseline_stats["mean"]
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({
        "candidate": candidate_stats,
        "baseline": baseline_stats,
        "difference_pp": difference,
        "verdict": "succeeded" if difference > 0 else "rejected",
    }), encoding="utf-8")
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "verdict": "succeeded" if difference > 0 else "rejected",
    }), encoding="utf-8")
    return path


def test_accept_correct_split_with_metric_binding(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    result_path=tmp_path / "result.json", declaration=declaration)
    assert report["accepted"], report["reasons"]
    assert report["reconstruction"]["candidate_n"] > 0
    assert report["reconstruction"]["baseline_n"] > 0


def test_reject_swapped_groups(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    report = accept(candles_path=candles, candidate_path=baseline_path,
                    baseline_path=candidate_path, declaration=declaration)
    assert not report["accepted"]
    assert any("omitted" in reason or "outside" in reason for reason in report["reasons"])


def test_reject_truncated_population(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    candidate = pd.read_csv(candidate_path, encoding="utf-8-sig")
    truncated_path = tmp_path / "candidate-truncated.csv"
    candidate.head(1).to_csv(truncated_path, index=False)
    report = accept(candles_path=candles, candidate_path=truncated_path,
                    baseline_path=baseline_path, declaration=declaration)
    assert not report["accepted"]
    assert any("omitted" in reason for reason in report["reasons"])


def test_reject_tampered_summary_mean(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate"]["mean"] += 5.0
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    result_path=tmp_path / "result.json", declaration=declaration)
    assert not report["accepted"]
    assert any("summary" in reason for reason in report["reasons"])


def test_reject_non_finite_summary_metrics(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate"]["mean"] = float("nan")
    summary["baseline"]["mean"] = float("nan")
    summary["difference_pp"] = float("nan")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    result_path=tmp_path / "result.json", declaration=declaration)
    assert not report["accepted"]
    assert any("strict JSON" in reason or "finite" in reason for reason in report["reasons"])


def test_reject_forged_supporting_statistics(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate"].update(n=999999, median=999, positive_share=-50)
    summary["baseline"].update(n=0, median=-999, positive_share=50)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    result_path=tmp_path / "result.json", declaration=declaration)
    assert not report["accepted"]
    assert any("n does not match" in reason for reason in report["reasons"])


def test_reject_malformed_declaration_structured(tmp_path: Path) -> None:
    import dataclasses

    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    bad_hours = dataclasses.replace(declaration, target_hours_utc=(0, 0, 25, -1))
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, declaration=bad_hours)
    assert not report["accepted"]
    assert any("target_hours" in reason for reason in report["reasons"])
    bad_rule = dataclasses.replace(declaration, rejection_rule="always_succeeded")
    without_artifacts = accept(
        candles_path=candles, candidate_path=candidate_path,
        baseline_path=baseline_path, declaration=bad_rule)
    assert not without_artifacts["accepted"]
    assert any("rejection_rule" in reason for reason in without_artifacts["reasons"])
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    with_artifacts = accept(
        candles_path=candles, candidate_path=candidate_path,
        baseline_path=baseline_path, summary_path=summary_path,
        result_path=tmp_path / "result.json", declaration=bad_rule)
    assert not with_artifacts["accepted"]
    assert any("rejection_rule" in reason for reason in with_artifacts["reasons"])


def test_reject_malformed_summary_structured(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    summary_path.write_text("[]", encoding="utf-8")
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    declaration=declaration)
    assert not report["accepted"]
    summary = {"candidate": {"mean": "not-a-number"}}
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, summary_path=summary_path,
                    declaration=declaration)
    assert not report["accepted"]


def test_accept_rejects_fractional_declaration_horizon_directly(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    bad = dataclasses.replace(declaration, horizon_minutes=60.9)
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, declaration=bad)
    assert not report["accepted"]
    assert any("horizon" in reason for reason in report["reasons"])


def _run_cli(tmp_path: Path, horizon_value) -> tuple[int, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    summary_path = _summary(tmp_path, candidate_path, baseline_path)
    raw = dataclasses.asdict(declaration)
    raw["horizon_minutes"] = horizon_value
    declaration_path = tmp_path / "declaration.json"
    declaration_path.write_text(json.dumps(raw), encoding="utf-8")
    output_path = tmp_path / "cli-report.json"
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "research.m5_checks.cli",
         "--candles", str(candles), "--candidate", str(candidate_path),
         "--baseline", str(baseline_path), "--horizon-minutes", "60",
         "--declaration", str(declaration_path), "--summary", str(summary_path),
         "--result", str(tmp_path / "result.json"), "--output", str(output_path)],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    return proc.returncode, output_path


def test_cli_rejects_fractional_or_non_integer_declared_horizon(tmp_path: Path) -> None:
    # A fractional 60.9 must never be coerced into an accepted 60-minute run.
    code, output = _run_cli(tmp_path / "fractional", 60.9)
    assert code != 0
    if output.exists():
        assert not json.loads(output.read_text(encoding="utf-8"))["accepted"]
    # A numeric string is equally malformed, not a 60-minute horizon.
    code, output = _run_cli(tmp_path / "string", "60")
    assert code != 0
    if output.exists():
        assert not json.loads(output.read_text(encoding="utf-8"))["accepted"]
    # The well-formed integer declaration still accepts.
    code, output = _run_cli(tmp_path / "normal", 60)
    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["accepted"]
    assert json.loads(output.read_text(encoding="utf-8"))["declaration"]["horizon_minutes"] == 60


def test_reject_wrong_candles_hash(tmp_path: Path) -> None:
    candles, candidate_path, baseline_path, declaration = _fixture(tmp_path)
    bad = Declaration(
        candles_sha256="0" * 64,
        window_start_close_utc=declaration.window_start_close_utc,
        window_end_close_utc=declaration.window_end_close_utc,
        horizon_minutes=declaration.horizon_minutes,
        target_hours_utc=declaration.target_hours_utc)
    report = accept(candles_path=candles, candidate_path=candidate_path,
                    baseline_path=baseline_path, declaration=bad)
    assert not report["accepted"]
