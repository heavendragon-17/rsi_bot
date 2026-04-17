"""
Benchmark buy-and-hold curve computation.

Reads local OHLCV CSV data and normalises it to the backtest's initial
capital so the resulting curve can be overlaid directly on the equity chart.

Gap-filling strategy: compute exactly what range [start_date, end_date] is
needed, check what the local CSV already covers, and download ONLY the missing
portions (left gap, right gap, or full range if no local data exists).
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_ohlcv_range(
    benchmark: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
) -> pd.DataFrame | None:
    """Fetch OHLCV candles for [since_ms, until_ms] (UTC milliseconds).

    Returns a DataFrame with UTC+7 timestamps (same convention as
    download.py) or None if no candles were returned by the exchange.
    """
    import time as _time

    import ccxt

    exchange = ccxt.binanceusdm()
    exchange.load_markets()

    # binanceusdm requires perpetual-futures format: "BTC/USDT:USDT"
    fetch_symbol = benchmark
    if ":" not in benchmark and "/USDT" in benchmark:
        fetch_symbol = benchmark + ":USDT"

    candles: list = []
    cursor = since_ms

    while cursor <= until_ms:
        _time.sleep(0.35)
        batch = exchange.fetch_ohlcv(fetch_symbol, timeframe, since=cursor, limit=1000)
        if not batch:
            break
        in_range = [c for c in batch if c[0] <= until_ms]
        candles.extend(in_range)
        if not in_range or batch[-1][0] >= until_ms:
            break
        cursor = batch[-1][0] + 1

    if not candles:
        return None

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    # Match download.py convention: store as UTC+7
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms") + pd.Timedelta(hours=7)
    return df


def _ensure_benchmark_range(
    benchmark: str,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    data_dir: str,
) -> None:
    """Ensure the local CSV contains data for [start_date, end_date].

    Computes coverage gaps against what the CSV already holds and fetches
    only the missing left / right portions — never re-downloads data we have.
    """
    safe = benchmark.replace("/", "")
    csv_path = os.path.join(data_dir, f"{safe}_{timeframe}.csv")
    os.makedirs(data_dir, exist_ok=True)

    need_start = pd.Timestamp(start_date) if start_date else pd.Timestamp.now() - pd.Timedelta(days=365)
    need_end = pd.Timestamp(end_date) if end_date else pd.Timestamp.now()

    # ── Load existing data ──────────────────────────────────────────────────
    existing: pd.DataFrame | None = None
    if os.path.exists(csv_path):
        try:
            existing = pd.read_csv(csv_path)
            existing["timestamp"] = pd.to_datetime(existing["timestamp"])
            existing = (
                existing.sort_values("timestamp")
                .drop_duplicates("timestamp")
                .reset_index(drop=True)
            )
        except Exception as exc:
            logger.warning("benchmark_load_error", symbol=benchmark, error=str(exc))
            existing = None

    # ── Identify gaps ───────────────────────────────────────────────────────
    # Gaps are expressed as (since_ms_utc, until_ms_utc) pairs for the API.
    gaps: list[tuple[int, int]] = []

    if existing is None or existing.empty:
        gaps.append((
            int(need_start.timestamp() * 1000),
            int(need_end.timestamp() * 1000),
        ))
        logger.info(
            "benchmark_no_local_data",
            symbol=benchmark,
            range_start=str(need_start.date()),
            range_end=str(need_end.date()),
        )
    else:
        csv_start = existing["timestamp"].min()
        csv_end = existing["timestamp"].max()

        # Left gap: need data before what we have
        if need_start.date() < csv_start.date():
            # until_ms: convert UTC+7 csv_start back to UTC ms, step back 1 ms
            gap_until_ms = int((csv_start - pd.Timedelta(hours=7)).timestamp() * 1000) - 1
            gaps.append((int(need_start.timestamp() * 1000), gap_until_ms))
            logger.info(
                "benchmark_left_gap",
                symbol=benchmark,
                need=str(need_start.date()),
                have_from=str(csv_start.date()),
            )

        # Right gap: need data after what we have
        if need_end.date() > csv_end.date():
            # since_ms: convert UTC+7 csv_end back to UTC ms, step forward 1 ms
            gap_since_ms = int((csv_end - pd.Timedelta(hours=7)).timestamp() * 1000) + 1
            gaps.append((gap_since_ms, int(need_end.timestamp() * 1000)))
            logger.info(
                "benchmark_right_gap",
                symbol=benchmark,
                have_until=str(csv_end.date()),
                need=str(need_end.date()),
            )

    if not gaps:
        return  # CSV already covers the full range — nothing to do

    # ── Fetch missing chunks ────────────────────────────────────────────────
    frames: list[pd.DataFrame] = []
    if existing is not None and not existing.empty:
        frames.append(existing)

    for since_ms, until_ms in gaps:
        try:
            logger.info(
                "benchmark_fetching_gap",
                symbol=benchmark,
                since_ms=since_ms,
                until_ms=until_ms,
            )
            chunk = _fetch_ohlcv_range(benchmark, timeframe, since_ms, until_ms)
            if chunk is not None and not chunk.empty:
                frames.append(chunk)
                logger.info("benchmark_gap_fetched", symbol=benchmark, rows=len(chunk))
            else:
                logger.warning("benchmark_gap_empty", symbol=benchmark,
                               since_ms=since_ms, until_ms=until_ms)
        except Exception as exc:
            logger.error("benchmark_fetch_gap_failed", symbol=benchmark, error=str(exc))

    # ── Merge and save ──────────────────────────────────────────────────────
    if frames:
        merged = (
            pd.concat(frames, ignore_index=True)
            .sort_values("timestamp")
            .drop_duplicates("timestamp", keep="last")
            .reset_index(drop=True)
        )
        merged.to_csv(csv_path, index=False)
        logger.info(
            "benchmark_csv_updated",
            symbol=benchmark,
            total_rows=len(merged),
            start=str(merged["timestamp"].min()),
            end=str(merged["timestamp"].max()),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_benchmark_curve(
    benchmark: str,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    initial_capital: float,
    data_dir: str = DATA_DIR,
) -> list[dict]:
    """Compute a buy-and-hold curve normalised to ``initial_capital``.

    Automatically fills any coverage gaps in the local CSV before computing,
    so the returned curve always covers [start_date, end_date] when the
    exchange has data for that range.

    Returns ``[{"date": "YYYY-MM-DD", "balance": float}]``.
    Returns ``[]`` on error or when the date range yields no rows.
    """
    safe = benchmark.replace("/", "")
    csv_path = os.path.join(data_dir, f"{safe}_{timeframe}.csv")

    # Fill any gaps (blocking; runs in a worker thread, not the API event loop)
    _ensure_benchmark_range(benchmark, timeframe, start_date, end_date, data_dir)

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

        # Reduce to one point per calendar day (last close of each day).
        # The CSV stores one row per candle (e.g. 96 rows/day for 15m), so
        # without this step the chart receives duplicate "YYYY-MM-DD" timestamps
        # and Lightweight Charts throws "data must be asc ordered by time".
        df["date"] = df["timestamp"].dt.strftime("%Y-%m-%d")
        df = df.groupby("date", sort=True).last().reset_index()

        first_close = float(df["close"].iloc[0])
        if first_close <= 0:
            return []

        dates = df["date"].tolist()
        balances = (df["close"] / first_close * initial_capital).round(2).tolist()

        logger.info(
            "benchmark_computed",
            symbol=benchmark,
            points=len(dates),
            first_date=dates[0] if dates else None,
            last_date=dates[-1] if dates else None,
        )
        return [{"date": d, "balance": b} for d, b in zip(dates, balances, strict=False)]

    except Exception as exc:
        logger.error("benchmark_compute_error", symbol=benchmark, error=str(exc))
        return []
