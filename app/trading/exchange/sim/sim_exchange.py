# app/sim/exchange.py
"""
SimExchange
=============
Implements IExchange using local order simulation against live
Binance aggTrade tick data.  PortfolioManager calls this identically
to BinanceAdapter — it is completely unaware of sim mode.

Delegates order storage and fill detection to FillSimulator(TickFillMode).
Owns position/balance state via SimTradeState.

Order lifecycle
---------------
Entry (market, no reduceOnly):
    create_order() → status=pending_open
    on_kline_open(symbol, open_price) → _execute_fill(order, open_price)

SL (stop_market, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≤ stop_price) → _execute_fill(fill_result)

TP (limit, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≥ limit_price) → _execute_fill(fill_result)

Soft SL (market, reduceOnly=True):
    create_order() → fills immediately at current tick price
"""
from __future__ import annotations

import time
import structlog
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.core.constants import DEFAULT_TAKER_FEE_DECIMAL, DEFAULT_MAKER_FEE_DECIMAL
from app.core.exceptions import OrderRejectedError
from app.core.interfaces import IExchange
from app.trading.exchange.fill_simulator import (
    FillSimulator, TickFillMode, PendingOrder,
)
from app.trading.exchange.sim.sim_state import ClosedTrade, SimPosition, SimTradeState

logger = structlog.get_logger()

TAKER_FEE = DEFAULT_TAKER_FEE_DECIMAL
MAKER_FEE = DEFAULT_MAKER_FEE_DECIMAL


def _to_dec(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)) if val is not None else Decimal("0")


class SimExchange(IExchange):
    """
    Local futures order simulator.  Thread-safe via SimTradeState.lock.
    Delegates fill detection and order storage to FillSimulator(TickFillMode).
    """

    def __init__(self, config: dict, notification_service: Any = None) -> None:
        sim_cfg = config.get("sim", config.get("paper_sim", {}))
        initial_balance = _to_dec(sim_cfg.get("initial_balance", 10000))

        self.state = SimTradeState(initial_balance)
        self._config = config
        self._last_prices: Dict[str, Decimal] = {}
        self._sim_time: Optional[float] = None

        self._notification_service = notification_service
        self._fires_entry_notification: bool = True
        self._fires_fill_notification: bool = True

        # Fill simulator for pending SL/TP order management and fill detection
        self._sim_instance: Optional[FillSimulator] = FillSimulator(TickFillMode(), MAKER_FEE, TAKER_FEE)
        # Bridge: state.pending_orders → simulator's dict for backward compat
        self.state.pending_orders = self._sim_instance.pending_orders  # type: ignore[assignment]

        logger.info(f"SimExchange initialised — balance={initial_balance} USDT")

    @property
    def _sim(self) -> FillSimulator:
        """Lazy-init FillSimulator (supports __new__-based test construction)."""
        inst = self.__dict__.get("_sim_instance")
        if inst is None:
            inst = FillSimulator(TickFillMode(), MAKER_FEE, TAKER_FEE)
            self._sim_instance = inst
            # Bridge: let state.pending_orders reference the simulator's dict
            # so tests that read state.pending_orders still work.
            if hasattr(self, "state"):
                self.state.pending_orders = inst.pending_orders  # type: ignore[assignment]
        return inst

    # ── Position amount callback for FillSimulator ───────────────

    def _get_position_amount(self, symbol: str) -> Decimal:
        pos = self.state.positions.get(symbol)
        return pos.amount if pos else Decimal("0")

    # ── IExchange interface ──────────────────────────────────────

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        logger.info(f"[SimExchange] set_leverage({leverage}, {symbol}) — no-op in sim mode")
        return True

    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        with self.state.lock:
            bal = float(self.state.balance)
        return {
            "free": {"USDT": bal}, "used": {"USDT": 0.0},
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
                    "symbol": sym, "contracts": float(pos.amount),
                    "side": "long", "entryPrice": float(pos.entry_price),
                    "unrealizedPnl": float(upnl),
                })
        return result

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.state.lock:
            return [self._order_to_dict(o)
                    for o in self._sim.get_pending_orders(symbol)]

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        with self.state.lock:
            po = self._sim.get_order(order_id)
        if po:
            return self._po_to_dict(po)
        return {"id": order_id, "status": "not_found"}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        return self._sim.cancel_order(order_id)

    def cancel_all_orders(self, symbol: str) -> int:
        return self._sim.cancel_all_orders(symbol)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
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
                    logger.debug(f"[SimExchange] reduceOnly order for {symbol} skipped — no open position")
                    return None

        order_id = str(uuid.uuid4())
        po = PendingOrder(
            id=order_id, symbol=symbol, order_type=order_type, side=side,
            amount=amount, price=price, trigger_price=stop_price,
            reduce_only=reduce_only, status="pending",
            info={},
        )

        # Market BUY (entry) → immediate fill or pending_open
        if order_type == "market" and side == "BUY" and not reduce_only:
            last_price = self._last_prices.get(symbol, Decimal("0"))
            if last_price > Decimal("0"):
                self._sim.add_order(po)
                self._execute_fill_from_order(po, last_price)
                logger.info(f"[SimExchange] Entry filled immediately ({order_id[:8]}) — {symbol} {amount} @ {last_price}")
            else:
                po.status = "pending_open"
                self._sim.add_order(po)
                logger.info(f"[SimExchange] Entry order queued ({order_id[:8]}) — {symbol} {amount}")
            return self._po_to_dict(po)

        # Market SELL with reduceOnly → immediate fill at current tick (soft SL)
        if order_type == "market" and reduce_only:
            last_price = self._last_prices.get(symbol, Decimal("0"))
            if last_price <= 0:
                raise OrderRejectedError(
                    f"[SimExchange] No tick price for {symbol}; cannot fill market reduceOnly order"
                )
            self._sim.add_order(po)
            self._execute_fill_from_order(po, last_price)
            return self._po_to_dict(po)

        # stop_market SL or limit TP → wait for tick scanner
        self._sim.add_order(po)
        logger.debug(f"[SimExchange] Order queued ({order_id[:8]}) — {order_type} {side} {symbol} @ {stop_price or price}")

        if order_type == "stop_market" and side == "SELL" and stop_price:
            self._link_sl_to_position(symbol, order_id, stop_price)

        return self._po_to_dict(po)

    # ── Sim-specific hooks ───────────────────────────────────────

    def on_kline_open(self, symbol: str, open_price: Decimal) -> None:
        open_price = _to_dec(open_price)
        with self.state.lock:
            orders = [o for o in self._sim.get_pending_orders(symbol)
                      if o.status == "pending_open"]
        for order in orders:
            logger.info(f"[SimExchange] Filling entry order at candle open {open_price} — {symbol}")
            self._execute_fill_from_order(order, open_price)

    def on_tick(self, symbol: str, price: Decimal, timestamp: float) -> None:
        price = _to_dec(price)
        self._last_prices[symbol] = price

        fill_results = self._sim.process_market_data(
            symbol, price, self._get_position_amount,
        )

        for fr in fill_results:
            self._execute_fill_from_result(fr)

    def is_paused(self) -> bool:
        return self.state.is_paused

    # ── Internal fill logic ──────────────────────────────────────

    def _execute_fill_from_order(self, order: PendingOrder, fill_price: Decimal) -> None:
        """Fill a PendingOrder directly (market entries, soft SL, kline_open)."""
        notify_entry = None
        notify_fill = None

        with self.state.lock:
            if order.status in ("filled", "cancelled"):
                return
            if order.id not in self._sim.pending_orders:
                return

            order.status = "filled"
            filled_at = self._sim_time or time.time()
            self._sim.remove_order(order.id)

            if order.side == "BUY":
                fee = fill_price * order.amount * TAKER_FEE
                self.state.balance -= fee
                self.state.total_fees_paid += fee
                self._open_position_locked(order.id, order.symbol, order.amount, fill_price, filled_at, fee)
                notify_entry = self._capture_entry_notification(order.symbol, fill_price, order.amount)
            elif order.side == "SELL":
                notify_fill = self._close_position_locked(
                    order.id, order.symbol, order.amount, fill_price,
                    order.order_type, order.reduce_only, filled_at,
                )

        self._emit_notifications(notify_entry, notify_fill)

    def _execute_fill_from_result(self, fr: Any) -> None:
        """Fill from a FillResult produced by process_market_data."""
        notify_entry = None
        notify_fill = None

        with self.state.lock:
            filled_at = self._sim_time or time.time()

            if fr.side == "BUY":
                fee = fr.fill_price * fr.fill_amount * TAKER_FEE
                self.state.balance -= fee
                self.state.total_fees_paid += fee
                self._open_position_locked(fr.order_id, fr.symbol, fr.fill_amount, fr.fill_price, filled_at, fee)
                notify_entry = self._capture_entry_notification(fr.symbol, fr.fill_price, fr.fill_amount)
            elif fr.side == "SELL":
                notify_fill = self._close_position_locked(
                    fr.order_id, fr.symbol, fr.fill_amount, fr.fill_price,
                    fr.order_type, fr.reduce_only, filled_at,
                )
                self._post_fill_hook(fr.order_id, fr.symbol, fr.order_type, fr.reduce_only)

        self._emit_notifications(notify_entry, notify_fill)

    def _open_position_locked(
        self, order_id: str, symbol: str, amount: Decimal,
        fill_price: Decimal, filled_at: float, entry_fee: Decimal,
    ) -> None:
        pos = SimPosition(
            symbol=symbol, side="long", amount=amount,
            entry_price=fill_price, initial_amount=amount,
            initial_risk=Decimal("0"),
        )
        pos._opened_at = filled_at  # type: ignore[attr-defined]
        self.state.positions[symbol] = pos
        logger.info(f"[SimExchange] Position opened — {symbol} {amount} @ {fill_price}")

    def _close_position_locked(
        self, order_id: str, symbol: str, amount: Decimal,
        fill_price: Decimal, order_type: str, reduce_only: bool,
        filled_at: float,
    ) -> Optional[tuple]:
        position = self.state.positions.get(symbol)
        if not position:
            return None

        close_amount = min(amount, position.amount)
        if close_amount <= 0:
            return None

        fee = fill_price * close_amount * (MAKER_FEE if order_type == "limit" else TAKER_FEE)
        pnl_gross = (fill_price - position.entry_price) * close_amount
        pnl_net = pnl_gross - fee

        self.state.balance += pnl_net
        self.state.total_fees_paid += fee

        exit_reason = self._exit_reason_from_fields(order_id, order_type, reduce_only, position)

        trade = ClosedTrade(
            symbol=symbol, entry_price=position.entry_price,
            exit_price=fill_price, amount=close_amount, side="long",
            pnl_gross=pnl_gross, fees_paid=fee, funding_paid=Decimal("0"),
            pnl_net=pnl_net,
            r_multiple=(pnl_net / position.initial_risk) if position.initial_risk else Decimal("0"),
            exit_reason=exit_reason,
            opened_at=0.0, closed_at=filled_at,
        )

        position.amount -= close_amount
        remaining = position.amount
        if position.amount <= Decimal("0.000001"):
            del self.state.positions[symbol]
        self.state.closed_trades.append(trade)

        balance_after = self.state.balance
        return (
            symbol, exit_reason, fill_price, close_amount,
            pnl_gross, pnl_net, fee, trade.r_multiple,
            remaining if remaining > Decimal("0.000001") else Decimal("0"),
            balance_after,
        )

    def _capture_entry_notification(
        self, symbol: str, fill_price: Decimal, amount: Decimal,
    ) -> Optional[tuple]:
        _sl_price = None
        _tp_prices: Dict[str, Decimal] = {}
        for o in self._sim.get_pending_orders(symbol):
            if o.side == "SELL":
                if o.order_type == "stop_market" and o.trigger_price:
                    _sl_price = o.trigger_price
                elif o.order_type == "limit" and o.price:
                    _tp_prices[f"TP{len(_tp_prices) + 1}"] = o.price
        return (symbol, "LONG", fill_price, amount,
                self.state.balance, _sl_price, _tp_prices or None)

    def _emit_notifications(self, notify_entry: Optional[tuple], notify_fill: Optional[tuple]) -> None:
        if notify_entry and self._notification_service:
            sym, side, ep, amt, bal, sl_price, tp_prices = notify_entry
            leverage = self._config.get("risk", {}).get("leverage", 1)
            try:
                self._notification_service.on_entry(
                    symbol=sym, side=side, entry_price=ep, amount=amt,
                    sl_price=sl_price, tp_prices=tp_prices,
                    leverage=leverage, balance=bal,
                )
            except Exception:
                logger.exception("notification on_entry failed")

        if notify_fill and self._notification_service:
            sym, reason, fp, amt, pnl_g, pnl_n, fees, r_mult, rem, bal = notify_fill
            try:
                self._notification_service.on_fill(
                    symbol=sym, exit_reason=reason, fill_price=fp, amount=amt,
                    pnl_gross=pnl_g, pnl_net=pnl_n, fees=fees,
                    r_multiple=r_mult, remaining_amount=rem, balance=bal,
                )
            except Exception:
                logger.exception("notification on_fill failed")

    # ── Position metadata helpers ────────────────────────────────

    def _link_sl_to_position(self, symbol: str, sl_order_id: str, sl_price: Decimal) -> None:
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

    def _post_fill_hook(self, order_id: str, symbol: str, order_type: str, reduce_only: bool) -> None:
        pos = self.state.positions.get(symbol)
        if not pos:
            return
        exit_reason = self._exit_reason_from_fields(order_id, order_type, reduce_only, pos)
        if exit_reason == "TP1":
            pos.tp1_hit = True
        elif exit_reason == "TP2":
            pos.tp2_hit = True

    def _exit_reason_from_fields(
        self, order_id: str, order_type: str, reduce_only: bool,
        position: SimPosition,
    ) -> str:
        if order_type == "stop_market":
            return "HARD_SL"
        if order_type == "market" and reduce_only:
            return "CANDLE_SL"
        for label, oid in position.tp_order_ids.items():
            if oid == order_id:
                return label
        if not position.tp1_hit:
            return "TP1"
        if not position.tp2_hit:
            return "TP2"
        return "TP3"

    # ── Dict conversion ─────────────────────────────────────────

    @staticmethod
    def _order_to_dict(po: PendingOrder) -> Dict[str, Any]:
        return {
            "id": po.id, "symbol": po.symbol, "type": po.order_type,
            "side": po.side, "amount": float(po.amount),
            "price": float(po.price) if po.price else None,
            "stopPrice": float(po.trigger_price) if po.trigger_price else None,
            "reduceOnly": po.reduce_only, "status": po.status,
            "filled": 0.0, "fillPrice": None,
            "timestamp": int(time.time() * 1000),
        }

    _po_to_dict = _order_to_dict
