# app/sim/state.py
"""
Sim trading state dataclasses.

Balance / session anchor / cumulative fees survive a bot restart via a JSON
snapshot at SIM_STATE_FILE_PATH. Open positions and pending orders are NOT
persisted — they're rebuilt by cleanup_on_startup against the live exchange.
SimTradeState is protected by an RLock for thread-safe access from both the
kline loop (symbol threads) and the aggTrade tick thread.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import structlog

logger = structlog.get_logger()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class SimOrder:
    id: str
    symbol: str
    order_type: str  # market | limit | stop_market
    side: str  # BUY | SELL
    amount: Decimal
    price: Decimal | None  # limit price (TP) or None
    stop_price: Decimal | None  # for stop_market (SL)
    reduce_only: bool
    status: str  # pending_open | pending | filled | cancelled
    created_at: float  # epoch seconds
    filled_at: float | None = None
    fill_price: Decimal | None = None


@dataclass
class SimPosition:
    symbol: str
    side: str  # "long" or "short" (sim currently opens only longs, but field is direction-neutral)
    amount: Decimal  # current open contracts
    entry_price: Decimal
    initial_amount: Decimal  # for R-multiple calc
    initial_risk: Decimal  # |entry - soft_sl| * initial_amount — the *risk-sizing* SL, not the disaster stop
    sl_order_id: str | None = None
    tp_order_ids: dict[str, str] = field(default_factory=dict)  # {"TP1": id, ...}
    lock_profit_price: Decimal | None = None
    lock_profit_activated: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False
    moved_sl: bool = False  # True once the SL stop_market order has been replaced (lock-profit / trailing)
    indicators: dict[str, float] | None = None
    entry_fee: Decimal = Decimal("0")
    opened_at: float = 0.0


@dataclass
class ClosedTrade:
    symbol: str
    entry_price: Decimal
    exit_price: Decimal
    amount: Decimal
    side: str
    pnl_gross: Decimal  # price movement only
    fees_paid: Decimal
    funding_paid: Decimal
    pnl_net: Decimal  # gross - fees - funding
    r_multiple: Decimal  # pnl_net / initial_risk
    exit_reason: str  # TP1|TP2|TP3|HARD_SL|MOVED_SL|CANDLE_SL|TOGGLE_CLOSE|RESET
    opened_at: float
    closed_at: float


class SimTradeState:
    """
    Thread-safe container for all sim trading state.
    Use the context manager (``with state.lock``) when performing
    multi-step reads/writes that must be atomic.
    """

    def __init__(self, initial_balance: Decimal):
        self.lock = threading.RLock()
        self.initial_balance: Decimal = initial_balance
        self.balance: Decimal = initial_balance
        self.positions: dict[str, SimPosition] = {}  # keyed by symbol
        self.pending_orders: dict[str, SimOrder] = {}  # keyed by order id
        self.closed_trades: list[ClosedTrade] = []
        self.total_fees_paid: Decimal = Decimal("0")
        self.total_funding_paid: Decimal = Decimal("0")
        self.is_paused: bool = False

    # ------------------------------------------------------------------
    # Convenience helpers (call under lock when needed)
    # ------------------------------------------------------------------

    def add_order(self, order: SimOrder) -> None:
        with self.lock:
            self.pending_orders[order.id] = order

    def cancel_order(self, order_id: str) -> bool:
        with self.lock:
            order = self.pending_orders.pop(order_id, None)
            if order:
                order.status = "cancelled"
                return True
            return False

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        with self.lock:
            ids = [oid for oid, o in self.pending_orders.items() if o.symbol == symbol]
            for oid in ids:
                self.pending_orders[oid].status = "cancelled"
                del self.pending_orders[oid]
            return len(ids)

    def session_pnl(self) -> Decimal:
        return self.balance - self.initial_balance

    def reset(self) -> None:
        """Reset all state to initial conditions (used by /reset)."""
        with self.lock:
            self.balance = self.initial_balance
            self.positions.clear()
            self.pending_orders.clear()
            self.closed_trades.clear()
            self.total_fees_paid = Decimal("0")
            self.total_funding_paid = Decimal("0")
            self.is_paused = False
        # Wipe the on-disk snapshot too so a restart after /reset starts fresh.
        from app.core import constants as _c
        try:
            os.unlink(_c.SIM_STATE_FILE_PATH)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("sim_state_reset_unlink_failed", exc_info=True)

    # ------------------------------------------------------------------
    # Persistence — survives restarts so deploys don't wipe session P&L
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Serialize the parts of state worth persisting across restarts."""
        with self.lock:
            return {
                "balance": str(self.balance),
                "initial_balance": str(self.initial_balance),
                "total_fees_paid": str(self.total_fees_paid),
                "total_funding_paid": str(self.total_funding_paid),
                "closed_trades_count": len(self.closed_trades),
            }

    def write_snapshot(self, path: str | None = None) -> None:
        """Atomically persist the snapshot to disk."""
        if path is None:
            from app.core import constants as _c
            path = _c.SIM_STATE_FILE_PATH
        data = self.snapshot()
        dir_name = os.path.dirname(path) or tempfile.gettempdir()
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            logger.warning("sim_state_snapshot_write_failed", exc_info=True)

    def try_restore(self, sim_cfg: dict, path: str | None = None) -> bool:
        """Restore balance/anchor from a previous snapshot if present.

        Returns True if a snapshot was applied. Skips restore (and removes the
        snapshot) when the configured ``initial_balance`` differs from the
        snapshot's anchor — that signals a config change that should reset the
        session rather than carry forward.
        """
        if path is None:
            from app.core import constants as _c
            path = _c.SIM_STATE_FILE_PATH
        try:
            with open(path) as f:
                snap = json.load(f)
        except FileNotFoundError:
            return False
        except (OSError, json.JSONDecodeError):
            logger.warning("sim_state_snapshot_read_failed", exc_info=True)
            return False

        try:
            snap_initial = Decimal(snap["initial_balance"])
        except (KeyError, ValueError, TypeError):
            return False

        configured_initial = Decimal(str((sim_cfg or {}).get("initial_balance", self.initial_balance)))
        if snap_initial != configured_initial:
            logger.info(
                "sim_state_snapshot_discarded_config_changed",
                snapshot_initial=str(snap_initial),
                configured_initial=str(configured_initial),
            )
            try:
                os.unlink(path)
            except OSError:
                pass
            return False

        with self.lock:
            try:
                self.balance = Decimal(snap["balance"])
                self.initial_balance = snap_initial
                self.total_fees_paid = Decimal(snap.get("total_fees_paid", "0"))
                self.total_funding_paid = Decimal(snap.get("total_funding_paid", "0"))
            except (KeyError, ValueError, TypeError):
                logger.warning("sim_state_snapshot_apply_failed", exc_info=True)
                return False
        logger.info(
            "sim_state_restored",
            balance=str(self.balance),
            initial_balance=str(self.initial_balance),
        )
        return True
