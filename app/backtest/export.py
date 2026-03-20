"""
Signal / report export utilities for backtest runners.

Extracted from run_batch_analysis.py (CSV) and run_portfolio_backtest.py (JSON).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


# ── CSV signal export ───────────────────────────────────────────────────────

def export_signals_to_csv(
    engine, symbol: str, output_dir: str, debug: bool = False
) -> str | None:
    """Export per-symbol trade signals to CSV with robust timestamp handling.

    Returns the CSV path on success, *None* on failure.
    """
    signals: list[dict] = []

    if hasattr(engine.strategy, "signal_history"):
        signals = engine.strategy.signal_history
    elif hasattr(engine.exchange, "trade_history"):
        signals = _reconstruct_signals(engine.exchange.trade_history, symbol)
    else:
        logger.warning("no_trade_history", symbol=symbol)
        return None

    if not signals:
        return None

    try:
        df = pd.DataFrame(signals)
        if "timestamp" in df.columns:
            try:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.sort_values("timestamp")
            except Exception:
                pass
        elif "trade_index" in df.columns:
            df = df.sort_values("trade_index")

        safe_symbol = symbol.replace("/", "_")
        csv_path = os.path.join(output_dir, f"signals_{safe_symbol}.csv")
        df.to_csv(csv_path, index=False)
        logger.info("signals_exported", symbol=symbol, path=csv_path, count=len(df))
        return csv_path
    except Exception as exc:
        logger.error("signal_export_error", symbol=symbol, error=str(exc))
        return None


def _reconstruct_signals(trade_history: list, symbol: str) -> list[dict]:
    """Rebuild signal records from an exchange trade_history list."""
    if not trade_history:
        return []

    sample = trade_history[0] if trade_history else {}
    available = list(sample.keys()) if isinstance(sample, dict) else []

    timestamp_field = None
    for field in ("timestamp", "datetime", "time", "date", "created_at", "entry_time", "exit_time"):
        if field in available:
            timestamp_field = field
            break

    signals: list[dict] = []
    for idx, trade in enumerate(trade_history):
        ts = _normalise_timestamp(trade, timestamp_field, idx)
        signal = {
            "timestamp": ts,
            "symbol": symbol,
            "trade_index": idx,
            "side": trade.get("side", "unknown"),
            "signal_type": "ENTRY" if trade.get("side") == "buy" else "EXIT",
            "price": float(trade.get("price", 0.0)),
            "amount": float(trade.get("amount", 0.0)),
            "order_type": trade.get("type", "market"),
            "reason": trade.get("reason", "unknown"),
        }
        for key, value in trade.items():
            if key not in signal and key != timestamp_field:
                signal[key] = _safe_value(value)
        signals.append(signal)
    return signals


def _normalise_timestamp(trade: dict, field: str | None, idx: int) -> str:
    if field and field in trade:
        ts = trade[field]
    elif "id" in trade:
        return f"trade_{trade['id']}"
    else:
        return f"trade_{idx:04d}"

    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(ts, pd.Timestamp):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if ts is None:
        return f"trade_{idx:04d}"
    return str(ts)


def _safe_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


# ── combined CSV ────────────────────────────────────────────────────────────

def export_combined_signals(batch_results: list, output_dir: str) -> str | None:
    """Combine per-symbol signal CSVs into a single master CSV."""
    all_dfs: list[pd.DataFrame] = []
    for result in batch_results:
        symbol = result["symbol"]
        safe = symbol.replace("/", "_")
        csv_path = os.path.join(output_dir, f"signals_{safe}.csv")
        if os.path.exists(csv_path):
            all_dfs.append(pd.read_csv(csv_path))

    if not all_dfs:
        return None

    combined = pd.concat(all_dfs, ignore_index=True)
    if "timestamp" in combined.columns:
        combined = combined.sort_values("timestamp")

    master_path = os.path.join(output_dir, "all_signals_combined.csv")
    combined.to_csv(master_path, index=False)
    logger.info("combined_signals_exported", path=master_path, total=len(combined))
    return master_path


# ── JSON report ─────────────────────────────────────────────────────────────

def export_json_report(results: dict, path: str) -> None:
    """Export a JSON report suitable for AI agent debugging."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, default=_safe_serialize, indent=2)
        logger.info("json_report_saved", path=path)
    except Exception as exc:
        logger.error("json_export_error", path=path, error=str(exc))


def _safe_serialize(obj):
    if isinstance(obj, (pd.Timestamp, pd.DatetimeIndex)):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return obj.to_list()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if pd.isna(obj):
        return None
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)
