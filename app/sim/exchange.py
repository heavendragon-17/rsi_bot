# app/sim/exchange.py
"""
SimExchange
=============
Implements IExchange using local order simulation against live
Binance aggTrade tick data.  PortfolioManager calls this identically
to BinanceAdapter — it is completely unaware of sim mode.

Order lifecycle
---------------
Entry (market, no reduceOnly):
    create_order() → status=pending_open
    on_kline_open(symbol, open_price) → _execute_fill(order, open_price)

SL (stop_market, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≤ stop_price) → _execute_fill(order, stop_price)

TP (limit, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≥ limit_price) → _execute_fill(order, limit_price)

Soft SL (market, reduceOnly=True):
    create_order() → fills immediately at current tick price

Lock-profit:
    PortfolioManager calls cancel_order(old_sl_id) + create_order(stop_market, new_sl)
    The new stop_market order is then monitored by the tick scanner.
"""
from __future__ import annotations

import time
import structlog
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.core.exceptions import OrderRejectedError
from app.core.interfaces import IExchange
from app.sim.state import ClosedTrade, SimOrder, SimPosition, SimTradeState

logger = structlog.get_logger()

TAKER_FEE = Decimal("0.0005")   # 0.05%
MAKER_FEE = Decimal("0.0002")   # 0.02%


def _to_dec(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)) if val is not None else Decimal("0")


class SimExchange(IExchange):
    """
    Local futures order simulator.  Thread-safe via SimTradeState.lock.
    """

    def __init__(self, config: dict, notification_service=None):
        sim_cfg = config.get("sim", config.get("paper_sim", {}))
        initial_balance = _to_dec(sim_cfg.get("initial_balance", 10000))

        self.state = SimTradeState(initial_balance)
        self._config = config
        self._last_prices: Dict[str, Decimal] = {}   # latest tick price per symbol
        self._sim_time: Optional[float] = None  # set by replay script to override time.time()

        # Notification: injected from outside (not self-created)
        self._notification_service = notification_service

        # Flags that tell PortfolioManager SimExchange handles its own notifications
        # so PortfolioManager skips firing duplicate events in sim mode.
        self._fires_entry_notification: bool = True
        self._fires_fill_notification: bool = True

        logger.info(f"SimExchange initialised — balance={initial_balance} USDT")

    # ------------------------------------------------------------------
    # IExchange interface
    # ------------------------------------------------------------------

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        logger.info(f"[SimExchange] set_leverage({leverage}, {symbol}) — no-op in sim mode")
        return True

    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        with self.state.lock:
            bal = float(self.state.balance)
        return {
            "free": {"USDT": bal},
            "used": {"USDT": 0.0},
            "total": {"USDT": bal},
            "USDT": {"free": bal, "used": 0.0, "total": bal},
        }

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        with self.state.lock:
            result = []
            for sym, pos in self.state.positions.items():
                if symbols and sym not in symbols:
                    continue
                last_price = self._last_prices.get(sym, pos.entry_price)
                upnl = (last_price - pos.entry_price) * pos.amount
                result.append({
                    "symbol": sym,
                    "contracts": float(pos.amount),
                    "side": "long",
                    "entryPrice": float(pos.entry_price),
                    "unrealizedPnl": float(upnl),
                })
        return result

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.state.lock:
            orders = [
                self._order_to_dict(o)
                for o in self.state.pending_orders.values()
                if symbol is None or o.symbol == symbol
            ]
        return orders

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        with self.state.lock:
            order = self.state.pending_orders.get(order_id)
        if order:
            return self._order_to_dict(order)
        return {"id": order_id, "status": "not_found"}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        return self.state.cancel_order(order_id)

    def cancel_all_orders(self, symbol: str) -> int:
        return self.state.cancel_orders_for_symbol(symbol)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        # Not needed in sim mode — kline data comes from BinanceStreamManager
        return []

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        params = params or {}
        reduce_only = bool(params.get("reduceOnly", False))
        stop_price = _to_dec(params.get("stopPrice")) if params.get("stopPrice") else None
        amount = _to_dec(amount)
        price = _to_dec(price) if price else None

        # reduceOnly guard: skip if no position exists
        if reduce_only:
            with self.state.lock:
                if symbol not in self.state.positions:
                    logger.debug(
                        f"[SimExchange] reduceOnly order for {symbol} skipped — no open position"
                    )
                    return None

        order = SimOrder(
            id=str(uuid.uuid4()),
            symbol=symbol,
            order_type=order_type,
            side=side,
            amount=amount,
            price=price,
            stop_price=stop_price,
            reduce_only=reduce_only,
            status="pending",
            created_at=time.time(),
        )

        # Market BUY (entry) → pending_open (fills at next candle open)
        if order_type == "market" and side == "BUY" and not reduce_only:
            order.status = "pending_open"
            self.state.add_order(order)
            logger.info(f"[SimExchange] Entry order queued ({order.id[:8]}) — {symbol} {amount}")
            return self._order_to_dict(order)

        # Market SELL with reduceOnly → immediate fill at current tick price (soft SL)
        if order_type == "market" and reduce_only:
            last_price = self._last_prices.get(symbol, Decimal("0"))
            if last_price <= 0:
                raise OrderRejectedError(
                    f"[SimExchange] No tick price for {symbol}; cannot fill market reduceOnly order"
                )
            order.status = "pending"
            self.state.add_order(order)
            self._execute_fill(order, last_price)
            return self._order_to_dict(order)

        # stop_market SL or limit TP → wait for tick scanner
        self.state.add_order(order)
        logger.debug(f"[SimExchange] Order queued ({order.id[:8]}) — {order_type} {side} {symbol} @ {stop_price or price}")

        # Back-fill position metadata so initial_risk and TP tracking are accurate
        if order_type == "stop_market" and side == "SELL" and stop_price:
            self._link_sl_to_position(symbol, order.id, stop_price)

        return self._order_to_dict(order)

    # ------------------------------------------------------------------
    # Sim-specific hooks called by MultiSymbolRunner
    # ------------------------------------------------------------------

    def on_kline_open(self, symbol: str, open_price: Decimal) -> None:
        """
        Fill pending_open market entry orders at the new candle open price.
        Called by MultiSymbolRunner._run_symbol_loop() on each new candle.
        """
        open_price = _to_dec(open_price)
        with self.state.lock:
            orders = [
                o for o in list(self.state.pending_orders.values())
                if o.symbol == symbol and o.status == "pending_open"
            ]
        for order in orders:
            logger.info(f"[SimExchange] Filling entry order at candle open {open_price} — {symbol}")
            self._execute_fill(order, open_price)

    def on_tick(self, symbol: str, price: Decimal, timestamp: float) -> None:
        """
        Scan all pending SL/TP orders for the symbol.
        Called by SimTradeStreamManager every 500 ms.
        Processes orders in insertion order (FIFO) — first fill wins.
        """
        price = _to_dec(price)
        self._last_prices[symbol] = price

        with self.state.lock:
            orders = [
                o for o in list(self.state.pending_orders.values())
                if o.symbol == symbol and o.status == "pending"
            ]

        for order in orders:
            triggered = False

            if order.order_type == "stop_market" and order.side == "SELL":
                # Hard SL: fill when price drops to or below stop_price
                if order.stop_price and price <= order.stop_price:
                    self._execute_fill(order, order.stop_price)
                    triggered = True

            elif order.order_type == "limit" and order.side == "SELL":
                # TP: fill when price rises to or above limit_price
                if order.price and price >= order.price:
                    self._execute_fill(order, order.price)
                    triggered = True

            if triggered:
                self._post_fill_hook(order)

    def is_paused(self) -> bool:
        return self.state.is_paused

    # ------------------------------------------------------------------
    # Internal fill logic
    # ------------------------------------------------------------------

    def _execute_fill(self, order: SimOrder, fill_price: Decimal) -> None:
        """
        Mark order as filled, calculate fees, update position and balance.
        Emits notification event after state update.
        """
        notify_entry = None   # (symbol, side, entry_price, amount, balance)
        notify_fill = None    # (symbol, exit_reason, fill_price, amount, pnl_gross, pnl_net, fees, r_multiple, remaining, balance)

        with self.state.lock:
            # Already filled or cancelled?
            if order.status in ("filled", "cancelled"):
                return
            if order.id not in self.state.pending_orders:
                return

            order.status = "filled"
            order.fill_price = fill_price
            order.filled_at = self._sim_time or time.time()
            del self.state.pending_orders[order.id]

            # --- BUY (entry) ---
            if order.side == "BUY":
                fee = fill_price * order.amount * TAKER_FEE
                self.state.balance -= fee
                self.state.total_fees_paid += fee
                self._open_position_locked(order, fill_price, fee)
                # Capture SL/TP from pending_orders (placed before kline_open fires)
                _sl_price = None
                _tp_prices: Dict[str, Decimal] = {}
                for o in self.state.pending_orders.values():
                    if o.symbol == order.symbol and o.side == "SELL":
                        if o.order_type == "stop_market" and o.stop_price:
                            _sl_price = o.stop_price
                        elif o.order_type == "limit" and o.price:
                            _tp_prices[f"TP{len(_tp_prices) + 1}"] = o.price
                # Capture for notification outside lock
                notify_entry = (
                    order.symbol, "LONG", fill_price, order.amount,
                    self.state.balance, _sl_price, _tp_prices or None,
                )
                return

            # --- SELL (SL or TP) ---
            position = self.state.positions.get(order.symbol)
            if not position:
                return

            close_amount = min(order.amount, position.amount)
            if close_amount <= 0:
                return

            # Fee
            if order.order_type == "limit":
                fee = fill_price * close_amount * MAKER_FEE
            else:
                fee = fill_price * close_amount * TAKER_FEE

            # P&L
            pnl_gross = (fill_price - position.entry_price) * close_amount
            pnl_net = pnl_gross - fee

            # Funding attribution (pro-rata by close amount / initial amount)
            funding_attr = Decimal("0")

            # Update balance
            self.state.balance += pnl_net
            self.state.total_fees_paid += fee

            # Determine exit reason
            exit_reason = self._exit_reason(order, position)

            # Build ClosedTrade
            trade = ClosedTrade(
                symbol=order.symbol,
                entry_price=position.entry_price,
                exit_price=fill_price,
                amount=close_amount,
                side="long",
                pnl_gross=pnl_gross,
                fees_paid=fee,
                funding_paid=funding_attr,
                pnl_net=pnl_net,
                r_multiple=(pnl_net / position.initial_risk) if position.initial_risk else Decimal("0"),
                exit_reason=exit_reason,
                opened_at=0.0,  # set in _open_position_locked
                closed_at=order.filled_at or self._sim_time or time.time(),
            )

            # Update or close position
            position.amount -= close_amount
            remaining = position.amount
            if position.amount <= Decimal("0.000001"):
                del self.state.positions[order.symbol]
                self.state.closed_trades.append(trade)
            else:
                self.state.closed_trades.append(trade)

            balance_after = self.state.balance

            # Capture for notification outside lock
            notify_fill = (
                order.symbol, exit_reason, fill_price, close_amount,
                pnl_gross, pnl_net, fee, trade.r_multiple,
                remaining if remaining > Decimal("0.000001") else Decimal("0"),
                balance_after,
            )

        # Emit notifications outside lock
        if notify_entry and self._notification_service:
            sym, side, ep, amt, bal, sl_price, tp_prices = notify_entry
            leverage = self._config.get("risk", {}).get("leverage", 1)
            try:
                self._notification_service.on_entry(
                    symbol=sym, side=side, entry_price=ep,
                    amount=amt, sl_price=sl_price, tp_prices=tp_prices,
                    leverage=leverage, balance=bal,
                )
            except Exception:
                logger.exception("notification on_entry failed")

        if notify_fill and self._notification_service:
            sym, reason, fp, amt, pnl_g, pnl_n, fees, r_mult, rem, bal = notify_fill
            try:
                self._notification_service.on_fill(
                    symbol=sym, exit_reason=reason, fill_price=fp,
                    amount=amt, pnl_gross=pnl_g, pnl_net=pnl_n,
                    fees=fees, r_multiple=r_mult, remaining_amount=rem,
                    balance=bal,
                )
            except Exception:
                logger.exception("notification on_fill failed")

    def _open_position_locked(
        self, order: SimOrder, fill_price: Decimal, entry_fee: Decimal
    ) -> None:
        """Called inside lock during BUY fill. Position opened here."""
        pos = SimPosition(
            symbol=order.symbol,
            side="long",
            amount=order.amount,
            entry_price=fill_price,
            initial_amount=order.amount,
            initial_risk=Decimal("0"),  # updated when SL order is linked
        )
        pos._opened_at = order.filled_at or self._sim_time or time.time()  # type: ignore[attr-defined]
        self.state.positions[order.symbol] = pos

        logger.info(
            f"[SimExchange] Position opened — {order.symbol} {order.amount} @ {fill_price}"
        )

    def _post_fill_hook(self, order: SimOrder) -> None:
        """
        Called after a SELL fill (SL or TP).
        Updates TP hit flags on position.
        """
        with self.state.lock:
            pos = self.state.positions.get(order.symbol)
            if not pos:
                return

            exit_reason = self._exit_reason_no_lock(order, pos)

            if exit_reason == "TP1":
                pos.tp1_hit = True
            elif exit_reason == "TP2":
                pos.tp2_hit = True

    def _link_sl_to_position(self, symbol: str, sl_order_id: str, sl_price: Decimal) -> None:
        """
        Called by SimExchange.create_order() when a stop_market SL is created,
        to back-fill initial_risk on the position.
        """
        with self.state.lock:
            pos = self.state.positions.get(symbol)
            if pos:
                pos.sl_order_id = sl_order_id
                if pos.initial_risk == Decimal("0"):
                    pos.initial_risk = abs(pos.entry_price - sl_price) * pos.initial_amount

    def _link_tp_to_position(self, symbol: str, tp_label: str, tp_order_id: str) -> None:
        with self.state.lock:
            pos = self.state.positions.get(symbol)
            if pos:
                pos.tp_order_ids[tp_label] = tp_order_id

    def _exit_reason(self, order: SimOrder, position: SimPosition) -> str:
        return self._exit_reason_no_lock(order, position)

    def _exit_reason_no_lock(self, order: SimOrder, position: SimPosition) -> str:
        if order.order_type == "stop_market":
            return "HARD_SL"
        if order.order_type == "market" and order.reduce_only:
            return "CANDLE_SL"
        # limit TP — determine which TP level by checking tp_order_ids
        for label, oid in position.tp_order_ids.items():
            if oid == order.id:
                return label
        # Fallback: use TP progress
        if not position.tp1_hit:
            return "TP1"
        if not position.tp2_hit:
            return "TP2"
        return "TP3"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _order_to_dict(self, order: SimOrder) -> Dict[str, Any]:
        return {
            "id": order.id,
            "symbol": order.symbol,
            "type": order.order_type,
            "side": order.side,
            "amount": float(order.amount),
            "price": float(order.price) if order.price else None,
            "stopPrice": float(order.stop_price) if order.stop_price else None,
            "reduceOnly": order.reduce_only,
            "status": order.status,
            "filled": float(order.fill_price * order.amount) if order.fill_price else 0.0,
            "fillPrice": float(order.fill_price) if order.fill_price else None,
            "timestamp": int(order.created_at * 1000),
        }
