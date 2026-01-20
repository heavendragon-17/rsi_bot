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
import time
import ccxt
from datetime import datetime, timedelta

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

    # Order tracking
    sl_order_id: Optional[str] = None

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False


@dataclass
class PendingEntry:
    symbol: str
    order_id: str
    entry_ts: Any  # Candle timestamp of the signal
    amount: Decimal
    signal: SignalEvent
    created_at: float
    last_check_at: float
    filled_amount: Decimal = Decimal("0")


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
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.33)))  # close 1/3
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))  # close 1/2 of remaining
        # TP3 closes 100% remaining

        # Pending Limit Entries
        self.pending_entries: Dict[str, PendingEntry] = {}

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
        # Use BREAKEVEN as exit reason for moved SL (profit protection)
        exit_reason = "BREAKEVEN"

        # 1) Try generic update_stop_loss(symbol, new_price, new_amount, exit_reason)
        fn2 = getattr(self.exchange, "update_stop_loss", None)
        if callable(fn2):
            try:
                ok = bool(fn2(symbol, target_price, amount_to_use, exit_reason))
                if ok:
                    return True
            except Exception:
                pass

        # 2) Fallback: cancel existing SL order and re-create LIMIT at target_price
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass
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
                return self.execute_partial_close(signal.symbol, "TP1")
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2")
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3")

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

        if signal.symbol in self.pending_entries:
            return None

        price = signal.price
        if price <= Decimal("0"):
            return None

        # Position sizing: Use soft_sl_price for risk calculation (2% risk)
        # Soft SL = primary SL level for position sizing
        # sl_price (disaster SL) = only for hard limit order protection
        sizing_sl = signal.soft_sl_price if signal.soft_sl_price is not None else signal.sl_price
        amount = self._calculate_position_size(balance, price, sizing_sl)

        # Check Entry Mode
        entry_mode = self.config.get("entry_mode", "MARKET").upper()
        if "strategy" in self.config:
            entry_mode = self.config["strategy"].get("entry_mode", entry_mode).upper()

        if entry_mode == "LIMIT":
            try:
                order = self.exchange.create_order(
                    symbol=signal.symbol,
                    type="limit",
                    side="BUY",
                    amount=amount,
                    price=price,
                )
                if not order:
                    return None

                self.pending_entries[signal.symbol] = PendingEntry(
                    symbol=signal.symbol,
                    order_id=order["id"],
                    entry_ts=signal.timestamp,
                    amount=amount,
                    signal=signal,
                    created_at=time.time(),
                    last_check_at=time.time(),
                )
                logging.info(f"[{signal.symbol}] Placed LIMIT ENTRY BUY at {price}")
                return order
            except ccxt.InsufficientFunds as e:
                logging.warning(f"Insufficient funds for {signal.symbol}: {e}")
                return None
            except ccxt.BaseError as e:
                logging.error(f"Failed to execute limit buy for {signal.symbol}: {e}")
                return None

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
        self._register_active_position(signal, amount, price)
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

    def execute_partial_close(self, symbol: str, tp_level: str):
        """
        Execute partial close for TP levels:
        - TP1: close tp1_close_pct of current amount, then move SL to entry on remaining
        - TP2: close tp2_close_pct of remaining
        - TP3: close all remaining
        """
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

        pos.amount -= close_amount

        # TP1: move SL to entry for remaining
        if tp_level == "TP1" and pos.amount > Decimal("0"):
            self._move_sl_to_entry(symbol)

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

    def has_pending_entry(self, symbol: str) -> bool:
        return symbol in self.pending_entries

    def _parse_timeframe_to_seconds(self, tf: str) -> int:
        if not tf: return 900
        if tf.endswith('m'): return int(tf[:-1]) * 60
        if tf.endswith('h'): return int(tf[:-1]) * 3600
        if tf.endswith('d'): return int(tf[:-1]) * 86400
        if tf.endswith('w'): return int(tf[:-1]) * 604800
        return 900 # default 15m

    def _register_active_position(self, signal: SignalEvent, amount: Decimal, entry_price: Decimal):
        """Register active position and place SL orders."""
        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            amount=amount,
            entry_price=entry_price,
            side="BUY",
            timestamp=signal.timestamp,
            tp1_price=signal.tp1_price,
            tp2_price=signal.tp2_price,
            tp3_price=signal.tp3_price,
            sl_price=signal.sl_price,
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

    def _update_or_create_position(self, symbol: str, filled: Decimal, signal: SignalEvent, avg_price: Decimal):
        """Update existing position or create new one."""
        if symbol in self.positions:
             pos = self.positions[symbol]
             if filled > pos.amount:
                 pos.amount = filled
                 if pos.sl_order_id and hasattr(self.exchange, "update_stop_loss"):
                     try:
                         self.exchange.update_stop_loss(symbol, pos.sl_price, amount=filled)
                     except Exception as e:
                         logging.warning(f"Failed to update SL amount: {e}")
        else:
             self._register_active_position(signal, filled, avg_price)

    def check_pending_entry(self, symbol: str, current_candle_timestamp: Any) -> None:
        """
        Check status of pending entry order.
        - Timeout logic (5 candles)
        - Partial fill logic
        """
        if symbol not in self.pending_entries:
            return

        entry = self.pending_entries[symbol]

        # Calculate elapsed candles
        tf = self.config.get("timeframe", "15m")
        tf_seconds = self._parse_timeframe_to_seconds(tf)

        # Determine elapsed time
        elapsed_seconds = 0
        try:
            # Handle pandas Timestamp vs int/float
            ts_curr = current_candle_timestamp
            ts_entry = entry.entry_ts

            if hasattr(ts_curr, "timestamp"): ts_curr = ts_curr.timestamp()
            if hasattr(ts_entry, "timestamp"): ts_entry = ts_entry.timestamp()

            # If int (ms), convert to seconds
            if isinstance(ts_curr, (int, float)) and ts_curr > 3000000000: # heuristic for ms
                 ts_curr /= 1000
            if isinstance(ts_entry, (int, float)) and ts_entry > 3000000000:
                 ts_entry /= 1000

            elapsed_seconds = float(ts_curr) - float(ts_entry)
        except Exception as e:
            logging.error(f"Error calculating elapsed time for {symbol}: {e}")
            elapsed_seconds = 0

        candles_elapsed = elapsed_seconds / tf_seconds if tf_seconds > 0 else 0

        # Check Exchange Status
        is_timeout = candles_elapsed >= 5
        is_mock = "MockExchange" in self.exchange.__class__.__name__

        if is_mock or is_timeout or (time.time() - entry.last_check_at > 60):
            entry.last_check_at = time.time()

            # Fetch order
            order_info = None
            try:
                if hasattr(self.exchange, "fetch_order"):
                    order_info = self.exchange.fetch_order(entry.order_id, symbol)
                else:
                    logging.warning("Exchange does not support fetch_order")
            except Exception as e:
                logging.warning(f"Failed to fetch order {entry.order_id}: {e}")

            if not order_info:
                if is_timeout:
                     logging.info(f"[{symbol}] Pending entry timed out and not found. Removing.")
                     self.pending_entries.pop(symbol)
                return

            status = order_info.get("status", "open")
            filled = to_decimal(order_info.get("filled", 0))
            remaining = to_decimal(order_info.get("remaining", 0))

            # Update filled amount
            entry.filled_amount = filled

            # Case: Fully Filled
            if status == "closed" and remaining == 0 and filled > 0:
                logging.info(f"[{symbol}] Entry filled completely ({filled}). Activating position.")
                self._update_or_create_position(symbol, filled, entry.signal, to_decimal(order_info.get("average", entry.signal.price)))
                self.pending_entries.pop(symbol)
                return

            # Case: Canceled (externally?)
            if status == "canceled":
                if filled > 0:
                    logging.info(f"[{symbol}] Entry canceled with partial fill ({filled}). Activating position.")
                    self._update_or_create_position(symbol, filled, entry.signal, to_decimal(order_info.get("average", entry.signal.price)))
                self.pending_entries.pop(symbol)
                return

            # Case: Timeout
            if is_timeout:
                # Case A: 0% Filled
                if filled <= 0:
                    logging.info(f"[{symbol}] Entry timed out (0 filled). Canceling.")
                    try:
                        self.exchange.cancel_order(entry.order_id, symbol)
                    except Exception as e:
                        logging.warning(f"Failed to cancel timed out order: {e}")
                    self.pending_entries.pop(symbol)
                    return

                # Case B: Partial Fill
                else:
                    logging.info(f"[{symbol}] Entry timed out (partial {filled}). Canceling remainder.")
                    try:
                        self.exchange.cancel_order(entry.order_id, symbol)
                    except Exception as e:
                        logging.warning(f"Failed to cancel remainder: {e}")

                    self._update_or_create_position(symbol, filled, entry.signal, to_decimal(order_info.get("average", entry.signal.price)))
                    self.pending_entries.pop(symbol)
                    return

            # Dynamic SL/TP Sync (Partial Fill Update)
            if filled > 0:
                self._update_or_create_position(symbol, filled, entry.signal, to_decimal(order_info.get("average", entry.signal.price)))
