"""Trade execution orchestration: entry, exit, and signal routing."""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.actions import (
    EXIT_BREAKEVEN,
    EXIT_MANUAL,
    EXIT_SOFT_SL,
    EXIT_STOP_LOSS,
    EXIT_TP1,
    EXIT_TP2,
    EXIT_TP3,
    SIDE_BUY,
    SIDE_SELL,
    opposite_side,
)
from app.core.events import SignalEvent
from app.core.exceptions import ExchangeError, InsufficientFundsError
from app.core.interfaces import IExchange
from app.trading.portfolio.models import Position
from app.trading.portfolio.notification_dispatch import NotificationDispatcher
from app.trading.portfolio.position_sizer import PositionSizer
from app.trading.portfolio.sl_tp_manager import SLTPManager

logger = structlog.get_logger()


class TradeExecutor:
    """Orchestrates trade entry, exit, and signal routing."""

    def __init__(
        self,
        exchange: IExchange,
        positions: dict[str, Position],
        sizer: PositionSizer,
        sl_tp: SLTPManager,
        dispatcher: NotificationDispatcher,
    ):
        self.exchange = exchange
        self.positions = positions
        self._sizer = sizer
        self._sl_tp = sl_tp
        self._dispatcher = dispatcher

    def sync_from_exchange(self) -> None:
        """Remove positions that no longer exist on exchange (e.g. SL filled)."""
        if not hasattr(self.exchange, "positions"):
            return
        for sym in list(self.positions.keys()):
            if sym not in self.exchange.positions:
                self.positions.pop(sym, None)

    def on_signal(self, signal: SignalEvent):
        """Process a trading signal. Routes to entry, exit, or SL/TP handlers."""
        self.sync_from_exchange()

        if signal.signal_type == SIDE_BUY:
            balance = self._sizer.sync_balance()
            return self._handle_entry_signal(signal, balance, entry_side=SIDE_BUY)

        if signal.signal_type == SIDE_SELL:
            if signal.symbol not in self.positions:
                balance = self._sizer.sync_balance()
                return self._handle_entry_signal(signal, balance, entry_side=SIDE_SELL)

            reason = (signal.reason or "").strip().upper()

            if EXIT_SOFT_SL in reason:
                return self._handle_soft_sl_exit(signal)

            if (
                "MOVE_SL_TO_ENTRY" in reason
                or "SL_TO_ENTRY" in reason
                or EXIT_BREAKEVEN in reason
                or reason.startswith("MOVE_SL")
            ):
                new_sl_price = signal.price if signal.price else None
                self._sl_tp.move_sl(signal.symbol, self.positions, new_sl_price)
                return None

            for tp_exit in (EXIT_TP1, EXIT_TP2, EXIT_TP3):
                if reason.startswith(tp_exit):
                    return self._sl_tp.execute_partial_close(
                        signal.symbol,
                        self.positions,
                        tp_exit,
                        new_sl_price=signal.sl_price,
                        exchange_sync_fn=self.sync_from_exchange,
                    )

            exit_reason = signal.reason or EXIT_MANUAL
            return self._handle_full_exit(signal.symbol, price=signal.price, exit_reason=exit_reason)

        return None

    def _handle_entry_signal(self, signal: SignalEvent, balance: Decimal, entry_side: str = SIDE_BUY):
        """Open a new position (long or short)."""
        if signal.symbol in self.positions:
            logger.warning(f"[{signal.symbol}] Skipping {entry_side}: position already exists")
            return None

        price = signal.price
        if price <= Decimal("0"):
            logger.warning(f"[{signal.symbol}] Skipping {entry_side}: invalid price {price}")
            return None

        sizing_sl = signal.soft_sl_price if signal.soft_sl_price is not None else signal.sl_price
        amount = self._sizer.calculate(balance, price, sizing_sl)

        if amount <= Decimal("0"):
            logger.warning(f"[{signal.symbol}] Skipping {entry_side}: zero position size")
            return None

        exit_side = opposite_side(entry_side)

        entry_params: dict = {}
        if signal.indicators:
            entry_params["_indicators"] = signal.indicators

        try:
            order = self.exchange.create_order(
                symbol=signal.symbol,
                order_type="market",
                side=entry_side,
                amount=amount,
                price=price,
                params=entry_params or None,
            )
            if not order:
                logger.warning(f"[{signal.symbol}] Skipping {entry_side}: create_order returned None")
                return None
        except InsufficientFundsError as e:
            logger.warning(f"Insufficient funds for {signal.symbol}: {e}")
            return None
        except ExchangeError as e:
            logger.error(f"Failed to execute {entry_side} for {signal.symbol}: {e}")
            return None

        signed_amount = amount if entry_side == SIDE_BUY else -amount

        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            amount=signed_amount,
            entry_price=price,
            side=entry_side,
            timestamp=signal.timestamp,
            tp1_price=signal.tp1_price,
            tp2_price=signal.tp2_price,
            tp3_price=signal.tp3_price,
            sl_price=signal.sl_price,
            lock_profit_price=signal.lock_profit_price,
            tp_allocations=signal.tp_allocations,
        )

        if signal.sl_price is not None:
            try:
                sl_params = {
                    "stopPrice": signal.sl_price,
                    "reduceOnly": True,
                    "exit_reason": EXIT_STOP_LOSS,
                }
                if signal.soft_sl_price is not None:
                    sl_params["soft_sl_price"] = signal.soft_sl_price
                sl_order = self.exchange.create_order(
                    symbol=signal.symbol,
                    order_type="stop_market",
                    side=exit_side,
                    amount=amount,
                    params=sl_params,
                )
                if sl_order:
                    self.positions[signal.symbol].sl_order_id = sl_order.get("id")
            except Exception as e:
                logger.error(f"Failed to place SL order for {signal.symbol}: {e}")

        tp_orders = self._sl_tp.place_tp_orders(signal, amount, position_side=entry_side)
        self.positions[signal.symbol].tp_order_ids = tp_orders

        self._dispatcher.notify_entry(
            symbol=signal.symbol,
            entry_side=entry_side,
            price=price,
            amount=amount,
            signal=signal,
            leverage=int(self._sizer.leverage),
            balance=balance,
        )

        return order

    def _handle_soft_sl_exit(self, signal: SignalEvent):
        """Execute soft SL with pre-execution position check to prevent double-sell."""
        symbol = signal.symbol

        try:
            positions = self.exchange.fetch_positions([symbol])
            has_exchange_position = any(abs(float(p.get("contracts", 0))) > 0 for p in positions)
        except Exception as e:
            logger.warning(f"Failed to fetch positions for {symbol}: {e}")
            has_exchange_position = True

        if not has_exchange_position:
            logger.info(f"[{symbol}] Soft SL: no exchange position (hard SL already fired)")
            self._sl_tp.cleanup_position(symbol, self.positions)
            return None

        return self._handle_full_exit(symbol, price=signal.price, exit_reason=EXIT_SOFT_SL)

    def _handle_full_exit(self, symbol: str, price: Decimal = None, exit_reason: str = EXIT_MANUAL):
        """Close entire remaining position at market and cleanup."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        exit_amount = abs(pos.amount)

        try:
            cancel_fn = getattr(self.exchange, "cancel_all_orders", None)
            if callable(cancel_fn):
                cancel_fn(symbol)
            else:
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
                side=pos.exit_side,
                amount=exit_amount,
                price=price,
                params={"reduceOnly": True, "exit_reason": exit_reason},
            )

            if order:
                fill_price = price or pos.entry_price
                closed_amount = exit_amount
                self.positions.pop(symbol, None)

                self._dispatcher.notify_exit(
                    symbol=symbol,
                    exit_reason=exit_reason,
                    fill_price=fill_price,
                    amount=closed_amount,
                )

                return order
        except ExchangeError as e:
            logger.error(f"Failed to execute full exit for {symbol}: {e}")
            return None

        return None
