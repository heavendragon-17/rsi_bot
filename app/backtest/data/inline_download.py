"""
Inline data download — downloads CSV if missing, with thread lock + SSE progress.

Used by backtest workers when data file doesn't exist.

Note: uses threading.Lock (not fcntl) so it works on both Linux and Windows.
All workers run inside a single-process ThreadPoolExecutor, so a threading
lock gives the same "only one download at a time per symbol" guarantee that
a file lock would, without any OS-specific dependencies.
"""

from __future__ import annotations

import os
import sys
import threading
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

# One lock per CSV path — prevents two threads downloading the same file.
_download_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def _get_lock(csv_path: str) -> threading.Lock:
    with _meta_lock:
        if csv_path not in _download_locks:
            _download_locks[csv_path] = threading.Lock()
        return _download_locks[csv_path]


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
    """Download data file if it doesn't exist. Thread-safe via threading.Lock."""
    if os.path.exists(csv_path):
        return

    lock = _get_lock(csv_path)
    with lock:
        # Double-check after acquiring lock (another thread may have finished)
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
