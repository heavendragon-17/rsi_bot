# app/core/portfolio_manager.py
"""
Layer 3: Execution - Portfolio Manager
=======================================
Handles position management, order execution, TP/SL placement.

TP handling:
- Strategy emits SELL with reason starting: "TP1", "TP2", "TP3"
- PortfolioManager will partial-close accordingly.

Extra:
- Strategy can emit SELL with reason like:
  "MOVE_SL_TO_ENTRY", "SL_TO_ENTRY", "BREAKEVEN", "MOVE_SL"
  -> PortfolioManager will ONLY move SL to entry (no market sell).
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from decimal import Decimal
import logging
import ccxt
from datetime import datetime

from app.core.interfaces import IExchange
from app.core.events import SignalEvent
from .utils import to_decimal


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
    lock_profit_price: Optional[Decimal] = None
    tp_allocations: Optional[dict] = None

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
        
        # Risk-based position sizing
        self.risk_per_trade_pct = Decimal(str(risk_cfg.get("risk_per_trade_pct", 0.02)))  # Risk 2% per trade
        self.use_risk_based_sizing = bool(risk_cfg.get("use_risk_based_sizing", True))
        self.min_sl_distance_pct = Decimal(str(risk_cfg.get("min_sl_distance_pct", 0.01)))  # Min 1% SL distance
        
        # Futures leverage
        self.leverage = Decimal(str(risk_cfg.get("leverage", 1)))  # Default 1x (spot-like)
        self.use_initial_capital_for_risk = bool(risk_cfg.get("use_initial_capital_for_risk", True))
        
        # Store initial capital for risk calculation
        backtest_cfg = config.get("backtest", {})
        self.initial_capital = Decimal(str(backtest_cfg.get("initial_balance", 10000)))

        # TP percentages (how much to close at each level)
        # TP percentages (how much to close at each level)
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.50)))  # close 50%
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))  # close 50% of remaining
        # TP3 closes 100% remaining

    # -------------------------
    # Position Sizing
    # -------------------------
    def _calculate_position_size(
        self, balance: Decimal, entry_price: Decimal, sl_price: Optional[Decimal]
    ) -> Decimal:
        """
        Calculate position size for futures trading with leverage.
        
        Risk-Based Formula (Futures):
            risk_capital = initial_capital (or current balance)
            risk_amount = risk_capital * risk_per_trade_pct
            sl_distance_pct = |entry_price - sl_price| / entry_price
            position_notional = risk_amount / sl_distance_pct
            position_size = position_notional / entry_price
            margin_required = position_notional / leverage
        
        The position size represents the notional value of the trade.
        With leverage, you only need (notional / leverage) as margin.
        
        Example (10x leverage, 2% risk, $10k capital, 5% SL):
            risk_amount = $10,000 * 0.02 = $200
            position_notional = $200 / 0.05 = $4,000
            margin_required = $4,000 / 10 = $400
            position_size = $4,000 / entry_price
        """
        # Determine risk capital (initial capital or current balance)
        if self.use_initial_capital_for_risk:
            risk_capital = self.initial_capital
        else:
            risk_capital = balance
        
        # Max margin we can use (based on current balance and leverage)
        max_margin = balance * self.max_position_size_pct
        max_notional = max_margin * self.leverage
        max_amount = max_notional / entry_price
        
        # Use risk-based sizing if enabled and SL is provided
        if self.use_risk_based_sizing and sl_price is not None and sl_price > Decimal("0"):
            sl_distance = abs(entry_price - sl_price)
            sl_distance_pct = sl_distance / entry_price
            
            # SAFETY: If SL distance is too small, use fallback sizing
            if sl_distance_pct < self.min_sl_distance_pct:
                print(f"  [WARNING] SL distance too small ({sl_distance_pct*100:.2f}% < {self.min_sl_distance_pct*100:.0f}%). Using max position size cap.")
                return max_amount
            
            if sl_distance_pct > Decimal("0"):
                # Risk amount in quote currency (based on initial capital)
                risk_amount = risk_capital * self.risk_per_trade_pct
                
                # Position notional to risk exactly risk_amount if SL hits
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                
                # Margin required for this position
                margin_required = position_notional / self.leverage
                
                # Cap at max position size (based on available margin * leverage)
                final_size = min(position_size, max_amount)
                was_capped = position_size > max_amount
                
                # DEBUG: Log position sizing details
                print(f"  [SIZING] Entry=${entry_price:.4f}, SL=${sl_price:.4f}, Dist={sl_distance_pct*100:.2f}%, Risk=${risk_amount:.2f}, Notional=${position_notional:.2f}, Size={final_size:.6f}")
                
                # Calculate actual risk if capped
                if was_capped:
                    actual_notional = final_size * entry_price
                    actual_risk = actual_notional * sl_distance_pct
                    print(f"  [CAPPED] Position capped! Target risk: ${risk_amount:.2f}, Actual risk: ${actual_risk:.2f} ({(actual_risk/risk_capital)*100:.2f}%)")
                
                return final_size
        
        # Fallback: use max_position_size_pct with leverage
        return max_amount

    # -------------------------
    # Helpers
    # -------------------------
    def sync_balance(self) -> Decimal:
        bal = self.exchange.fetch_balance()
        # CCXT returns total balance in 'total' dict
        return to_decimal(bal.get("total", {}).get("USDT", 0))

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
                self.positions.pop(sym, None)

    def _move_sl_to_entry(self, symbol: str, new_price: Decimal = None, new_amount: Decimal = None) -> bool:
        """
        Move SL to a new price for the remaining position.
        If new_price is None, uses entry price (breakeven).
        Prefers exchange-native update if available, otherwise cancel+replace LIMIT.
        
        Args:
            symbol: Trading symbol
            new_price: Optional new SL price (uses entry_price if not provided)
            new_amount: Optional new amount for the SL order (uses pos.amount if not provided)
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        if pos.amount <= Decimal("0"):
            return False

        # Default to entry price if no new_price specified
        target_price = new_price if new_price is not None else pos.entry_price
        # Default to current position amount if no new_amount specified
        amount_to_use = new_amount if new_amount is not None else pos.amount
        
        # Dynamic exit reason based on price comparison with entry
        if target_price > pos.entry_price:
            exit_reason = "LOCK_PROFIT"  # Locking in profit (e.g., 0.2R)
        elif target_price == pos.entry_price:
            exit_reason = "BREAKEVEN"  # At entry, no profit/loss
        else:
            exit_reason = "TRAILING_SL"  # Tightening SL (still at loss if hit)
        
        fn2 = getattr(self.exchange, "update_stop_loss", None)
        if callable(fn2):
            try:
                ok = bool(fn2(symbol, target_price, amount_to_use, exit_reason))
                if ok:
                    return True
            except Exception as e:
                print(f"[_move_sl_to_entry] update_stop_loss failed for {symbol}: {e}")
                pass

        # 2) Fallback: cancel existing SL order and re-create LIMIT at target_price
        logging.info(f"[_move_sl_to_entry] Fallback to Cancel+Replance for {symbol}")
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception as e:
                logging.warning(f"[_move_sl_to_entry] Failed to cancel SL {pos.sl_order_id} for {symbol}: {e}")
            pos.sl_order_id = None

        try:
            new_sl_order = self.exchange.create_order(
                symbol=symbol,
                type="limit",
                side="SELL",
                amount=amount_to_use,
                price=target_price,
                params={"exit_reason": exit_reason},
            )
            if new_sl_order:
                pos.sl_order_id = new_sl_order.get("id")
                logging.info(f"[{symbol}] Moved SL to {target_price}")
                return True
        except ccxt.BaseError as e:
            logging.error(f"Failed to move SL for {symbol}: {e}")
            return False

        return False

    # -------------------------
    # Main entry
    # -------------------------
    def on_signal(self, signal: SignalEvent):
        """
        Process a trading signal.
        - BUY: open position + place SL limit
        - SELL:
            + TP1/TP2/TP3 partial/full close
            + MOVE_SL_TO_ENTRY: only move SL to entry, do not sell
            + Otherwise: full close
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

            # --- special SELL: move SL only ---
            # any of these reason keywords will just move SL (not close position)
            if (
                "MOVE_SL_TO_ENTRY" in reason
                or "SL_TO_ENTRY" in reason
                or "BREAKEVEN" in reason
                or reason.startswith("MOVE_SL")
            ):
                # If signal.price is provided, use it as new SL level
                # Otherwise, move to entry (breakeven)
                new_sl_price = signal.price if signal.price else None
                self._move_sl_to_entry(signal.symbol, new_sl_price)
                return None

            # --- TP partial closes ---
            if reason.startswith("TP1"):
                return self.execute_partial_close(signal.symbol, "TP1", new_sl_price=signal.sl_price)
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2", new_sl_price=signal.sl_price)
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3", new_sl_price=signal.sl_price)

            # Any other SELL -> close full (pass exit_reason)
            exit_reason = signal.reason or "MANUAL"
            return self._handle_full_sell(signal.symbol, price=signal.price, exit_reason=exit_reason)

        return None

    # -------------------------
    # BUY logic
    # -------------------------
    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal):
        if signal.symbol in self.positions:
            return None

        price = signal.price
        if price <= Decimal("0"):
            return None

        # Position sizing: Use soft_sl_price for risk calculation (2% risk)
        # Soft SL = primary SL level for position sizing
        # sl_price (disaster SL) = only for hard limit order protection
        sizing_sl = signal.soft_sl_price if signal.soft_sl_price is not None else signal.sl_price
        amount = self._calculate_position_size(balance, price, sizing_sl)

        # Execute market BUY - pass signal.price for consistent fill price in backtest
        try:
            order = self.exchange.create_order(
                symbol=signal.symbol,
                type="market",
                side="BUY",
                amount=amount,
                price=price,  # Use signal price for backtest consistency
            )
            if not order:
                return None
        except ccxt.InsufficientFunds as e:
            logging.warning(f"Insufficient funds for {signal.symbol}: {e}")
            return None
        except ccxt.BaseError as e:
            logging.error(f"Failed to execute buy for {signal.symbol}: {e}")
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
            sl_price=signal.sl_price,  # Store disaster SL for reference
            lock_profit_price=signal.lock_profit_price, # Store lock profit price
            tp_allocations=signal.tp_allocations,
        )

        # Place hard SL limit order (disaster SL) if provided
        if signal.sl_price is not None:
            try:
                sl_order = self.exchange.create_order(
                    symbol=signal.symbol,
                    type="limit",
                    side="SELL",
                    amount=amount,
                    price=signal.sl_price,  # Disaster SL on exchange
                    params={"exit_reason": "DISASTER_SL"},
                )
                if sl_order:
                    self.positions[signal.symbol].sl_order_id = sl_order.get("id")
            except ccxt.BaseError as e:
                logging.error(f"Failed to place SL order for {signal.symbol}: {e}")

        return order

    # -------------------------
    # SELL logic
    # -------------------------
    def _handle_full_sell(self, symbol: str, price: Decimal = None, exit_reason: str = "MANUAL"):
        """
        Close entire remaining position at market and cleanup.
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]

        # Cancel SL order if any
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except ccxt.OrderNotFound:
                pass  # Already gone
            except ccxt.BaseError as e:
                logging.warning(f"Failed to cancel SL {pos.sl_order_id}: {e}")

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side="SELL",
                amount=pos.amount,
                price=price,
                params={"exit_reason": exit_reason},
            )

            if order:
                self.positions.pop(symbol, None)
                return order
        except ccxt.BaseError as e:
            logging.error(f"Failed to execute full sell for {symbol}: {e}")
            return None

        return None

    def execute_partial_close(self, symbol: str, tp_level: str, new_sl_price: Optional[Decimal] = None):
        """
        Execute partial close for TP levels:
        - TP1: close tp1_close_pct of current amount, then move SL to entry (or new_sl_price) for remaining
        - TP2: close tp2_close_pct of remaining
        - TP3: close all remaining
        """
        self.sync_from_exchange()

        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        tp_level = tp_level.upper().strip()

        if tp_level == "TP1" and pos.tp1_hit:
            # If TP1 already hit, we might be receiving a retry signal to move SL
            if new_sl_price and pos.amount > Decimal("0"):
                try:
                    self.exchange.update_stop_loss(symbol, new_sl_price, pos.amount, exit_reason="LOCK_PROFIT")
                except Exception as e:
                    logging.warning(f"Failed to retry SL update for {symbol}: {e}")
            return None
        if tp_level == "TP2" and pos.tp2_hit:
            return None
        if tp_level == "TP3" and pos.tp3_hit:
            return None

        close_amount = Decimal("0")

        # Get close % from position allocation or global config
        allocs = pos.tp_allocations or {}
        
        if tp_level == "TP1":
            pct = Decimal(str(allocs.get("TP1", self.tp1_close_pct)))
            close_amount = pos.amount * pct
            pos.tp1_hit = True
        elif tp_level == "TP2":
            pct = Decimal(str(allocs.get("TP2", self.tp2_close_pct)))
            close_amount = pos.amount * pct
            pos.tp2_hit = True
        elif tp_level == "TP3":
            # TP3 is usually 100% remaining, but let's allow override if needed
            # Default behavior for TP3 is closing everything
            pct = Decimal(str(allocs.get("TP3", "1.0")))
            close_amount = pos.amount * pct
            pos.tp3_hit = True

        if close_amount <= Decimal("0"):
            return None

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side="SELL",
                amount=close_amount,
                params={"exit_reason": tp_level},
            )
            if not order:
                return None
        except ccxt.BaseError as e:
            logging.error(f"Failed to execute partial close {tp_level} for {symbol}: {e}")
            return None

        old_amount = pos.amount
        pos.amount -= close_amount
        # Update SL amount for remaining position (resize SL order)
        # If new_sl_price is provided, it moves there. If None, it moves to Entry (or stays at Entry).
        if pos.amount > Decimal("0"):
            self._move_sl_to_entry(symbol, new_price=new_sl_price)

        # If fully closed, cleanup
        if pos.amount <= Decimal("0.00000001"):
            if pos.sl_order_id:
                try:
                    self.exchange.cancel_order(pos.sl_order_id, symbol)
                except ccxt.OrderNotFound:
                    pass
                except ccxt.BaseError as e:
                    logging.warning(f"Failed to cancel SL {pos.sl_order_id} during cleanup: {e}")
            self.positions.pop(symbol, None)

        return order
