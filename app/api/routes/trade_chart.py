"""
Trade chart route.

GET /api/trades/{trade_id}/chart — OHLCV candles around a trade with indicators.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.data.indicators import Indicators
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import RunConfig, Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])

DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backtest", "data"),
)

CONTEXT_CANDLES = 50  # candles before entry / after exit


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{trade_id}/chart")
def get_trade_chart(
    trade_id: int, db: Session = Depends(_get_db)
) -> list[dict[str, Any]]:
    trade = db.query(Trade).filter_by(id=trade_id).first()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    cfg = db.query(RunConfig).filter_by(run_id=trade.run_id).first()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Run config not found")

    symbol = trade.symbol
    timeframe = cfg.timeframe
    safe_sym = symbol.replace("/", "")
    csv_path = os.path.join(DATA_DIR, f"{safe_sym}_{timeframe}.csv")

    if not os.path.isfile(csv_path):
        raise HTTPException(
            status_code=404,
            detail=f"CSV data not found: {safe_sym}_{timeframe}.csv",
        )

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Locate entry/exit indices
    entry_time = pd.Timestamp(trade.entry_time)
    exit_time = pd.Timestamp(trade.exit_time) if trade.exit_time else entry_time

    entry_idx = df["timestamp"].searchsorted(entry_time, side="left")
    exit_idx = df["timestamp"].searchsorted(exit_time, side="right")

    start = max(0, int(entry_idx) - CONTEXT_CANDLES)
    end = min(len(df), int(exit_idx) + CONTEXT_CANDLES)
    window = df.iloc[start:end].copy()

    if window.empty:
        return []

    # Compute indicators on the full slice for accuracy
    indicators = Indicators()
    ind_df = indicators.compute(window)

    candles: list[dict[str, Any]] = []
    for _, row in ind_df.iterrows():
        ts = row["timestamp"]
        is_entry = abs((ts - entry_time).total_seconds()) < 1
        is_exit = trade.exit_time and abs((ts - exit_time).total_seconds()) < 1

        candle: dict[str, Any] = {
            "time": ts.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
            "is_entry": bool(is_entry),
            "is_exit": bool(is_exit),
        }

        # Add indicator columns (mapped to names frontend expects)
        col_map = {"rsi_14": "rsi", "rsi_wma45": "wma45", "rsi_ema9": "ema9"}
        for src, dst in col_map.items():
            if src in ind_df.columns:
                val = row[src]
                candle[dst] = None if pd.isna(val) else float(val)

        # Add SL tracking if available
        if trade.stop_loss_price is not None:
            candle["active_sl"] = float(trade.stop_loss_price)

        candles.append(candle)

    return candles
