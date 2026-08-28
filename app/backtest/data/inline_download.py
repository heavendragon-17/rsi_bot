"""
Inline data download — downloads CSV if missing, with thread lock + SSE progress.

Used by backtest workers when data file doesn't exist.

All workers run inside a single-process `ThreadPoolExecutor`, so a
`threading.Lock` provides the required "only one download at a time per
symbol" guarantee without OS-specific file locking.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

import structlog

from app.backtest.data.download import calculate_candle_limit, download_data

logger = structlog.get_logger()

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
    """Download (or update) data file when it's missing or doesn't cover end_date."""

    def _csv_covers_end() -> bool:
        """True if CSV exists and its last timestamp >= requested end_date."""
        if not os.path.exists(csv_path):
            return False
        if not end_date:
            return True  # no upper bound → assume current file is fine
        try:
            import pandas as pd

            df_check = pd.read_csv(csv_path, usecols=["timestamp"])
            df_check["timestamp"] = pd.to_datetime(df_check["timestamp"])
            last_ts = df_check["timestamp"].max()
            covered = bool(pd.Timestamp(end_date) <= last_ts)
            if not covered:
                logger.info(
                    "csv_stale_will_fetch_forward",
                    symbol=symbol,
                    csv_last=str(last_ts.date()),
                    requested_end=end_date,
                )
            return covered
        except Exception as e:
            logger.warning("csv_coverage_check_failed", error=str(e))
            return False

    if _csv_covers_end():
        return

    lock = _get_lock(csv_path)
    with lock:
        # Re-check inside lock — another thread may have already fetched
        if _csv_covers_end():
            return

        # Calculate how many candles we need from date range
        from datetime import date as date_cls

        d_start = date_cls.fromisoformat(start_date)
        d_end = date_cls.fromisoformat(end_date)
        days = (d_end - d_start).days
        if days <= 0:
            days = 365
        limit = calculate_candle_limit(timeframe, days=days)

        publish_event_fn(
            run_id,
            loop,
            "download_progress",
            {
                "pct": 0,
                "symbol": symbol,
                "candles_fetched": 0,
                "candles_total": limit,
            },
        )

        output_dir = os.path.dirname(csv_path)

        download_data(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            output_dir=output_dir,
            on_progress=lambda fetched, total: publish_event_fn(
                run_id,
                loop,
                "download_progress",
                {
                    "pct": int(fetched / total * 100) if total else 0,
                    "symbol": symbol,
                    "candles_fetched": fetched,
                    "candles_total": total,
                },
            ),
        )

        publish_event_fn(
            run_id,
            loop,
            "download_complete",
            {
                "symbol": symbol,
            },
        )
