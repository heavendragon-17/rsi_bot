"""
Centralised data download, validation, and path management for backtest runners.

Deduplicates logic previously scattered across run_batch_analysis.py,
run_portfolio_backtest.py, and run_paper_tick_replay.py.
"""
from __future__ import annotations

import os

import pandas as pd
import structlog

from app.backtest.download_data import calculate_candle_limit, download_data

logger = structlog.get_logger()

BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(BACKTEST_DIR, "data")


class DataManager:
    """Download, validate, and cache backtest OHLCV data."""

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, timeframe: str = "15m"):
        self.data_dir = data_dir
        self.timeframe = timeframe
        self._shared_exchange = None

    # ── public API ──────────────────────────────────────────────────────

    def get_csv_path(self, symbol: str) -> str:
        safe = symbol.replace("/", "")
        return os.path.join(self.data_dir, f"{safe}_{self.timeframe}.csv")

    def needs_download(self, symbol: str, required_rows: int) -> bool:
        """Return *True* when the local CSV is missing, too short, or stale."""
        path = self.get_csv_path(symbol)
        if not os.path.exists(path):
            return True
        return self._is_stale_or_short(path, required_rows)

    def ensure_data(self, symbol: str, limit: int) -> str:
        """Download data for *symbol* if missing/stale and return the CSV path."""
        path = self.get_csv_path(symbol)
        if self.needs_download(symbol, limit):
            safe = symbol.replace("/", "")
            download_data(safe, self.timeframe, limit, self.data_dir)
            if not os.path.exists(path):
                raise FileNotFoundError(f"Download failed for {symbol}")
        return path

    def ensure_bulk_data(self, symbols: list[str], limit: int) -> dict[str, str]:
        """Download data for multiple symbols, sharing one ccxt exchange instance.

        Returns a mapping of ``{symbol: csv_path}``.
        """
        missing: list[tuple[str, str]] = []  # (symbol, safe_symbol)
        for symbol in symbols:
            if self.needs_download(symbol, limit):
                missing.append((symbol, symbol.replace("/", "")))

        if missing:
            exchange = self._get_shared_exchange()
            logger.info(
                "downloading_missing_data",
                count=len(missing),
                symbols=[s for s, _ in missing],
            )
            for symbol, safe in missing:
                download_data(safe, self.timeframe, limit, self.data_dir, exchange=exchange)
                path = self.get_csv_path(symbol)
                if not os.path.exists(path):
                    raise FileNotFoundError(f"Download failed for {symbol}")

        return {sym: self.get_csv_path(sym) for sym in symbols}

    # ── internals ───────────────────────────────────────────────────────

    def _get_shared_exchange(self):
        """Lazy-create a single ccxt exchange to avoid repeated load_markets()."""
        if self._shared_exchange is None:
            import ccxt

            self._shared_exchange = ccxt.binanceusdm()
            self._shared_exchange.load_markets()
        return self._shared_exchange

    def _is_stale_or_short(self, path: str, required_rows: int) -> bool:
        row_count = 0
        last_line = ""
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row_count += 1
                    last_line = line
        row_count -= 1  # subtract header

        if row_count < int(required_rows * 0.95):
            return True

        # Check recency
        try:
            last_ts_str = last_line.split(",")[0].strip()
            last_ts = pd.to_datetime(last_ts_str, errors="coerce")
            tf_str = self.timeframe.replace("m", "min").replace("h", "H").replace("d", "D")
            tf_delta = pd.to_timedelta(tf_str)
            now_utc7 = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
            if pd.notna(last_ts) and (now_utc7 - last_ts) > (tf_delta * 2):
                return True
        except Exception as exc:
            logger.warning("data_recency_check_error", path=path, error=str(exc))
            return True

        return False
