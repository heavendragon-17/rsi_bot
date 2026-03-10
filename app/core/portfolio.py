# app/core/portfolio_manager.py
"""
Layer 3: Execution - Portfolio Manager
=======================================
Handles position management, order execution, TP/SL placement.

Execution flow (per SPEC):
- BUY signal → market entry + stop_market SL + limit TP1/TP2/TP3 (all on exchange)
- TP fills detected by polling (sync_tp_fills) after each candle close
- Soft SL → pre-execution guard + market close with reduceOnly
- All exit orders use reduceOnly=True to prevent accidental SHORT positions
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime

import structlog

from app.core.exceptions import ExchangeError, InsufficientFundsError

logger = structlog.get_logger()
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
    tp_order_ids: Dict[str, str] = field(default_factory=dict)  # {"TP1": order_id, ...}

    # TP hit flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False


class PortfolioManager:
    """
    Manages positions, executes orders, and handles TP/SL.

    Uses normalized order type vocabulary:
    - SL placed as stop_market (not limit) with reduceOnly=True
    - TP placed as limit with reduceOnly=True
    - All exit orders include reduceOnly=True
    """

    def __init__(self, exchange: IExchange, config: dict, notification_service=None):
        self.exchange = exchange
        self.config = config
        self.positions: Dict[str, Position] = {}
        self._notification_service = notification_service

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

        # Store initial capital for risk calculation
        backtest_cfg = config.get("backtest", {})
        self.initial_capital = Decimal(str(backtest_cfg.get("initial_balance", 10000)))

        # TP percentages (how much to close at each level)
        self.tp1_close_pct = Decimal(str(risk_cfg.get("tp1_close_pct", 0.50)))
        self.tp2_close_pct = Decimal(str(risk_cfg.get("tp2_close_pct", 0.50)))
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
        """
        # Determine risk capital (initial capital or current balance)
        if self.use_initial_capital_for_risk:
            risk_capital = self.initial_capital
            # When using initial capital for risk, cap against initial capital too.
            # Using current (degraded) balance as the cap would produce smaller positions
            # than the risk formula intends, causing inconsistent TP/SL PnL.
            cap_balance = self.initial_capital
        else:
            risk_capital = balance
            cap_balance = balance

        # Max margin we can use (cap_balance ensures consistency with risk_capital)
        max_margin = cap_balance * self.max_position_size_pct
        max_notional = max_margin * self.leverage
        max_amount = max_notional / entry_price

        # Use risk-based sizing if enabled and SL is provided
        if self.use_risk_based_sizing and sl_price is not None and sl_price > Decimal("0"):
            sl_distance = abs(entry_price - sl_price)
            sl_distance_pct = sl_distance / entry_price if entry_price > Decimal("0") else Decimal("0")

            # EDGE CASE: Zero SL distance (SL = Entry) - reject trade
            if sl_distance_pct <= Decimal("0"):
                logger.error(f"SL distance is zero (SL={sl_price}, Entry={entry_price}). Cannot calculate position size.")
                return Decimal("0")

            # SAFETY: If SL distance is too small, still use risk-based sizing
            if sl_distance_pct < self.min_sl_distance_pct:
                risk_amount = risk_capital * self.risk_per_trade_pct
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                capped_size = min(position_size, max_amount)
                logger.warning(
                    f"SL distance too small ({sl_distance_pct*100:.2f}% < {self.min_sl_distance_pct*100:.0f}%). "
                    f"Risk-based size={position_size:.4f}, capped to {capped_size:.4f}"
                )
                return capped_size

            if sl_distance_pct > Decimal("0"):
                risk_amount = risk_capital * self.risk_per_trade_pct
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                margin_required = position_notional / self.leverage

                final_size = min(position_size, max_amount)
                was_capped = position_size > max_amount

                logger.info(
                    f"[SIZING] Entry=${entry_price:.4f}, SL=${sl_price:.4f}, "
                    f"Dist={sl_distance_pct*100:.2f}%, Risk=${risk_amount:.2f}, "
                    f"Notional=${position_notional:.2f}, Size={final_size:.6f}"
                )

                if was_capped:
                    actual_notional = final_size * entry_price
                    actual_risk = actual_notional * sl_distance_pct
                    logger.info(
                        f"[CAPPED] Position capped! Target risk: ${risk_amount:.2f}, "
                        f"Actual risk: ${actual_risk:.2f} ({(actual_risk/risk_capital)*100:.2f}%)"
                    )

                return final_size

        # Fallback: use max_position_size_pct with leverage
        return max_amount

    # -------------------------
    # Helpers
    # -------------------------
    def sync_balance(self) -> Decimal:
        bal = self.exchange.fetch_balance()
        return to_decimal(bal.get("total", {}).get("USDT", 0))

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def get_position_snapshot(self, symbol: str):
        """Return a read-only PositionSnapshot for the strategy. None if no position."""
        from app.core.snapshots import PositionSnapshot
        if symbol not in self.positions:
            return PositionSnapshot(has_position=False, symbol=symbol)
        pos = self.positions[symbol]
        lock_profit_triggered = (
            pos.sl_price is not None
            and pos.entry_price is not None
            and pos.sl_price > pos.entry_price
        )
        return PositionSnapshot(
            has_position=True,
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            current_sl=pos.sl_price if pos.sl_price is not None else Decimal("0"),
            tp1_hit=pos.tp1_hit,
            tp2_hit=pos.tp2_hit,
            tp3_hit=pos.tp3_hit,
            lock_profit_triggered=lock_profit_triggered,
        )

    def close_position(self, symbol: str, _percentage: Decimal = Decimal("1.0"), price: Decimal = None, reason: str = "MANUAL") -> None:
        """Close position (full exit). _percentage reserved for future partial-close support."""
        self._handle_full_sell(symbol, price=price, exit_reason=reason)

    def move_stop_loss(self, symbol: str, new_sl_price: Decimal) -> bool:
        """Move the stop loss order to a new price level."""
        return self._move_sl_to_entry(symbol, new_sl_price)

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
    # TP Fill Sync (LFT Polling)
    # -------------------------
    def sync_tp_fills(self, symbol: str) -> None:
        """
        Check if any TP orders have filled. Update position accordingly.
        Called after each candle close (polling approach for LFT).
        """
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        for tp_level, order_id in list(pos.tp_order_ids.items()):
            try:
                order = self.exchange.fetch_order(order_id, symbol)
                if order.get("status") in ("closed", "filled"):
                    filled_amount = to_decimal(order.get("filled", order.get("amount", 0)))
                    pos.amount -= filled_amount
                    setattr(pos, f"{tp_level.lower()}_hit", True)
                    del pos.tp_order_ids[tp_level]

                    logger.info(f"[{symbol}] {tp_level} filled: {filled_amount}, remaining: {pos.amount}")

                    # Move SL to breakeven after TP1
                    if tp_level == "TP1" and pos.amount > Decimal("0"):
                        self._move_sl_to_entry(symbol)
            except Exception as e:
                logger.warning(f"Failed to check {tp_level} order {order_id}: {e}")

        # Cleanup if fully closed
        if pos.amount <= Decimal("1e-8"):
            self._cleanup_position(symbol)

    def _cleanup_position(self, symbol: str) -> None:
        """Cancel remaining orders and remove position from tracking."""
        pos = self.positions.get(symbol)
        if not pos:
            return

        # Cancel SL order
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass

        # Cancel remaining TP orders
        for tp_level, order_id in list(pos.tp_order_ids.items()):
            try:
                self.exchange.cancel_order(order_id, symbol)
            except Exception:
                pass

        self.positions.pop(symbol, None)

    # -------------------------
    # SL Management
    # -------------------------
    def _move_sl_to_entry(self, symbol: str, new_price: Decimal = None, new_amount: Decimal = None) -> bool:
        """
        Cancel existing SL and replace with stop_market at target price.
        If new_price is None, uses entry price (breakeven).
        All SL orders use reduceOnly=True.
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        if pos.amount <= Decimal("0"):
            return False

        target_price = new_price if new_price is not None else pos.entry_price
        amount = new_amount if new_amount is not None else pos.amount

        # Cancel existing SL
        if pos.sl_order_id:
            try:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            except Exception:
                pass
            pos.sl_order_id = None

        # Place new stop_market SL with reduceOnly
        try:
            sl_order = self.exchange.create_order(
                symbol=symbol,
                order_type="stop_market",
                side="SELL",
                amount=amount,
                params={
                    "stopPrice": target_price,
                    "reduceOnly": True,
                    "exit_reason": self._sl_exit_reason(target_price, pos.entry_price),
                },
            )
            if sl_order:
                pos.sl_order_id = sl_order.get("id")
                logger.info(f"[{symbol}] SL moved to {target_price} (stop_market, reduceOnly)")
                return True
        except Exception as e:
            logger.error(f"Failed to place SL for {symbol}: {e}")

        return False

    @staticmethod
    def _sl_exit_reason(sl_price: Decimal, entry_price: Decimal) -> str:
        """Dynamic exit reason based on SL price vs entry."""
        if sl_price > entry_price:
            return "LOCK_PROFIT"
        elif sl_price == entry_price:
            return "BREAKEVEN"
        else:
            return "STOP_LOSS"

    # -------------------------
    # TP Placement
    # -------------------------
    def _place_tp_orders(self, signal: SignalEvent, total_amount: Decimal) -> Dict[str, str]:
        """Place TP1/TP2/TP3 as limit orders on exchange with reduceOnly=True."""
        tp_order_ids = {}
        remaining = total_amount

        allocs = signal.tp_allocations or {}

        levels = [
            ("TP1", signal.tp1_price, Decimal(str(allocs.get("TP1", self.tp1_close_pct)))),
            ("TP2", signal.tp2_price, Decimal(str(allocs.get("TP2", self.tp2_close_pct)))),
            ("TP3", signal.tp3_price, Decimal("1.0")),  # close all remaining
        ]

        for label, tp_price, pct in levels:
            if tp_price is None or remaining <= Decimal("0"):
                continue

            close_amount = remaining * pct
            if close_amount <= Decimal("0"):
                continue

            try:
                order = self.exchange.create_order(
                    symbol=signal.symbol,
                    order_type="limit",
                    side="SELL",
                    amount=close_amount,
                    price=tp_price,
                    params={"reduceOnly": True, "exit_reason": label},
                )
                if order and order.get("id"):
                    tp_order_ids[label] = order["id"]
            except Exception as e:
                logger.error(f"Failed to place {label} order for {signal.symbol}: {e}")

            remaining -= close_amount

        return tp_order_ids

    # -------------------------
    # Main entry
    # -------------------------
    def on_signal(self, signal: SignalEvent):
        """
        Process a trading signal.
        - BUY: market entry + stop_market SL + limit TP1/TP2/TP3
        - SELL:
            + SOFT_SL: pre-execution guard + market close
            + MOVE_SL*: only move SL, do not sell
            + TP1/TP2/TP3: partial close (manual override)
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

            # --- Soft SL with pre-execution guard ---
            if "SOFT_SL" in reason:
                return self._handle_soft_sl_exit(signal)

            # --- special SELL: move SL only ---
            if (
                "MOVE_SL_TO_ENTRY" in reason
                or "SL_TO_ENTRY" in reason
                or "BREAKEVEN" in reason
                or reason.startswith("MOVE_SL")
            ):
                new_sl_price = signal.price if signal.price else None
                self._move_sl_to_entry(signal.symbol, new_sl_price)
                return None

            # --- TP partial closes (manual override for non-polling scenarios) ---
            if reason.startswith("TP1"):
                return self.execute_partial_close(signal.symbol, "TP1", new_sl_price=signal.sl_price)
            if reason.startswith("TP2"):
                return self.execute_partial_close(signal.symbol, "TP2", new_sl_price=signal.sl_price)
            if reason.startswith("TP3"):
                return self.execute_partial_close(signal.symbol, "TP3", new_sl_price=signal.sl_price)

            # Any other SELL -> close full
            exit_reason = signal.reason or "MANUAL"
            return self._handle_full_sell(signal.symbol, price=signal.price, exit_reason=exit_reason)

        return None

    # -------------------------
    # BUY logic
    # -------------------------
    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal):
        if signal.symbol in self.positions:
            logger.warning(f"[{signal.symbol}] Skipping BUY: position already exists")
            return None

        price = signal.price
        if price <= Decimal("0"):
            logger.warning(f"[{signal.symbol}] Skipping BUY: invalid price {price}")
            return None

        # Position sizing: Use soft_sl_price for risk calculation
        sizing_sl = signal.soft_sl_price if signal.soft_sl_price is not None else signal.sl_price
        amount = self._calculate_position_size(balance, price, sizing_sl)

        # 1. Market BUY
        try:
            order = self.exchange.create_order(
                symbol=signal.symbol,
                order_type="market",
                side="BUY",
                amount=amount,
                price=price,  # hint for MockExchange
            )
            if not order:
                logger.warning(f"[{signal.symbol}] Skipping BUY: create_order returned None")
                return None
        except InsufficientFundsError as e:
            logger.warning(f"Insufficient funds for {signal.symbol}: {e}")
            return None
        except ExchangeError as e:
            logger.error(f"Failed to execute buy for {signal.symbol}: {e}")
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
            lock_profit_price=signal.lock_profit_price,
            tp_allocations=signal.tp_allocations,
        )

        # 2. Place hard SL as STOP_MARKET (reduceOnly)
        if signal.sl_price is not None:
            try:
                sl_order = self.exchange.create_order(
                    symbol=signal.symbol,
                    order_type="stop_market",
                    side="SELL",
                    amount=amount,
                    params={
                        "stopPrice": signal.sl_price,
                        "reduceOnly": True,
                        "exit_reason": "STOP_LOSS",
                    },
                )
                if sl_order:
                    self.positions[signal.symbol].sl_order_id = sl_order.get("id")
            except Exception as e:
                logger.error(f"Failed to place SL order for {signal.symbol}: {e}")

        # 3. Place TP limit orders (reduceOnly)
        tp_orders = self._place_tp_orders(signal, amount)
        self.positions[signal.symbol].tp_order_ids = tp_orders

        # 4. Notify on entry — skip if exchange fires its own entry notification (e.g. SimExchange)
        if self._notification_service and not getattr(self.exchange, "_fires_entry_notification", False):
            tp_prices = {k: v for k, v in [
                ("TP1", signal.tp1_price), ("TP2", signal.tp2_price), ("TP3", signal.tp3_price)
            ] if v is not None}
            try:
                self._notification_service.on_entry(
                    symbol=signal.symbol,
                    side="LONG",
                    entry_price=price,
                    amount=amount,
                    sl_price=signal.sl_price,
                    tp_prices=tp_prices or None,
                    leverage=int(self.leverage),
                    balance=balance,
                )
            except Exception:
                logger.warning(f"[{signal.symbol}] on_entry notification failed")

        return order

    # -------------------------
    # Soft SL with pre-execution guard
    # -------------------------
    def _handle_soft_sl_exit(self, signal: SignalEvent):
        """Execute soft SL with pre-execution position check to prevent double-sell."""
        symbol = signal.symbol

        # Pre-execution guard: verify position still exists on exchange
        try:
            positions = self.exchange.fetch_positions([symbol])
            has_exchange_position = any(
                abs(float(p.get("contracts", 0))) > 0 for p in positions
            )
        except Exception as e:
            logger.warning(f"Failed to fetch positions for {symbol}: {e}")
            has_exchange_position = True  # Assume position exists, try to close

        if not has_exchange_position:
            # Hard SL already fired — just cleanup local state
            logger.info(f"[{symbol}] Soft SL: no exchange position (hard SL already fired)")
            self._cleanup_position(symbol)
            return None

        # Position exists, safe to close
        return self._handle_full_sell(symbol, price=signal.price, exit_reason="SOFT_SL")

    # -------------------------
    # SELL logic
    # -------------------------
    def _handle_full_sell(self, symbol: str, price: Decimal = None, exit_reason: str = "MANUAL"):
        """Close entire remaining position at market and cleanup."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Cancel all pending orders for this symbol (SL + TPs)
        try:
            cancel_fn = getattr(self.exchange, "cancel_all_orders", None)
            if callable(cancel_fn):
                cancel_fn(symbol)
            else:
                # Fallback: cancel individually
                if pos.sl_order_id:
                    self.exchange.cancel_order(pos.sl_order_id, symbol)
                for order_id in pos.tp_order_ids.values():
                    self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.warning(f"Failed to cancel orders for {symbol}: {e}")

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                order_type="market",
                side="SELL",
                amount=pos.amount,
                price=price,
                params={"reduceOnly": True, "exit_reason": exit_reason},
            )

            if order:
                fill_price = price or pos.entry_price
                closed_amount = pos.amount
                self.positions.pop(symbol, None)

                # Notify on fill — skip if exchange fires its own fill notification (e.g. SimExchange)
                if self._notification_service and not getattr(self.exchange, "_fires_fill_notification", False):
                    try:
                        self._notification_service.on_fill(
                            symbol=symbol,
                            exit_reason=exit_reason,
                            fill_price=fill_price,
                            amount=closed_amount,
                        )
                    except Exception:
                        logger.warning(f"[{symbol}] on_fill notification failed")

                return order
        except ExchangeError as e:
            logger.error(f"Failed to execute full sell for {symbol}: {e}")
            return None

        return None

    def execute_partial_close(self, symbol: str, tp_level: str, new_sl_price: Optional[Decimal] = None):
        """
        Execute partial close for TP levels (manual override).
        For the normal flow, TPs are exchange-managed limit orders detected by sync_tp_fills().
        This method is kept for manual partial close or strategy-driven TP signals.
        """
        self.sync_from_exchange()

        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        tp_level = tp_level.upper().strip()

        if tp_level == "TP1" and pos.tp1_hit:
            if new_sl_price and pos.amount > Decimal("0"):
                self._move_sl_to_entry(symbol, new_sl_price)
            return None
        if tp_level == "TP2" and pos.tp2_hit:
            return None
        if tp_level == "TP3" and pos.tp3_hit:
            return None

        close_amount = Decimal("0")
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
            pct = Decimal(str(allocs.get("TP3", "1.0")))
            close_amount = pos.amount * pct
            pos.tp3_hit = True

        if close_amount <= Decimal("0"):
            return None

        # Cancel the specific TP order if it was placed on exchange
        tp_order_id = pos.tp_order_ids.pop(tp_level, None)
        if tp_order_id:
            try:
                self.exchange.cancel_order(tp_order_id, symbol)
            except Exception:
                pass

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                order_type="market",
                side="SELL",
                amount=close_amount,
                params={"reduceOnly": True, "exit_reason": tp_level},
            )
            if not order:
                return None
        except ExchangeError as e:
            logger.error(f"Failed to execute partial close {tp_level} for {symbol}: {e}")
            return None

        pos.amount -= close_amount

        if pos.amount > Decimal("0"):
            self._move_sl_to_entry(symbol, new_price=new_sl_price)

        if pos.amount <= Decimal("1e-8"):
            self._cleanup_position(symbol)

        return order
