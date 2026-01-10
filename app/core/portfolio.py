"""
Layer 3: Execution - Portfolio Manager
=======================================
Handles position management, order execution, TP/SL placement.

TP handling:
- Strategy emits SELL with reason starting: "TP1", "TP2", "TP3"
- PortfolioManager will partial-close accordingly.
"""

from __future__ import annotations

from typing import Dict, Optional
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime

from app.core.interfaces import IExchange
from app.core.events import SignalEvent


@dataclass
class Position:
    """
    Represents an open position with TP/SL tracking.
    """
    symbol: str
    amount: Decimal
    entry_price: Decimal
    side: str  # 'BUY' (Long)
    timestamp: datetime

    # TP/SL prices (from SignalEvent)
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None

    # Order tracking
    sl_order_id: Optional[str] = None

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False


class PortfolioManager:
    """
    Manages positions, executes orders, and handles TP/SL.

    Notes for backtest:
    - SL can fill inside MockExchange via pending limit orders.
    - Therefore we MUST sync portfolio state from exchange frequently.
    """

    def __init__(self, exchange: IExchange, config: dict):
        self.exchange = exchange
        self.config = config
        self.positions: Dict[str, Position] = {}

        # Risk settings
        risk_cfg = config.get("risk", {})
        self.max_position_size_pct = Decimal(str(risk_cfg.get("max_position_size_pct", 0.99)))

        # TP percentages (how much to close at each level)
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.33)))  # close 1/3
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))  # close 1/2 of remaining
        # TP3 closes 100% remaining

    # -------------------------
    # Helpers
    # -------------------------
    def sync_balance(self) -> Decimal:
        return self.exchange.get_balance()

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def sync_from_exchange(self) -> None:
        """
        Make portfolio positions consistent with exchange positions.
        If SL filled inside exchange, exchange.positions will no longer have symbol.
        """
        if not hasattr(self.exchange, "positions"):
            return

        for sym in list(self.positions.keys()):
            if sym not in self.exchange.positions:
                # Position is gone on exchange -> remove locally
                self.positions.pop(sym, None)

    # -------------------------
    # Main entry
    # -------------------------
    def on_signal(self, signal: SignalEvent):
        """
        Process a trading signal.
        - BUY: open position + place SL limit
        - SELL: TP1/TP2/TP3 partial/full close OR full close
        """
        # IMPORTANT: always sync first (SL may have closed the position)
        self.sync_from_exchange()

        if signal.signal_type == "BUY":
            balance = self.sync_balance()
            return self._handle_buy_signal(signal, balance)

        if signal.signal_type == "SELL":
            # If SL already closed it, just ignore quietly
            if signal.symbol not in self.positions:
                return None

            reason = (signal.reason or "").strip().upper()

            if reason.startswith("TP1"):
                return self.execute_partial_close(signal.symbol, "TP1")
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2")
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3")

            # Any other SELL -> close full
            return self._handle_full_sell(signal.symbol)

        return None

    # -------------------------
    # BUY logic
    # -------------------------
    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal):
        if signal.symbol in self.positions:
            # already in a trade
            return None

        price = signal.price
        if price <= Decimal("0"):
            return None

        # Position sizing in quote currency (e.g. USDT)
        amount_quote = balance * self.max_position_size_pct
        amount = amount_quote / price

        # Execute market BUY
        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type="MARKET",
            side="BUY",
            amount=amount,
        )

        if not order:
            return None

        # Create position record
        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            amount=amount,
            entry_price=price,
            side="BUY",
            timestamp=signal.timestamp,
            tp1_price=signal.tp1_price,
            tp2_price=signal.tp2_price,
            tp3_price=signal.tp3_price,
            sl_price=signal.sl_price,
        )

        # Place SL limit order if provided
        if signal.sl_price is not None:
            sl_order = self.exchange.create_order(
                symbol=signal.symbol,
                order_type="LIMIT",
                side="SELL",
                amount=amount,
                price=signal.sl_price,
            )
            if sl_order:
                self.positions[signal.symbol].sl_order_id = sl_order.get("id")
                print(f"Placed limit SL order at {signal.sl_price}")

        print(f"Executed BUY for {signal.symbol} @ {price}")
        print(f"  TP1: {signal.tp1_price}")
        print(f"  TP2: {signal.tp2_price}")
        print(f"  TP3: {signal.tp3_price}")
        print(f"  SL : {signal.sl_price}")

        return order

    # -------------------------
    # SELL logic
    # -------------------------
    def _handle_full_sell(self, symbol: str):
        """
        Close entire remaining position at market and cleanup.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Cancel SL order if any
        if pos.sl_order_id:
            self.exchange.cancel_order(pos.sl_order_id, symbol)

        # Market SELL full amount
        order = self.exchange.create_order(
            symbol=symbol,
            order_type="MARKET",
            side="SELL",
            amount=pos.amount,
        )

        if order:
            self.positions.pop(symbol, None)
            print(f"Executed FULL SELL for {symbol}")
            return order

        return None

    def execute_partial_close(self, symbol: str, tp_level: str):
        """
        Execute partial close for TP levels:
        - TP1: close tp1_close_pct of original, move SL to entry on remaining
        - TP2: close tp2_close_pct of remaining
        - TP3: close all remaining
        """
        # Sync first in case SL filled
        self.sync_from_exchange()

        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        tp_level = tp_level.upper().strip()

        if tp_level == "TP1" and pos.tp1_hit:
            return None
        if tp_level == "TP2" and pos.tp2_hit:
            return None
        if tp_level == "TP3" and pos.tp3_hit:
            return None

        close_amount = Decimal("0")

        if tp_level == "TP1":
            close_amount = pos.amount * self.tp1_close_pct
            pos.tp1_hit = True

        elif tp_level == "TP2":
            close_amount = pos.amount * self.tp2_close_pct
            pos.tp2_hit = True

        elif tp_level == "TP3":
            close_amount = pos.amount
            pos.tp3_hit = True

        if close_amount <= Decimal("0"):
            return None

        # Execute partial SELL
        order = self.exchange.create_order(
            symbol=symbol,
            order_type="MARKET",
            side="SELL",
            amount=close_amount,
        )

        if not order:
            return None

        pos.amount -= close_amount
        print(f"Executed {tp_level} SELL for {symbol}: {close_amount}")

        # TP1 special: move SL to entry for remaining
        if tp_level == "TP1" and pos.amount > Decimal("0"):
            if pos.sl_order_id:
                self.exchange.cancel_order(pos.sl_order_id, symbol)

            new_sl = pos.entry_price  # breakeven SL
            new_sl_order = self.exchange.create_order(
                symbol=symbol,
                order_type="LIMIT",
                side="SELL",
                amount=pos.amount,
                price=new_sl,
            )
            if new_sl_order:
                pos.sl_order_id = new_sl_order.get("id")
                print(f"Moved SL to entry (breakeven): {new_sl}")

        # If fully closed, cleanup
        if pos.amount <= Decimal("0.00000001"):
            if pos.sl_order_id:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            self.positions.pop(symbol, None)
            print(f"Position fully closed for {symbol}")

        return order
