"""Focused tests for the BTC research Phase 1 evidence baseline."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import app.backtest.btc_research_phase1 as phase1
from app.backtest.btc_research_phase1 import (
    ValidatedInputs,
    _baseline_outcomes,
    _exact_forward_outcome,
    _git_identity,
    _summaries,
    run_phase1_baseline,
    validate_inputs,
)
from app.backtest.signal_replay_models import SignalReplayInputError
from app.trading.strategy.btc_rsi_cross_alert.models import (
    H4_EXPECTED_CLOSE_MISSING,
    H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
    PREPARATION_READY,
)


def _frame(times: list[datetime], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": closes}, index=pd.DatetimeIndex(times))


def _write_ohlcv_inputs(
    directory: Path,
    *,
    periods: dict[str, int],
    start: str = "2026-01-01 00:00:00",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    steps = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
    for timeframe, period_count in periods.items():
        timestamps = pd.date_range(
            start,
            periods=period_count,
            freq=f"{steps[timeframe]}min",
        )
        closes = [100.0 + position * 0.01 for position in range(period_count)]
        pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1.0] * period_count,
            }
        ).to_csv(directory / f"BTCUSDT_{timeframe}.csv", index=False)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_exact_horizon_requires_the_exact_target_close_and_percent_units() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = _frame(
        [start + timedelta(minutes=5 * position) for position in range(13)],
        [100.0] + [100.0] * 11 + [110.0],
    )
    outcome = _exact_forward_outcome(
        frame,
        "5m",
        trigger_close=start + timedelta(minutes=5),
        trigger_price=100.0,
        horizon_minutes=60,
    )
    assert outcome["outcome_status"] == "COMPLETE"
    assert outcome["return_pct"] == 10.0

    no_exact_target = frame.drop(frame.index[-1])
    missing = _exact_forward_outcome(
        no_exact_target,
        "5m",
        trigger_close=start + timedelta(minutes=5),
        trigger_price=100.0,
        horizon_minutes=60,
    )
    assert missing["outcome_status"] == "INCOMPLETE_TAIL"
    assert missing["return_pct"] is None


def test_gap_invalidates_outcome_without_using_a_later_candle() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    frame = _frame(
        [start - timedelta(minutes=5), start, start + timedelta(minutes=10), start + timedelta(minutes=15)],
        [100.0, 100.0, 120.0, 120.0],
    )
    outcome = _exact_forward_outcome(
        frame,
        "5m",
        trigger_close=start,
        trigger_price=100.0,
        horizon_minutes=15,
    )
    assert outcome["outcome_status"] == "GAP"
    assert outcome["return_pct"] is None


def test_source_validation_rejects_duplicate_native_candle(monkeypatch) -> None:
    def fail_with_duplicate(*_args, **_kwargs):
        raise SignalReplayInputError("Historical 5m CSV contains duplicate candle opens")

    monkeypatch.setattr(phase1, "load_ohlcv_csv", fail_with_duplicate)
    with pytest.raises(SignalReplayInputError, match="duplicate"):
        validate_inputs(".")


def test_source_report_records_identity_hashes_and_native_cadence(tmp_path) -> None:
    steps = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
    for timeframe, minutes in steps.items():
        timestamps = pd.date_range(
            "2026-01-01 00:00:00",
            periods=2,
            freq=f"{minutes}min",
        )
        pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0, 101.0],
                "high": [100.0, 101.0],
                "low": [100.0, 101.0],
                "close": [100.0, 101.0],
                "volume": [1.0, 1.0],
            }
        ).to_csv(tmp_path / f"BTCUSDT_{timeframe}.csv", index=False)

    inputs = validate_inputs(tmp_path)

    assert inputs.source_report["identity"]["symbol"] == "BTC/USDT"
    assert inputs.source_report["identity"]["venue_instrument"] == "BTC/USDT:USDT"
    for timeframe in steps:
        facts = inputs.source_report["files"][timeframe]
        assert facts["expected_filename"] == f"BTCUSDT_{timeframe}.csv"
        assert len(facts["sha256"]) == 64
        assert facts["non_cadence_count"] == 0
        assert facts["gap_count"] == 0


def test_summary_is_deterministic_and_keeps_missing_outcomes_explicit() -> None:
    signal_rows = [
        {"timeframe": "5m", "horizon": "1h", "outcome_status": "COMPLETE", "return_pct": 1.0, "trigger_close_at": "2026-01-01T00:05:00Z"},
        {"timeframe": "5m", "horizon": "1h", "outcome_status": "INCOMPLETE_TAIL", "return_pct": None, "trigger_close_at": "2026-01-02T00:05:00Z"},
    ]
    first = _summaries(signal_rows, signal_rows)
    second = _summaries(signal_rows, signal_rows)
    assert first == second
    summary = next(item for item in first[0] if item["timeframe"] == "5m" and item["horizon"] == "1h")
    assert summary["signal_outcomes"]["status_counts"]["INCOMPLETE_TAIL"] == 1
    assert summary["signal_outcomes"]["mean_return_pct"] == 1.0


def test_two_candle_zero_signal_run_is_invalid_and_records_preparation_exclusions(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    _write_ohlcv_inputs(data_dir, periods={timeframe: 2 for timeframe in ("5m", "15m", "1h", "4h")})

    packet = run_phase1_baseline(
        data_dir,
        tmp_path / "packets",
        repo_root=tmp_path,
    )
    summary = json.loads((packet / "summary.json").read_text(encoding="utf-8"))

    assert summary["completion_status"] == "SUCCESS"
    assert summary["operational_status"] == "INVALID"
    assert summary["signal_counts"] == {"5m": 0, "15m": 0}
    preparation = summary["preparation"]
    assert preparation["total_requested_event_count"] == 4
    assert preparation["total_evaluable_event_count"] == 0
    assert preparation["timeframes_with_missing_warmup"] == ["5m", "15m"]
    assert preparation["timeframes_without_evaluable_coverage"] == ["5m", "15m"]
    assert all(
        item["preparation_excluded_count"] == item["requested_event_count"]
        for item in preparation["by_timeframe"].values()
    )


def test_fully_prepared_zero_signal_period_remains_valid(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_ohlcv_inputs(
        data_dir,
        periods={"5m": 1320, "15m": 440, "1h": 120, "4h": 30},
        start="2026-01-01 03:00:00",
    )
    start = datetime(2026, 1, 4, 15, 0)
    end = datetime(2026, 1, 4, 15, 30)

    packet = run_phase1_baseline(
        data_dir,
        tmp_path / "packets",
        start=start,
        end=end,
        repo_root=tmp_path,
    )
    summary = json.loads((packet / "summary.json").read_text(encoding="utf-8"))

    assert summary["operational_status"] == "VALID"
    assert summary["signal_counts"] == {"5m": 0, "15m": 0}
    assert summary["preparation"]["fully_prepared_requested_period"] is True
    assert summary["preparation"]["total_requested_event_count"] > 0
    assert summary["preparation"]["total_evaluable_event_count"] == summary["preparation"]["total_requested_event_count"]
    assert summary["warnings"] == []


def test_comparator_excludes_unready_bars_but_retains_unaffected_bars(monkeypatch) -> None:
    start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    m5_times = [
        start - timedelta(minutes=5),
        datetime(2026, 1, 5, 12, 55, tzinfo=UTC),
        datetime(2026, 1, 5, 16, 55, tzinfo=UTC),
    ]
    m15_times = [start - timedelta(minutes=15)]
    inputs = ValidatedInputs(
        data_dir=Path("."),
        paths={},
        frames={
            "5m": _frame(m5_times, [100.0, 101.0, 102.0]),
            "15m": _frame(m15_times, [100.0]),
            "1h": _frame([], []),
            "4h": _frame([], []),
        },
        source_report={},
    )
    monkeypatch.setattr(phase1, "_cache_for", lambda _inputs: object())
    readiness = {
        "5m": {
            datetime(2026, 1, 5, 9, 0, tzinfo=UTC): H4_EXPECTED_CLOSE_MISSING,
            datetime(2026, 1, 5, 13, 0, tzinfo=UTC): H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
            datetime(2026, 1, 5, 17, 0, tzinfo=UTC): PREPARATION_READY,
        },
        "15m": {start: PREPARATION_READY},
    }
    report: dict[str, object] = {}

    rows = _baseline_outcomes(
        inputs,
        start,
        datetime(2026, 1, 5, 17, 0, tzinfo=UTC),
        readiness_by_timeframe=readiness,
        comparator_report=report,
    )

    m5_rows = [row for row in rows if row["timeframe"] == "5m"]
    assert {row["trigger_close_at"] for row in m5_rows} == {"2026-01-05T17:00:00Z"}
    m5_report = report["by_timeframe"]["5m"]
    assert m5_report["candidate_bar_count"] == 3
    assert m5_report["eligible_bar_count"] == 1
    assert m5_report["preparation_excluded_count"] == 2
    assert m5_report["preparation_exclusion_reasons"] == {
        H4_EXPECTED_CLOSE_MISSING: 1,
        H4_INSUFFICIENT_CONTIGUOUS_HISTORY: 1,
    }


def test_git_identity_tracks_staged_unstaged_and_untracked_content_but_excludes_packets(
    tmp_path: Path,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is required for the isolated identity fixture")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "phase1@example.invalid", cwd=repo)
    _git("config", "user.name", "Phase 1 Test", cwd=repo)
    logic = repo / "logic.py"
    logic.write_text("value = 0\n", encoding="utf-8")
    _git("add", "logic.py", cwd=repo)
    _git("commit", "-qm", "initial", cwd=repo)

    initial = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert initial == _git_identity(repo, excluded_paths=(repo / "packets",))

    logic.write_text("value = 1\n", encoding="utf-8")
    unstaged_one = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert unstaged_one["dirty"] is True
    assert unstaged_one["dirty_code_identity_sha256"] != initial["dirty_code_identity_sha256"]

    _git("add", "logic.py", cwd=repo)
    staged_one = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert staged_one["dirty_code_identity_sha256"] == unstaged_one["dirty_code_identity_sha256"]

    logic.write_text("value = 2\n", encoding="utf-8")
    unstaged_two = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert unstaged_two["dirty_code_identity_sha256"] != staged_one["dirty_code_identity_sha256"]
    _git("add", "logic.py", cwd=repo)
    staged_two = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert staged_two["dirty_code_identity_sha256"] != staged_one["dirty_code_identity_sha256"]

    (repo / "untracked.py").write_text("untracked = True\n", encoding="utf-8")
    with_untracked = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert with_untracked["dirty_code_identity_sha256"] != staged_two["dirty_code_identity_sha256"]
    assert with_untracked == _git_identity(repo, excluded_paths=(repo / "packets",))

    packet_file = repo / "packets" / "run" / "summary.json"
    packet_file.parent.mkdir(parents=True)
    packet_file.write_text("{\"generated\": true}\n", encoding="utf-8")
    with_packet = _git_identity(repo, excluded_paths=(repo / "packets",))
    assert with_packet == with_untracked
    assert all("packets" not in status for status in with_packet["status"])
