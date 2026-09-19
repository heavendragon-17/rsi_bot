"""Regression tests for the Core V2.1 audit analysis research module.

The committed replay CSV/JSONL ledgers are git-ignored (about 100 MB), so
these tests exercise the module against a synthetic two-row ledger stub.
The historical artifacts under ``artifacts/core_v2_1/`` must remain
untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research import core_v2_1_audit_analysis as audit

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_FULL_REPLAY = REPO_ROOT / "artifacts" / "core_v2_1" / "full_replay"


def _ledger_rows() -> tuple[list[str], list[dict[str, str]]]:
    header = list(audit.EXPECTED_CSV_COLUMNS)
    base = {
        "venue": "BINANCE_FUTURES",
        "status": "evaluated",
        "reasons": "",
        "context_closed_at_json": "{}",
        "state_before_json": "{}",
        "state_after_json": "{}",
    }
    rows = [
        {
            **base,
            "sequence": "1",
            "trigger_closed_at": "2026-07-15T02:45:00+00:00",
            "symbol": "NEARUSDT",
            "event_type": "A_PLUS_LONG",
            "decision_kind": "A_PLUS_LONG",
            "decision_json": json.dumps(
                {
                    "kind": "A_PLUS_LONG",
                    "event": {
                        "event_type": "A_PLUS_LONG",
                        "trade_levels": {
                            "reference_entry": "2.019",
                            "reference_stop": "2.00434760408012847325",
                            "risk_1r": "0.01465239591987152675",
                            "tp1": "2.03365239591987152675",
                            "tp2": "2.04830479183974305350",
                            "tp3": "2.06295718775961458025",
                        },
                        "wait_bars_elapsed": None,
                    },
                    "reasons": [],
                }
            ),
        },
        {
            **base,
            "sequence": "2",
            "trigger_closed_at": "2026-07-15T03:00:00+00:00",
            "symbol": "NEARUSDT",
            "event_type": "WAIT_FOR_PULLBACK",
            "decision_kind": "WAIT_FOR_PULLBACK",
            "decision_json": json.dumps(
                {
                    "kind": "WAIT_FOR_PULLBACK",
                    "event": {
                        "event_type": "WAIT_FOR_PULLBACK",
                        "trade_levels": None,
                        "wait_bars_elapsed": 0,
                        "preferred_entry_zone": {"lower": "2.0", "upper": "2.01"},
                    },
                    "reasons": ["PRICE_EXTENDED_FROM_EMA21"],
                }
            ),
        },
    ]
    return header, rows


def test_read_csv_rows_rejects_header_drift(tmp_path: Path) -> None:
    bad = tmp_path / "core_v2_1_replay.csv"
    bad.write_text("sequence,symbol\n1,ETHUSDT\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header drifted"):
        audit._read_csv_rows(bad)


def test_counts_and_family_separation() -> None:
    header, rows = _ledger_rows()
    frame = pd.DataFrame(rows, columns=header)
    events = audit._build_events_frame(frame)
    counts = audit._counts(events.to_dict("records"), "event_type")
    assert counts == {"A_PLUS_LONG": 1, "WAIT_FOR_PULLBACK": 1}
    families = dict(zip(events["event_type"], events["family"], strict=True))
    assert families == {
        "A_PLUS_LONG": "immediate_long",
        "WAIT_FOR_PULLBACK": "pullback_long",
    }
    levels = events.iloc[0]
    assert levels["reference_entry"] == "2.019"
    assert levels["tp3"] == "2.06295718775961458025"
    assert events.iloc[1]["wait_bars_elapsed"] == 0


def test_metadata_recount_verification(tmp_path: Path) -> None:
    metadata_path = tmp_path / "core_v2_1_replay.metadata.json"
    metadata_path.write_text(
        json.dumps({"event_counts": {"A_PLUS_LONG": 1}, "window_mode": "full:common_window"}),
        encoding="utf-8",
    )
    check = audit._verify_metadata(metadata_path, {"A_PLUS_LONG": 1})
    assert check["event_counts_match_recount"] is True
    failing = audit._verify_metadata(metadata_path, {"A_PLUS_LONG": 2})
    assert failing["event_counts_match_recount"] is False
    assert failing["event_count_mismatches"]["A_PLUS_LONG"] == {
        "metadata": 1,
        "recount": 2,
    }


def test_historical_replay_artifacts_preserved() -> None:
    metadata = HISTORICAL_FULL_REPLAY / "core_v2_1_replay.metadata.json"
    assert metadata.is_file()
    recorded = json.loads(metadata.read_text(encoding="utf-8"))
    assert recorded["event_counts"] == {
        "A_PLUS_LONG": 63,
        "PULLBACK_LONG": 19,
        "WAIT_CANCELLED": 72,
        "WAIT_EXPIRED": 116,
        "WAIT_FOR_PULLBACK": 207,
    }
    assert recorded["ledger_records"] == 125_000
    readme = (REPO_ROOT / "artifacts" / "core_v2_1" / "README.md").read_text(encoding="utf-8")
    assert "9C477EB68506947EFF8446C1EFCDEB46ACE7BED4D2A8537457D759961E9E7D52" in readme