"""Canonical per-trade DataFrame builder for the audit pipeline.

Reads `Trade` rows for a given `run_id` from the backtest database and
projects them onto the canonical audit schema documented in
`docs/17_audit/audit.md`. This is the single input adapter for `sanity.py`,
`bootstrap_ci.py`, and `deflated_sharpe.py` — those tests should never
talk to the ORM directly.

Output columns (sorted by entry_time ascending, positional index 0..N-1):

    entry_time     datetime64[ns]
    exit_time      datetime64[ns]
    side           object (str: SIDE_BUY="BUY" or SIDE_SELL="SELL")
    symbol         object (str)
    entry_price    float64
    exit_price     float64
    qty            float64
    ret_pct        float64        ← Trade.pnl_pct (already native Float)
    ret_abs        float64        ← Trade.pnl     (TEXT Decimal → float)
    holding_hours  float64        ← Trade.hold_time_hours (already Float)
    exit_reason    object (str)
    run_id         int64

Open trades (NULL `exit_time`) are dropped with a structlog warning; the
count is returned on `TradeLog.dropped_open_count` so the report can
surface it. Open trades have no realized PnL and would corrupt every
downstream statistic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import structlog
from sqlalchemy.orm import Session

from app.core.actions import SIDE_BUY, SIDE_SELL
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Trade

logger = structlog.get_logger()


# Engine-side legacy strings ("LONG"/"SHORT") emitted by BacktestReporter when
# building round-trips are normalized to the canonical SIDE_BUY/SIDE_SELL
# vocabulary defined in app/core/actions.py. Done at the adapter boundary so
# every downstream audit test consumes one vocabulary only.
_SIDE_NORMALIZATION = {
    "LONG": SIDE_BUY,
    "SHORT": SIDE_SELL,
    SIDE_BUY: SIDE_BUY,
    SIDE_SELL: SIDE_SELL,
}


def _normalize_side(raw: str) -> str:
    """Map persisted side string to canonical SIDE_BUY/SIDE_SELL."""
    if raw is None:
        return raw
    return _SIDE_NORMALIZATION.get(raw.upper(), raw.upper())


@dataclass(frozen=True)
class TradeLog:
    """Canonical audit input — DataFrame plus build metadata."""

    df: pd.DataFrame
    run_id: int
    dropped_open_count: int


_CANONICAL_COLUMNS = [
    "entry_time",
    "exit_time",
    "side",
    "symbol",
    "entry_price",
    "exit_price",
    "qty",
    "ret_pct",
    "ret_abs",
    "holding_hours",
    "exit_reason",
    "run_id",
]


def _decimal_text_to_float(val) -> float:
    """Convert a TEXT-stored Decimal string to float. NULL → NaN."""
    if val is None:
        return float("nan")
    return float(val)


def _native_to_float(val) -> float:
    """Pass-through for native Float columns. NULL → NaN."""
    if val is None:
        return float("nan")
    return float(val)


def build_trade_log(run_id: int, *, session: Session | None = None) -> TradeLog:
    """Build the canonical per-trade DataFrame for `run_id`.

    If `session` is provided the caller owns its lifecycle; otherwise a
    fresh `SessionLocal` is opened and closed here.
    """
    own_session = session is None
    db = session or SessionLocal()
    try:
        rows = (
            db.query(Trade)
            .filter(Trade.run_id == run_id)
            .order_by(Trade.entry_time.asc())
            .all()
        )
    finally:
        if own_session:
            db.close()

    raw_count = len(rows)
    closed = [t for t in rows if t.exit_time is not None]
    dropped = raw_count - len(closed)
    if dropped:
        logger.warning(
            "audit_open_trades_dropped",
            run_id=run_id,
            dropped_open_count=dropped,
            kept_closed_count=len(closed),
        )

    records = [
        {
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "side": _normalize_side(t.side),
            "symbol": t.symbol,
            "entry_price": _decimal_text_to_float(t.entry_price),
            "exit_price": _decimal_text_to_float(t.exit_price),
            "qty": _decimal_text_to_float(t.quantity),
            "ret_pct": _native_to_float(t.pnl_pct),
            "ret_abs": _decimal_text_to_float(t.pnl),
            "holding_hours": _native_to_float(t.hold_time_hours),
            "exit_reason": t.exit_reason,
            "run_id": int(t.run_id),
        }
        for t in closed
    ]

    df = pd.DataFrame.from_records(records, columns=_CANONICAL_COLUMNS)
    if not df.empty:
        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df["exit_time"] = pd.to_datetime(df["exit_time"])
    df = df.reset_index(drop=True)

    return TradeLog(df=df, run_id=run_id, dropped_open_count=dropped)
