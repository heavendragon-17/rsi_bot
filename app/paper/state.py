# app/paper/state.py
"""
Paper trading state dataclasses.

All state is in-memory only — resets on restart (by design per SPEC).
PaperTradeState is protected by an RLock for thread-safe access
from both the kline loop (symbol threads) and the aggTrade tick thread.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class PaperOrder:
    id: str
    symbol: str
    order_type: str                  # market | limit | stop_market
    side: str                        # BUY | SELL
    amount: Decimal
    price: Optional[Decimal]         # limit price (TP) or None
    stop_price: Optional[Decimal]    # for stop_market (SL)
    reduce_only: bool
    status: str                      # pending_open | pending | filled | cancelled
    created_at: float                # epoch seconds
    filled_at: Optional[float] = None
    fill_price: Optional[Decimal] = None


@dataclass
class PaperPosition:
    symbol: str
    side: str                                # always "long" (bot is LONG-only)
    amount: Decimal                          # current open contracts
    entry_price: Decimal
    initial_amount: Decimal                  # for R-multiple calc
    initial_risk: Decimal                    # (entry_price - sl_price) * initial_amount
    sl_order_id: Optional[str] = None
    tp_order_ids: Dict[str, str] = field(default_factory=dict)  # {"TP1": id, ...}
    lock_profit_price: Optional[Decimal] = None
    lock_profit_activated: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False


@dataclass
class ClosedTrade:
    symbol: str
    entry_price: Decimal
    exit_price: Decimal
    amount: Decimal
    side: str
    pnl_gross: Decimal                       # price movement only
    fees_paid: Decimal
    funding_paid: Decimal
    pnl_net: Decimal                         # gross - fees - funding
    r_multiple: Decimal                      # pnl_net / initial_risk
    exit_reason: str                         # TP1|TP2|TP3|HARD_SL|CANDLE_SL|TOGGLE_CLOSE|RESET
    opened_at: float
    closed_at: float


class PaperTradeState:
    """
    Thread-safe container for all paper trading state.
    Use the context manager (``with state.lock``) when performing
    multi-step reads/writes that must be atomic.
    """

    def __init__(self, initial_balance: Decimal):
        self.lock = threading.RLock()
        self.initial_balance: Decimal = initial_balance
        self.balance: Decimal = initial_balance
        self.positions: Dict[str, PaperPosition] = {}       # keyed by symbol
        self.pending_orders: Dict[str, PaperOrder] = {}     # keyed by order id
        self.closed_trades: List[ClosedTrade] = []
        self.total_fees_paid: Decimal = Decimal("0")
        self.total_funding_paid: Decimal = Decimal("0")
        self.is_paused: bool = False

    # ------------------------------------------------------------------
    # Convenience helpers (call under lock when needed)
    # ------------------------------------------------------------------

    def add_order(self, order: PaperOrder) -> None:
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
        """Reset all state to initial conditions (used by /paper_reset)."""
        with self.lock:
            self.balance = self.initial_balance
            self.positions.clear()
            self.pending_orders.clear()
            self.closed_trades.clear()
            self.total_fees_paid = Decimal("0")
            self.total_funding_paid = Decimal("0")
            self.is_paused = False
