# app/core/portfolio.py
"""
Layer 3: Execution - Portfolio Manager
=======================================
Handles position management, order execution, TP/SL placement.
"""

from __future__ import annotations

from typing import Dict, Optional
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime

from app.core.interfaces import IFuturesExchange, IPortfolio
from app.core.events import SignalEvent, Candle
from app.core.risk_types import RiskParams, ExitTrigger


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

    # Execution Triggers
    sl_trigger: ExitTrigger = ExitTrigger.LIMIT_ORDER
    tp_trigger: ExitTrigger = ExitTrigger.WICK


class PortfolioManager(IPortfolio):
    """
    Manages positions, executes orders, and handles TP/SL.
    """

    def __init__(self, exchange: IFuturesExchange, config: dict):
        self.exchange = exchange
        self.config = config
        self.positions: Dict[str, Position] = {}

        # Risk settings
        risk_cfg = config.get("risk", {})
        self.max_position_size_pct = Decimal(str(risk_cfg.get("max_position_size_pct", 0.99)))
        
        # Risk-based position sizing
        self.risk_per_trade_pct = Decimal(str(risk_cfg.get("risk_per_trade_pct", 0.02)))
        self.use_risk_based_sizing = bool(risk_cfg.get("use_risk_based_sizing", True))
        self.min_sl_distance_pct = Decimal(str(risk_cfg.get("min_sl_distance_pct", 0.01)))
        
        # Futures leverage
        self.leverage = Decimal(str(risk_cfg.get("leverage", 1)))
        self.use_initial_capital_for_risk = bool(risk_cfg.get("use_initial_capital_for_risk", True))
        
        backtest_cfg = config.get("backtest", {})
        self.initial_capital = Decimal(str(backtest_cfg.get("initial_balance", 10000)))

        # TP percentages
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.33)))
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))

    # -------------------------
    # Position Sizing
    # -------------------------
    def _calculate_position_size(
        self, balance: Decimal, entry_price: Decimal, sl_price: Optional[Decimal]
    ) -> Decimal:
        if self.use_initial_capital_for_risk:
            risk_capital = self.initial_capital
        else:
            risk_capital = balance
        
        max_margin = balance * self.max_position_size_pct
        max_notional = max_margin * self.leverage
        max_amount = max_notional / entry_price
        
        if self.use_risk_based_sizing and sl_price is not None and sl_price > Decimal("0"):
            sl_distance = abs(entry_price - sl_price)
            sl_distance_pct = sl_distance / entry_price
            
            if sl_distance_pct < self.min_sl_distance_pct:
                print(f"  [WARNING] SL distance too small ({sl_distance_pct*100:.2f}% < {self.min_sl_distance_pct*100:.0f}%). Using max position size cap.")
                return max_amount
            
            if sl_distance_pct > Decimal("0"):
                risk_amount = risk_capital * self.risk_per_trade_pct
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                
                final_size = min(position_size, max_amount)
                was_capped = position_size > max_amount
                
                if was_capped:
                    actual_notional = final_size * entry_price
                    actual_risk = actual_notional * sl_distance_pct
                    print(f"  [CAPPED] Position capped! Target risk: ${risk_amount:.2f}, Actual risk: ${actual_risk:.2f} ({(actual_risk/risk_capital)*100:.2f}%)")
                
                return final_size
        
        return max_amount

    # -------------------------
    # Helpers
    # -------------------------
    def sync_balance(self) -> Decimal:
        return self.exchange.get_balance()

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def close_position(self, symbol: str, percentage: Decimal) -> None:
        """Close percentage of position (0.0 - 1.0)."""
        if symbol not in self.positions:
            return
        if percentage >= Decimal("1.0"):
            self._handle_full_sell(symbol)
        else:
            # Implement partial close if needed, reusing execute_partial_close logic manually
            pos = self.positions[symbol]
            amount = pos.amount * percentage
            if amount > 0:
                self.exchange.create_order(symbol, "MARKET", "SELL", amount, exit_reason="MANUAL_PARTIAL")
                pos.amount -= amount
                if pos.amount <= Decimal("0"):
                    self.positions.pop(symbol, None)

    def sync_from_exchange(self) -> None:
        if not hasattr(self.exchange, "positions"):
            return
        # Sync simple position existence
        # Note: In real futures exchange, get_position returns details.
        # MockExchange.positions is just symbol->amount.
        # We need to trust internal state mostly but verify if closed externally.
        for sym in list(self.positions.keys()):
            pos_data = self.exchange.get_position(sym)
            if not pos_data or pos_data['amount'] == 0:
                self.positions.pop(sym, None)

    def _move_sl_to_entry(self, symbol: str) -> bool:
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        if pos.amount <= Decimal("0"):
            return False

        entry = pos.entry_price

        # Prefer place_stop_loss or update mechanism
        # For parity with old code that tried `update_stop_loss_to_entry` on MockExchange:
        fn = getattr(self.exchange, "update_stop_loss_to_entry", None)
        if callable(fn):
            ok = bool(fn(symbol))
            if ok:
                return True

        # Fallback: cancel and replace
        if pos.sl_order_id:
            self.exchange.cancel_order(pos.sl_order_id, symbol)
            pos.sl_order_id = None

        sl_order = self.exchange.place_stop_loss(symbol, pos.amount, entry)
        if sl_order:
            pos.sl_order_id = sl_order.get("id")
            return True

        return False

    # -------------------------
    # Logic
    # -------------------------
    def on_candle(self, candle: Candle) -> None:
        """
        Check for CANDLE_CLOSE exits.
        """
        if candle.symbol not in self.positions:
            return

        pos = self.positions[candle.symbol]

        # SL Logic for CANDLE_CLOSE
        if pos.sl_trigger == ExitTrigger.CANDLE_CLOSE and pos.sl_price:
            # Assuming LONG positions only for now as per strategy
            if pos.side == "BUY" and candle.close <= pos.sl_price:
                self._handle_full_sell(candle.symbol, price=candle.close)
                # print(f"CANDLE_CLOSE SL triggered for {candle.symbol} at {candle.close}")

    def on_signal(self, signal: SignalEvent, risk_params: Optional[RiskParams] = None) -> None:
        self.sync_from_exchange()

        if signal.signal_type == "BUY":
            balance = self.sync_balance()
            return self._handle_buy_signal(signal, balance, risk_params)

        if signal.signal_type == "SELL":
            if signal.symbol not in self.positions:
                return None

            reason = (signal.reason or "").strip().upper()

            if (
                "MOVE_SL_TO_ENTRY" in reason
                or "SL_TO_ENTRY" in reason
                or "BREAKEVEN" in reason
                or reason.startswith("MOVE_SL")
            ):
                self._move_sl_to_entry(signal.symbol)
                return None

            if reason.startswith("TP1"):
                return self.execute_partial_close(signal.symbol, "TP1")
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2")
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3")

            return self._handle_full_sell(signal.symbol, price=signal.price)

        return None

    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal, risk_params: Optional[RiskParams]):
        if signal.symbol in self.positions:
            return None

        price = signal.price
        if price <= Decimal("0"):
            return None

        amount = self._calculate_position_size(balance, price, signal.sl_price)

        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type="MARKET",
            side="BUY",
            amount=amount,
        )
        if not order:
            return None

        # Determine triggers
        sl_trigger = risk_params.sl_trigger if risk_params else ExitTrigger.LIMIT_ORDER
        tp_trigger = risk_params.tp_trigger if risk_params else ExitTrigger.WICK

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
            sl_trigger=sl_trigger,
            tp_trigger=tp_trigger,
        )

        # Handle SL
        if signal.sl_price is not None:
            if sl_trigger == ExitTrigger.LIMIT_ORDER:
                # Place standard STOP_LOSS order
                sl_order = self.exchange.place_stop_loss(signal.symbol, amount, signal.sl_price)
                if sl_order:
                    self.positions[signal.symbol].sl_order_id = sl_order.get("id")

            elif sl_trigger == ExitTrigger.CANDLE_CLOSE:
                # Place Disaster SL if configured
                if risk_params and risk_params.disaster_sl_price:
                    sl_order = self.exchange.place_stop_loss(signal.symbol, amount, risk_params.disaster_sl_price)
                    # We don't track this as the primary sl_order_id because we don't want to move it to entry usually?
                    # Or maybe we do? Strategy says "Disaster SL (3x distance)".
                    # For now, we fire and forget or track it?
                    # The portfolio assumes `sl_order_id` is THE stop loss.
                    if sl_order:
                        self.positions[signal.symbol].sl_order_id = sl_order.get("id")

        return order

    def _handle_full_sell(self, symbol: str, price: Decimal = None):
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]

        if pos.sl_order_id:
            self.exchange.cancel_order(pos.sl_order_id, symbol)

        order = self.exchange.create_order(
            symbol=symbol,
            order_type="MARKET",
            side="SELL",
            amount=pos.amount,
            price=price,
            exit_reason="MANUAL",
        )

        if order:
            self.positions.pop(symbol, None)
            return order

        return None

    def execute_partial_close(self, symbol: str, tp_level: str):
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

        order = self.exchange.create_order(
            symbol=symbol,
            order_type="MARKET",
            side="SELL",
            amount=close_amount,
            exit_reason=tp_level,
        )
        if not order:
            return None

        pos.amount -= close_amount

        # TP1: move SL to entry for remaining
        if tp_level == "TP1" and pos.amount > Decimal("0"):
            self._move_sl_to_entry(symbol)

        if pos.amount <= Decimal("0.00000001"):
            if pos.sl_order_id:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            self.positions.pop(symbol, None)

        return order
