"""Default report path helpers for the historical BTC alert replay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC_PLUS_7 = timezone(timedelta(hours=7), name="UTC+7")


def default_output_path(
    start_utc: datetime | None,
    end_utc: datetime | None,
    report_dir: Path,
) -> Path:
    start_label = (
        start_utc.astimezone(UTC_PLUS_7).strftime("%Y-%m-%d")
        if start_utc
        else "earliest"
    )
    end_label = (
        end_utc.astimezone(UTC_PLUS_7).strftime("%Y-%m-%d")
        if end_utc
        else "latest"
    )
    return report_dir / f"signal_replay_{start_label}_{end_label}.md"


def default_split_output_paths(
    start_utc: datetime | None,
    end_utc: datetime | None,
    report_dir: Path,
) -> tuple[Path, Path]:
    """Return the default M5 and M15 report paths."""

    combined_path = default_output_path(start_utc, end_utc, report_dir)
    return (
        combined_path.with_name(f"{combined_path.stem}_m5{combined_path.suffix}"),
        combined_path.with_name(f"{combined_path.stem}_m15{combined_path.suffix}"),
    )
