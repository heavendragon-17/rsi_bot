# app/sim/state.py
"""
Sim trading state dataclasses.

All state is in-memory only — resets on restart (by design per SPEC).
SimTradeState is protected by an RLock for thread-safe access
from both the kline loop (symbol threads) and the aggTrade tick thread.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from decimal import Decimal


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
    side: str  # always "long" (bot is LONG-only)
    amount: Decimal  # current open contracts
    entry_price: Decimal
    initial_amount: Decimal  # for R-multiple calc
    initial_risk: Decimal  # (entry_price - sl_price) * initial_amount
    sl_order_id: str | None = None
    tp_order_ids: dict[str, str] = field(default_factory=dict)  # {"TP1": id, ...}
    lock_profit_price: Decimal | None = None
    lock_profit_activated: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False
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
    exit_reason: str  # TP1|TP2|TP3|HARD_SL|CANDLE_SL|TOGGLE_CLOSE|RESET
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
