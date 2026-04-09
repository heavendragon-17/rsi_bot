"""
Benchmark buy-and-hold curve computation.

Reads local OHLCV CSV data and normalises it to the backtest's initial
capital so the resulting curve can be overlaid directly on the equity chart.
Auto-downloads missing or stale data before computing.
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import structlog

logger = structlog.get_logger()

BENCHMARK_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "HYPE/USDT",
    "BNB/USDT",
    "XRP/USDT",
]

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))


def _ensure_benchmark_data(
    benchmark: str,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    data_dir: str,
) -> None:
    """Ensure the local CSV covers [start_date, end_date].

    Three cases trigger a download:
    1. CSV is missing entirely → full backward fetch.
    2. CSV start is later than needed start_date (coverage gap) → delete + full backward fetch.
    3. CSV end is more than 2 days behind needed end_date (stale) → incremental forward fetch.
    """
    from app.backtest.data.download import calculate_candle_limit, download_data

    safe = benchmark.replace("/", "")
    csv_path = os.path.join(data_dir, f"{safe}_{timeframe}.csv")

    now = datetime.now()
    start_dt = datetime.fromisoformat(str(start_date)) if start_date else None
    end_dt = datetime.fromisoformat(str(end_date)) if end_date else now

    # Limit covers from earliest needed date to today + 30-day buffer for safety
    earliest = start_dt or end_dt
    span_days = max((now - earliest).days + 30, 60)
    limit = calculate_candle_limit(timeframe, days=span_days)

    needs_full = False
    needs_update = False

    if not os.path.exists(csv_path):
        logger.info("benchmark_csv_missing_will_download", symbol=benchmark, path=csv_path)
        needs_full = True
    else:
        try:
            df_meta = pd.read_csv(csv_path, usecols=["timestamp"])
            df_meta["timestamp"] = pd.to_datetime(df_meta["timestamp"])

            if df_meta.empty:
                needs_full = True
            else:
                csv_start = df_meta["timestamp"].min().date()
                csv_end = df_meta["timestamp"].max().date()
                need_start = start_dt.date() if start_dt else None
                need_end = end_dt.date()

                # Coverage gap: CSV doesn't reach back to start_date
                if need_start and csv_start > need_start:
                    logger.info(
                        "benchmark_coverage_gap",
                        symbol=benchmark,
                        csv_start=str(csv_start),
                        needed_start=str(need_start),
                    )
                    # Delete so download_data does a full backward fetch
                    os.remove(csv_path)
                    needs_full = True

                # Staleness: CSV tail is more than 2 days behind end_date
                elif (need_end - csv_end).days > 2:
                    logger.info(
                        "benchmark_data_stale",
                        symbol=benchmark,
                        csv_end=str(csv_end),
                        needed_end=str(need_end),
                        lag_days=(need_end - csv_end).days,
                    )
                    needs_update = True

        except Exception as exc:
            logger.warning("benchmark_check_error", symbol=benchmark, error=str(exc))
            needs_full = True

    if needs_full or needs_update:
        try:
            logger.info(
                "benchmark_downloading",
                symbol=benchmark,
                timeframe=timeframe,
                limit=limit,
                mode="full" if needs_full else "incremental",
            )
            download_data(benchmark, timeframe, limit, data_dir)
        except Exception as exc:
            logger.error("benchmark_download_failed", symbol=benchmark, error=str(exc))


def compute_benchmark_curve(
    benchmark: str,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    initial_capital: float,
    data_dir: str = DATA_DIR,
) -> list[dict]:
    """Compute buy-and-hold curve from a local OHLCV CSV file.

    Auto-downloads the CSV if it is missing, does not cover ``start_date``,
    or is stale relative to ``end_date``.

    Returns ``[{"date": "YYYY-MM-DD", "balance": float}]`` normalised so the
    first close price equals ``initial_capital``.  Returns ``[]`` when data
    cannot be fetched or the date range yields no rows.
    """
    safe = benchmark.replace("/", "")
    csv_path = os.path.join(data_dir, f"{safe}_{timeframe}.csv")

    # Download / refresh if needed (blocking; runs inside a worker thread)
    _ensure_benchmark_data(benchmark, timeframe, start_date, end_date, data_dir)

    if not os.path.exists(csv_path):
        logger.error("benchmark_csv_unavailable_after_download", symbol=benchmark)
        return []

    try:
        df = pd.read_csv(csv_path, usecols=["timestamp", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        if start_date:
            df = df[df["timestamp"] >= str(start_date)]
        if end_date:
            df = df[df["timestamp"] <= str(end_date)]

        df = df.reset_index(drop=True)
        if df.empty:
            logger.warning(
                "benchmark_no_data_in_range",
                symbol=benchmark,
                start=start_date,
                end=end_date,
            )
            return []

        first_close = float(df["close"].iloc[0])
        if first_close <= 0:
            return []

        dates = df["timestamp"].dt.strftime("%Y-%m-%d").tolist()
        balances = (df["close"] / first_close * initial_capital).round(2).tolist()

        logger.info(
            "benchmark_computed",
            symbol=benchmark,
            points=len(dates),
            first_date=dates[0] if dates else None,
            last_date=dates[-1] if dates else None,
        )
        return [{"date": d, "balance": b} for d, b in zip(dates, balances)]

    except Exception as exc:
        logger.error("benchmark_compute_error", symbol=benchmark, error=str(exc))
        return []
