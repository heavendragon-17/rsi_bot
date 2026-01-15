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
  
New in v2:
- on_candle() method checks SL/TP on candle close (not wicks)
- Disaster SL placed on exchange at 3x risk level
"""

from __future__ import annotations

from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime

from app.core.interfaces import IExchange
from app.core.events import SignalEvent, Candle
from app.core.risk_types import RiskParams, ExitTrigger, TPLevel


@dataclass
class Position:
    """
    Represents an open position with TP/SL tracking.
    """
    symbol: str
    amount: Decimal
    entry_price: Decimal
    side: str  # 'LONG' or 'SHORT'
    timestamp: datetime

    # TP/SL prices (from SignalEvent)
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None

    # Order tracking
    sl_order_id: Optional[str] = None
    disaster_sl_order_id: Optional[str] = None  # 3x backup SL on exchange

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    
    # Risk params from strategy
    risk_params: Optional[RiskParams] = None


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
                self.positions.pop(sym, None)

    # -------------------------
    # Candle-Close SL/TP Checking
    # -------------------------
    def on_candle(self, candle: Candle) -> List[dict]:
        """
        Check open positions for SL/TP on candle close.
        
        This method is called on every candle close by the engine.
        It checks positions based on the strategy's ExitTrigger setting.
        
        Returns: List of execution events (for logging).
        """
        executions = []
        symbol = candle.symbol
        
        if symbol not in self.positions:
            return executions
        
        pos = self.positions[symbol]
        close_price = candle.close
        
        # Check SL (if candle-close trigger)
        if self._should_stop_loss(pos, close_price):
            exec_event = self._execute_sl_on_candle(pos, candle)
            if exec_event:
                executions.append(exec_event)
            return executions  # Position closed, skip TP check
        
        # Check TPs (if candle-close trigger)
        tp_execs = self._check_tps_on_candle(pos, candle)
        executions.extend(tp_execs)
        
        return executions
    
    def _should_stop_loss(self, pos: Position, close_price: Decimal) -> bool:
        """Check if SL should trigger based on candle close."""
        if pos.sl_price is None:
            return False
        
        # Check if risk_params uses candle_close trigger
        if pos.risk_params and pos.risk_params.sl_trigger != ExitTrigger.CANDLE_CLOSE:
            return False  # Not using candle-close SL
        
        # Side-aware SL check
        if pos.side == 'LONG' or pos.side == 'BUY':
            return close_price <= pos.sl_price
        else:  # SHORT
            return close_price >= pos.sl_price
    
    def _execute_sl_on_candle(self, pos: Position, candle: Candle) -> Optional[dict]:
        """Execute SL exit and cleanup."""
        symbol = pos.symbol
        
        # Cancel disaster SL on exchange (we're exiting via code)
        if pos.disaster_sl_order_id:
            try:
                self.exchange.cancel_order(pos.disaster_sl_order_id, symbol)
            except Exception:
                pass
        
        # Cancel any pending SL order
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass
        
        # Execute market close
        close_side = 'SELL' if pos.side in ('LONG', 'BUY') else 'BUY'
        order = self.exchange.create_order(
            symbol=symbol,
            order_type='MARKET',
            side=close_side,
            amount=pos.amount,
            price=candle.close,
            exit_reason='SL_CANDLE_CLOSE',
        )
        
        if order:
            self.positions.pop(symbol, None)
            return {
                'type': 'SL',
                'symbol': symbol,
                'price': float(candle.close),
                'amount': float(pos.amount),
                'reason': 'SL_CANDLE_CLOSE',
            }
        return None
    
    def _check_tps_on_candle(self, pos: Position, candle: Candle) -> List[dict]:
        """Check and execute TP levels based on candle close."""
        executions = []
        
        if not pos.risk_params:
            return executions
        
        if pos.risk_params.tp_trigger != ExitTrigger.CANDLE_CLOSE:
            return executions
        
        close_price = candle.close
        symbol = pos.symbol
        
        for tp in pos.risk_params.tp_levels:
            if tp.executed:
                continue
            
            # Calculate TP price from percentage
            tp_price = pos.entry_price * (Decimal('1') + tp.price_pct)
            
            # Side-aware TP check
            is_long = pos.side in ('LONG', 'BUY')
            tp_hit = (close_price >= tp_price) if is_long else (close_price <= tp_price)
            
            if tp_hit:
                close_amount = pos.amount * tp.size_pct
                close_side = 'SELL' if is_long else 'BUY'
                
                order = self.exchange.create_order(
                    symbol=symbol,
                    order_type='MARKET',
                    side=close_side,
                    amount=close_amount,
                    price=close_price,
                    exit_reason=f'TP_CANDLE_CLOSE',
                )
                
                if order:
                    tp.executed = True
                    pos.amount -= close_amount
                    
                    executions.append({
                        'type': 'TP',
                        'symbol': symbol,
                        'price': float(close_price),
                        'amount': float(close_amount),
                        'reason': 'TP_CANDLE_CLOSE',
                    })
                    
                    # If position fully closed, cleanup
                    if pos.amount <= Decimal('0.00000001'):
                        if pos.disaster_sl_order_id:
                            try:
                                self.exchange.cancel_order(pos.disaster_sl_order_id, symbol)
                            except Exception:
                                pass
                        if pos.sl_order_id:
                            try:
                                self.exchange.cancel_order(pos.sl_order_id, symbol)
                            except Exception:
                                pass
                        self.positions.pop(symbol, None)
                        break
        
        return executions

    def _move_sl_to_entry(self, symbol: str) -> bool:
        """
        Move SL to entry price for the remaining position.
        Prefers exchange-native update if available, otherwise cancel+replace LIMIT.
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        if pos.amount <= Decimal("0"):
            return False

        entry = pos.entry_price

        # 1) Prefer exchange function if exists (MockExchange patch)
        fn = getattr(self.exchange, "update_stop_loss_to_entry", None)
        if callable(fn):
            ok = bool(fn(symbol))
            if ok:
                return True

        # 2) Otherwise try generic update_stop_loss(symbol, new_price)
        fn2 = getattr(self.exchange, "update_stop_loss", None)
        if callable(fn2):
            try:
                ok = bool(fn2(symbol, entry))
                if ok:
                    return True
            except Exception:
                pass

        # 3) Fallback: cancel existing SL order and re-create LIMIT at entry
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass
            pos.sl_order_id = None

        new_sl_order = self.exchange.create_order(
            symbol=symbol,
            order_type="LIMIT",
            side="SELL",
            amount=pos.amount,
            price=entry,
            exit_reason="MOVE_SL_TO_ENTRY",
        )
        if new_sl_order:
            pos.sl_order_id = new_sl_order.get("id")
            return True

        return False

    # -------------------------
    # Main entry
    # -------------------------
    def on_signal(self, signal: SignalEvent, risk_params: Optional[RiskParams] = None):
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
            return self._handle_buy_signal(signal, balance, risk_params)

        if signal.signal_type == "SELL":
            # If SL already closed it, just ignore quietly
            if signal.symbol not in self.positions:
                return None

            reason = (signal.reason or "").strip().upper()

            # --- special SELL: move SL only ---
            # any of these reason keywords will just move SL to entry
            if (
                "MOVE_SL_TO_ENTRY" in reason
                or "SL_TO_ENTRY" in reason
                or "BREAKEVEN" in reason
                or reason.startswith("MOVE_SL")
            ):
                self._move_sl_to_entry(signal.symbol)
                return None

            # --- TP partial closes ---
            if reason.startswith("TP1"):
                return self.execute_partial_close(signal.symbol, "TP1")
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2")
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3")

            # Any other SELL -> close full
            return self._handle_full_sell(signal.symbol, price=signal.price)

        return None

    # -------------------------
    # BUY logic
    # -------------------------
    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal, risk_params: Optional[RiskParams] = None):
        if signal.symbol in self.positions:
            return None

        price = signal.price
        if price <= Decimal("0"):
            return None

        # Position sizing
        amount = self._calculate_position_size(balance, price, signal.sl_price)

        # Execute market BUY
        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type="MARKET",
            side="BUY",
            amount=amount,
        )
        if not order:
            return None

        # Create position record with risk_params
        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            amount=amount,
            entry_price=price,
            side="LONG",  # Updated from "BUY" to "LONG"
            timestamp=signal.timestamp,
            tp1_price=signal.tp1_price,
            tp2_price=signal.tp2_price,
            tp3_price=signal.tp3_price,
            sl_price=signal.sl_price,
            risk_params=risk_params,  # Store strategy's risk params
        )

        # Place disaster SL on exchange (3x normal SL) if risk_params provided
        if risk_params and signal.sl_price is not None:
            disaster_sl_distance = abs(price - signal.sl_price) * Decimal(str(risk_params.disaster_sl_multiplier))
            disaster_sl_price = price - disaster_sl_distance if signal.sl_price < price else price + disaster_sl_distance
            
            if hasattr(self.exchange, 'place_stop_loss'):
                disaster_sl_id = self.exchange.place_stop_loss(
                    signal.symbol, amount, disaster_sl_price
                )
                if disaster_sl_id:
                    self.positions[signal.symbol].disaster_sl_order_id = disaster_sl_id
        
        # For backward compatibility: place regular SL if no risk_params (old flow)
        elif signal.sl_price is not None and risk_params is None:
            sl_order = self.exchange.create_order(
                symbol=signal.symbol,
                order_type="LIMIT",
                side="SELL",
                amount=amount,
                price=signal.sl_price,
                exit_reason="STOP_LOSS",
            )
            if sl_order:
                self.positions[signal.symbol].sl_order_id = sl_order.get("id")

        return order

    # -------------------------
    # SELL logic
    # -------------------------
    def _handle_full_sell(self, symbol: str, price: Decimal = None):
        """
        Close entire remaining position at market and cleanup.
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]

        # Cancel SL order if any
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

        # If fully closed, cleanup
        if pos.amount <= Decimal("0.00000001"):
            if pos.sl_order_id:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            self.positions.pop(symbol, None)

        return order
