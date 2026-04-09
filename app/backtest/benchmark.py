"""
Benchmark buy-and-hold curve computation.

Reads local OHLCV CSV data and normalises it to the backtest's initial
capital so the resulting curve can be overlaid directly on the equity chart.
"""

from __future__ import annotations

import os

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


def compute_benchmark_curve(
    benchmark: str,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    initial_capital: float,
    data_dir: str = DATA_DIR,
) -> list[dict]:
    """Compute buy-and-hold curve from a local OHLCV CSV file.

    Returns ``[{"date": "YYYY-MM-DD", "balance": float}]`` normalised so the
    first close price equals ``initial_capital``.  Returns ``[]`` when the CSV
    is missing, empty, or the date range yields no rows.
    """
    safe = benchmark.replace("/", "")
    csv_path = os.path.join(data_dir, f"{safe}_{timeframe}.csv")

    if not os.path.exists(csv_path):
        logger.warning("benchmark_csv_missing", symbol=benchmark, path=csv_path)
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
