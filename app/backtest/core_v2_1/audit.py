"""Structured audit ledger for deterministic Core V2.1 replay evidence."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ReplayAuditRecord:
    sequence: int
    trigger_closed_at: pd.Timestamp
    symbol: str
    venue: str
    context_closed_at: Mapping[str, str]
    state_before: Any
    decision: Any
    state_after: Any
    status: str = "evaluated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "trigger_closed_at": self.trigger_closed_at.isoformat(),
            "symbol": self.symbol,
            "venue": self.venue,
            "context_closed_at": dict(self.context_closed_at),
            "state_before": to_jsonable(self.state_before),
            "decision": to_jsonable(self.decision),
            "state_after": to_jsonable(self.state_after),
            "status": self.status,
        }


@dataclass(frozen=True)
class LedgerPaths:
    jsonl: Path
    csv: Path
    metadata: Path


class AuditLedger:
    """Append-only in-memory ledger with atomic, portable exports."""

    def __init__(self) -> None:
        self._records: list[ReplayAuditRecord] = []

    @property
    def records(self) -> tuple[ReplayAuditRecord, ...]:
        return tuple(self._records)

    def append(self, record: ReplayAuditRecord) -> None:
        expected = len(self._records) + 1
        if record.sequence != expected:
            raise ValueError(f"Audit sequence must be contiguous: expected {expected}, got {record.sequence}")
        if self._records and record.trigger_closed_at < self._records[-1].trigger_closed_at:
            raise ValueError("Audit ledger trigger times must be chronological")
        self._records.append(record)

    def export(
        self,
        output_dir: str | Path,
        *,
        metadata: Mapping[str, Any],
        prefix: str = "core_v2_1_replay",
    ) -> LedgerPaths:
        """Write full JSONL, review-friendly CSV, and run metadata atomically."""

        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        paths = LedgerPaths(
            jsonl=directory / f"{prefix}.jsonl",
            csv=directory / f"{prefix}.csv",
            metadata=directory / f"{prefix}.metadata.json",
        )
        rows = [record.to_dict() for record in self._records]
        _atomic_text(paths.jsonl, "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        _write_csv_atomic(paths.csv, rows)
        run_metadata = {
            "schema_version": 1,
            "ledger_records": len(rows),
            "first_trigger_closed_at": rows[0]["trigger_closed_at"] if rows else None,
            "last_trigger_closed_at": rows[-1]["trigger_closed_at"] if rows else None,
            **to_jsonable(dict(metadata)),
        }
        _atomic_text(paths.metadata, json.dumps(run_metadata, indent=2, sort_keys=True) + "\n")
        return paths


def to_jsonable(value: Any) -> Any:
    """Recursively serialize strategy dataclasses, enums, pandas, and Decimal."""

    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return [to_jsonable(item) for item in sorted(value, key=lambda item: repr(item))]
    if hasattr(value, "to_dict"):
        return to_jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    fieldnames = (
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
    try:
        with temp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                decision = row.get("decision") or {}
                event = (decision.get("event") or {}) if isinstance(decision, dict) else {}
                reasons = (
                    decision.get("reasons") or event.get("reasons") or []
                    if isinstance(decision, dict)
                    else []
                )
                writer.writerow(
                    {
                        "sequence": row["sequence"],
                        "trigger_closed_at": row["trigger_closed_at"],
                        "symbol": row["symbol"],
                        "venue": row["venue"],
                        "status": row["status"],
                        "event_type": event.get("event_type", "") if isinstance(event, dict) else "",
                        "decision_kind": decision.get("kind", "") if isinstance(decision, dict) else "",
                        "reasons": "|".join(str(reason) for reason in reasons),
                        "context_closed_at_json": json.dumps(row["context_closed_at"], sort_keys=True),
                        "state_before_json": json.dumps(row["state_before"], sort_keys=True),
                        "decision_json": json.dumps(row["decision"], sort_keys=True),
                        "state_after_json": json.dumps(row["state_after"], sort_keys=True),
                    }
                )
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _atomic_text(path: Path, content: str) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
