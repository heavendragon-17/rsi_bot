"""
Inline data download — downloads CSV if missing, with file lock + SSE progress.

Used by backtest workers when data file doesn't exist.
"""

from __future__ import annotations

import os
import sys
from typing import Callable

import structlog

from app.backtest.data.download import calculate_candle_limit, download_data

logger = structlog.get_logger()

_IS_WIN = sys.platform == "win32"


def _lock_file(f) -> None:
    if _IS_WIN:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    if _IS_WIN:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def download_if_missing(
    *,
    csv_path: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    run_id: int,
    loop,
    publish_event_fn: Callable,
) -> None:
    """Download data file if it doesn't exist. Thread-safe via file lock."""
    if os.path.exists(csv_path):
        return

    lock_path = f"{csv_path}.lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    with open(lock_path, "w") as lock_file:
        _lock_file(lock_file)
        try:
            # Double-check after acquiring lock (another worker may have finished)
            if os.path.exists(csv_path):
                return

            # Calculate how many candles we need from date range
            from datetime import date as date_cls

            d_start = date_cls.fromisoformat(start_date)
            d_end = date_cls.fromisoformat(end_date)
            days = (d_end - d_start).days
            if days <= 0:
                days = 365
            limit = calculate_candle_limit(timeframe, days=days)

            publish_event_fn(run_id, loop, "download_progress", {
                "pct": 0, "symbol": symbol,
                "candles_fetched": 0, "candles_total": limit,
            })

            output_dir = os.path.dirname(csv_path)

            download_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                output_dir=output_dir,
                on_progress=lambda fetched, total: publish_event_fn(
                    run_id, loop, "download_progress", {
                        "pct": int(fetched / total * 100) if total else 0,
                        "symbol": symbol,
                        "candles_fetched": fetched,
                        "candles_total": total,
                    }
                ),
            )

            publish_event_fn(run_id, loop, "download_complete", {
                "symbol": symbol,
            })

        finally:
            _unlock_file(lock_file)
