"""Focused tests for the offline M15 signal-and-gate diagnostic.

These tests cover the five verification obligations of the M15 diagnostic:
future candles cannot change an earlier evaluation, H1/H4 context is already
closed at the decision time, missing targets and incomplete tails stay explicit,
the three comparison groups follow their documented eligibility rules, and
manually checked synthetic examples match the calculated returns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app.backtest.btc_research_phase1 as phase1
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
    DECISION_NO_FRESH_BULLISH_CROSS,
    H4_EXPECTED_CLOSE_MISSING,
    PREPARATION_READY,
)
from research import btc_m15_signal_diagnostic as diagnostic

STEPS = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
START = "2025-10-01T00:00:00Z"


def _walk(periods: int, *, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 30000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.0015, periods)))


def _synthetic_inputs(
    tmp_path: Path | None = None,
    *,
    periods: dict[str, int] | None = None,
    start: str = START,
) -> tuple[phase1.ValidatedInputs, Path | None]:
    """Build (or write and load) a small self-consistent four-timeframe source."""

    counts = {"5m": 4000, "15m": 4000, "1h": 1200, "4h": 400} if periods is None else periods
    frames: dict[str, pd.DataFrame] = {}
    for seed, (timeframe, count) in enumerate(sorted(counts.items()), start=1):
        index = pd.date_range(start, periods=count, freq=f"{STEPS[timeframe]}min", tz="UTC")
        frames[timeframe] = pd.DataFrame(
            {"close": _walk(count, seed=seed), "timeframe": timeframe, "closed": True},
            index=index,
        )
    if tmp_path is None:
        inputs = phase1.ValidatedInputs(data_dir=Path("."), paths={}, frames=frames, source_report={})
        return inputs, None
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for timeframe, frame in frames.items():
        flat = frame.reset_index(names="timestamp")
        flat["timestamp"] = flat["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        for column in ("open", "high", "low"):
            flat[column] = flat["close"]
        flat["volume"] = 1.0
        flat.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].to_csv(
            data_dir / f"BTCUSDT_{timeframe}.csv", index=False
        )
    loaded = phase1.validate_inputs(data_dir)
    return loaded, data_dir


def _m15_frame(periods: int = 60, *, start: str = "2026-01-01T00:00:00Z", closes=None) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    values = np.full(periods, 100.0) if closes is None else np.asarray(closes, dtype=float)
    return pd.DataFrame({"close": values}, index=index)


def _single_bar_scan(frame: pd.DataFrame, close_position: int = 0) -> pd.DataFrame:
    close_time = frame.index[close_position].to_pydatetime() + timedelta(minutes=15)
    return pd.DataFrame(
        {
            "trigger_close_at": [phase1._utc_iso(close_time)],
            "trigger_close_price": [float(frame["close"].iloc[close_position])],
        }
    )


def _all_groups_mask(scan: pd.DataFrame) -> dict[str, pd.Series]:
    flags = pd.Series([True] * len(scan), index=scan.index)
    return {group: flags.copy() for group in diagnostic.GROUPS}


def test_horizons_are_fixed_to_one_and_four_hours() -> None:
    """The diagnostic must not search for a better horizon."""

    assert diagnostic.HORIZONS == (("1h", 60), ("4h", 240))
    assert diagnostic.TIMEFRAME == "15m"
    assert diagnostic.GROUPS == ("m15_signal", "gate_ready_no_cross", "all_eligible_bars")


def test_h1_and_h4_context_closes_never_postdate_the_decision_time() -> None:
    inputs, _ = _synthetic_inputs()
    window_start = datetime(2025, 10, 20, tzinfo=UTC)
    window_end = datetime(2025, 10, 21, tzinfo=UTC)
    scan, audit = diagnostic.scan_population(inputs, window_start, window_end)
    eligible = scan.loc[scan.preparation_reason.eq(PREPARATION_READY)]
    assert len(eligible) > 0
    assert audit["eligible_bar_count"] == len(eligible)
    trigger = pd.to_datetime(eligible.trigger_close_at, utc=True)
    h1 = pd.to_datetime(eligible.h1_close_at, utc=True)
    h4 = pd.to_datetime(eligible.h4_close_at, utc=True)
    assert (h1 <= trigger).all()
    assert (h4 <= trigger).all()
    # The context is the latest native boundary at or before the trigger close.
    assert (h1 == trigger.dt.floor("1h")).all()
    assert (h4 == trigger.dt.floor("4h")).all()


def test_future_candles_cannot_alter_an_earlier_evaluation() -> None:
    inputs, _ = _synthetic_inputs()
    trigger = datetime(2025, 10, 20, 12, 0, tzinfo=UTC)
    full, _ = diagnostic.scan_population(inputs, trigger, trigger)

    truncated: dict[str, pd.DataFrame] = {}
    for timeframe, frame in inputs.frames.items():
        closes = pd.DatetimeIndex(frame.index).tz_convert(UTC) + timedelta(minutes=STEPS[timeframe])
        truncated[timeframe] = frame.loc[closes <= trigger]
    cut_inputs = phase1.ValidatedInputs(
        data_dir=Path("."), paths={}, frames=truncated, source_report={}
    )
    cut, _ = diagnostic.scan_population(cut_inputs, trigger, trigger)

    assert len(full) == len(cut) == 1
    assert full.iloc[0].to_dict() == cut.iloc[0].to_dict()
    assert full.iloc[0]["preparation_reason"] == PREPARATION_READY


def test_missing_target_gap_and_incomplete_tail_stay_explicit() -> None:
    frame = _m15_frame(30)
    trigger_close = frame.index[0].to_pydatetime() + timedelta(minutes=15)
    target_4h = trigger_close + timedelta(minutes=240)
    trigger_price = float(frame["close"].iloc[0])

    def statuses(source: pd.DataFrame) -> dict[int, str]:
        index = phase1._forward_index(source, "15m")
        rows = diagnostic.observations(_single_bar_scan(source), _all_groups_mask(_single_bar_scan(source)), index)
        return dict(zip(rows.horizon_minutes, rows.outcome_status, strict=True))

    assert statuses(frame) == {60: "COMPLETE", 240: "COMPLETE"}
    # A missing exact target candle is never replaced by a later candle.
    assert statuses(frame.drop(frame.index[16]))[240] == "MISSING_TARGET"
    # A native gap before the exact target invalidates the outcome.
    assert statuses(frame.drop(frame.index[8]))[240] == "GAP"
    # A source that ends before the target close is an explicit incomplete tail.
    short = _m15_frame(10)
    assert statuses(short)[240] == "INCOMPLETE_TAIL"
    source = phase1._forward_index(short, "15m")
    scan = _single_bar_scan(short)
    rows = diagnostic.observations(scan, _all_groups_mask(scan), source)
    incomplete = rows.loc[rows.horizon_minutes.eq(240)]
    assert incomplete.return_pct.isna().all()
    assert not incomplete.included_both_horizons.any()
    assert str(incomplete.target_close_at.iloc[0]) == phase1._utc_iso(target_4h)
    assert trigger_price == float(frame["close"].iloc[0])


def test_comparison_group_eligibility_rules_nest_and_are_documented() -> None:
    scan = pd.DataFrame(
        {
            "trigger_close_at": ["t1", "t2", "t3", "t4"],
            "preparation_reason": [PREPARATION_READY, PREPARATION_READY, PREPARATION_READY, H4_EXPECTED_CLOSE_MISSING],
            "price_gates_pass": [True, False, True, None],
        }
    )
    membership = diagnostic.group_membership(scan, ["t1"])
    assert membership["all_eligible_bars"].tolist() == [True, True, True, False]
    assert membership["gate_ready_no_cross"].tolist() == [True, False, True, False]
    assert membership["m15_signal"].tolist() == [True, False, False, False]
    # Nesting: m15_signal subset of gate_ready_no_cross subset of all_eligible_bars.
    assert (membership["m15_signal"] & ~membership["gate_ready_no_cross"]).sum() == 0
    assert (membership["gate_ready_no_cross"] & ~membership["all_eligible_bars"]).sum() == 0
    # An emitted alert that fails a documented gate is a hard integrity error.
    with pytest.raises(ValueError, match="fail the documented gate rules"):
        diagnostic.group_membership(scan, ["t3", "t4"])


def test_gate_predicate_must_agree_with_the_locked_decision_reasons() -> None:
    consistent = pd.DataFrame(
        {
            "preparation_reason": [PREPARATION_READY] * 3,
            "m15_decision_reason": [
                DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
                DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
                DECISION_NO_FRESH_BULLISH_CROSS,
            ],
            "fresh_bullish_cross": [True, True, False],
            "price_gates_pass": [True, False, False],
        }
    )
    diagnostic.verify_gate_consistency(consistent)
    assert diagnostic.fresh_bullish_cross(DECISION_NO_FRESH_BULLISH_CROSS) is False
    assert diagnostic.fresh_bullish_cross(DECISION_M15_CLOSE_NOT_ABOVE_EMA21) is True
    # A crossed bar whose reported gate failure contradicts the predicate is rejected.
    contradicted = consistent.copy()
    contradicted.loc[1, "price_gates_pass"] = True
    with pytest.raises(ValueError, match="price-gate predicate"):
        diagnostic.verify_gate_consistency(contradicted)
    also_contradicted = consistent.copy()
    also_contradicted.loc[0, "price_gates_pass"] = False
    with pytest.raises(ValueError, match="price-gate predicate"):
        diagnostic.verify_gate_consistency(also_contradicted)
    malformed = consistent.copy()
    malformed.loc[2, "m15_decision_reason"] = DECISION_M15_CLOSE_NOT_ABOVE_EMA21
    with pytest.raises(ValueError):
        diagnostic.verify_gate_consistency(malformed)


def test_manually_checked_synthetic_returns_match_the_calculated_values() -> None:
    closes = np.full(40, 100.0)
    closes[4] = 102.0  # close at 01:15 UTC, the exact 1h target of the 00:15 close
    closes[16] = 97.0  # close at 04:15 UTC, the exact 4h target
    frame = _m15_frame(40, closes=closes)
    scan = _single_bar_scan(frame)
    source = phase1._forward_index(frame, "15m")
    rows = (
        diagnostic.observations(scan, _all_groups_mask(scan), source)
        .loc[lambda frame: frame["group"].eq("m15_signal")]
        .set_index("horizon")
    )

    assert abs(rows.loc["1h", "return_pct"] - 2.0) < 1e-12
    assert abs(rows.loc["4h", "return_pct"] - (-3.0)) < 1e-12
    assert rows.loc["1h", "target_close_at"] == "2026-01-01T01:15:00Z"
    assert rows.loc["4h", "target_close_at"] == "2026-01-01T04:15:00Z"
    assert rows.included_both_horizons.all()
    summary = diagnostic.horizon_summaries(diagnostic.observations(scan, _all_groups_mask(scan), source))
    assert summary[0]["populations"]["m15_signal"]["mean_return_pct"] == pytest.approx(2.0)
    assert summary[1]["populations"]["m15_signal"]["mean_return_pct"] == pytest.approx(-3.0)
    assert summary[0]["populations"]["m15_signal"]["positive_return_share"] == pytest.approx(1.0)


def test_parent_horizon_parity_rejects_a_changed_return() -> None:
    closes = np.full(40, 100.0)
    closes[4] = 102.0
    closes[16] = 97.0
    frame = _m15_frame(40, closes=closes)
    scan = _single_bar_scan(frame)
    computed = diagnostic.observations(scan, _all_groups_mask(scan), phase1._forward_index(frame, "15m"))
    parent_like = computed.loc[computed["group"].eq("m15_signal")].copy()
    diagnostic.verify_parent_returns(parent_like, computed)
    tampered = parent_like.copy()
    tampered.loc[tampered.horizon_minutes.eq(60), "return_pct"] = 99.0
    with pytest.raises(ValueError, match="return_pct"):
        diagnostic.verify_parent_returns(tampered, computed)
    shifted = parent_like.copy()
    shifted.loc[shifted.horizon_minutes.eq(240), "target_close_at"] = "2026-01-01T05:15:00Z"
    with pytest.raises(ValueError, match="target_close_at"):
        diagnostic.verify_parent_returns(shifted, computed)


def test_monthly_summaries_count_only_the_fixed_complete_population() -> None:
    # 62 days of M15 candles so both January and February triggers have exact targets.
    frame = _m15_frame(6000)
    scan = pd.DataFrame(
        {
            "trigger_close_at": ["2026-01-01T00:15:00Z", "2026-02-01T00:15:00Z"],
            "trigger_close_price": [100.0, 100.0],
        }
    )
    membership = {
        "m15_signal": pd.Series([True, True]),
        "gate_ready_no_cross": pd.Series([True, True]),
        "all_eligible_bars": pd.Series([True, True]),
    }
    rows = diagnostic.observations(scan, membership, phase1._forward_index(frame, "15m"))
    monthly = diagnostic.monthly_summaries(rows)
    assert set(monthly.month_utc) == {"2026-01", "2026-02"}
    assert monthly.n_included.eq(1).all()
    january = monthly.loc[monthly.month_utc.eq("2026-01") & monthly.horizon_minutes.eq(60)].iloc[0]
    assert january.mean_return_pct == pytest.approx(0.0)
    assert monthly.horizon_minutes.nunique() == 2


def _write_parent_packet(data_dir: Path, inputs: phase1.ValidatedInputs, packet: Path, signals: list[dict]) -> None:
    packet.mkdir(parents=True, exist_ok=True)
    columns = list(phase1.CSV_FIELDS)
    with (packet / "signals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = __import__("csv").DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(signals)
    files = {
        timeframe: {
            "path": str(inputs.paths[timeframe]),
            "sha256": inputs.source_report["files"][timeframe]["sha256"],
        }
        for timeframe in phase1.TIMEFRAMES
    }
    manifest = {
        "run_id": packet.name,
        "completion_status": "SUCCESS",
        "definition_version": phase1.DEFINITION_VERSION,
        "inputs": {"identity": {"venue_instrument": phase1.VENUE_INSTRUMENT}, "files": files},
    }
    summary = {
        "completion_status": "SUCCESS",
        "signal_counts": {"5m": 0, "15m": len(signals) // len(phase1.HORIZONS)},
        "baseline_comparator": {
            "by_timeframe": {
                "15m": {
                    "matched_window_start_close_utc": signals[0]["trigger_close_at"],
                    "matched_window_end_close_utc": signals[-len(phase1.HORIZONS)]["trigger_close_at"],
                }
            }
        },
    }
    (packet / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (packet / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (packet / "report.md").write_text("# synthetic parent\n", encoding="utf-8")
    assert data_dir.is_dir()


def test_end_to_end_synthetic_run_writes_a_complete_packet(tmp_path: Path) -> None:
    inputs, data_dir = _synthetic_inputs(tmp_path)
    assert data_dir is not None
    scan, _ = diagnostic.scan_population(
        inputs, datetime(2025, 10, 1, tzinfo=UTC), datetime(2025, 11, 10, tzinfo=UTC)
    )
    gated = scan.loc[
        scan.preparation_reason.eq(PREPARATION_READY) & scan.price_gates_pass.fillna(False).astype(bool)
    ]
    assert len(gated) >= 3
    chosen = gated.iloc[[0, len(gated) // 2, len(gated) - 1]]
    chosen_times = pd.to_datetime(chosen.trigger_close_at, utc=True)
    assert (chosen_times.diff().dropna() >= pd.Timedelta(hours=1)).all()

    source = phase1._forward_index(inputs.frames["15m"], "15m")
    rows: list[dict] = []
    for sequence, bar in enumerate(chosen.itertuples(), start=1):
        close_time = datetime.fromisoformat(bar.trigger_close_at.replace("Z", "+00:00"))
        price = float(bar.trigger_close_price)
        for horizon, minutes in phase1.HORIZONS:
            outcome = phase1._exact_forward_outcome_from_index(
                source, "15m", trigger_close=close_time, trigger_price=price, horizon_minutes=minutes
            )
            rows.append(
                {
                    **{field: "" for field in phase1.CSV_FIELDS},
                    "event_id": f"synthetic-{sequence}",
                    "sequence": sequence,
                    "timeframe": "15m",
                    "trigger_open_at": phase1._utc_iso(close_time - timedelta(minutes=15)),
                    "trigger_close_at": bar.trigger_close_at,
                    "trigger_close_price": str(price),
                    "decision_reason": "ALERT_FRESH_BULLISH_CROSS_H4_BULLISH",
                    "horizon": horizon,
                    "horizon_minutes": minutes,
                    **outcome,
                }
            )
    packet = tmp_path / "run_20260101T000000000000Z_00000000"
    _write_parent_packet(data_dir, inputs, packet, rows)

    produced = diagnostic.run(packet, tmp_path / "out", charts=False)
    manifest = json.loads((produced / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((produced / "summary.json").read_text(encoding="utf-8"))
    assert manifest["completion_status"] == "SUCCESS"
    assert manifest["parent"]["signal_count"] == 3
    assert manifest["population_counts"]["m15_signal"] == 3
    assert (
        manifest["population_counts"]["m15_signal"]
        <= manifest["population_counts"]["gate_ready_no_cross"]
        <= manifest["population_counts"]["all_eligible_bars"]
    )
    assert summary["alpha_assessment"] == "NOT_ASSESSED"
    scan_audit = manifest["scan"]
    assert (
        scan_audit["cross_and_gates_bar_count"]
        + scan_audit["cross_without_gates_bar_count"]
        + scan_audit["no_cross_bar_count"]
        == scan_audit["eligible_bar_count"]
    )
    assert (
        scan_audit["cross_and_gates_bar_count"] - manifest["population_counts"]["m15_signal"]
        == scan_audit["cooldown_suppressed_bar_count"]
    )
    assert manifest["parent_replay_counts"] is None
    assert scan_audit["price_gates_pass_bar_count"] == manifest["population_counts"]["gate_ready_no_cross"]
    for cell in summary["horizon_summaries"]:
        assert cell["populations"]["m15_signal"]["n_included"] == 3
    for name in ("observations.csv", "bars.csv", "monthly.csv", "report.md"):
        assert (produced / name).is_file()
    assert not (produced / "charts").exists()
    assert "not realized" in (produced / "report.md").read_text(encoding="utf-8")
    intervals = summary["contrast_uncertainty"]
    assert len(intervals) == len(diagnostic.HORIZONS) * 3
