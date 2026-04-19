# app/sim/exchange.py
"""
SimExchange
=============
Implements IExchange using local order simulation against live
Binance aggTrade tick data.  PortfolioManager calls this identically
to BinanceAdapter — it is completely unaware of sim mode.

Delegates order storage and fill detection to FillSimulator(TickFillMode).
Owns position/balance state via SimTradeState.

Fill execution logic (position open/close, notifications, position linking)
is delegated to module-level functions in ``sim_fill_handler``.

Order lifecycle
---------------
Entry (market, no reduceOnly):
    create_order() → status=pending_open
    on_kline_open(symbol, open_price) → execute_fill_from_order(order, open_price)

SL (stop_market, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≤ stop_price) → execute_fill_from_result(fill_result)

TP (limit, reduceOnly=True):
    create_order() → status=pending
    on_tick(price ≥ limit_price) → execute_fill_from_result(fill_result)

Soft SL (market, reduceOnly=True):
    create_order() → fills immediately at current tick price
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import structlog

from app.core.constants import DEFAULT_MAKER_FEE_DECIMAL, DEFAULT_TAKER_FEE_DECIMAL
from app.core.exceptions import OrderRejectedError
from app.core.interfaces import IExchange
from app.core.utils import to_decimal
from app.trading.exchange.fill_simulator import (
    FillSimulator,
    PendingOrder,
    TickFillMode,
)
from app.trading.exchange.sim.sim_fill_handler import (
    execute_fill_from_order,
    execute_fill_from_result,
    link_sl_to_position,
)
from app.trading.exchange.sim.sim_liquidation import check_liquidation
from app.trading.exchange.sim.sim_state import SimTradeState

logger = structlog.get_logger()

TAKER_FEE = DEFAULT_TAKER_FEE_DECIMAL
MAKER_FEE = DEFAULT_MAKER_FEE_DECIMAL


class SimExchange(IExchange):
    """
    Local futures order simulator.  Thread-safe via SimTradeState.lock.
    Delegates fill detection and order storage to FillSimulator(TickFillMode).
    Fill execution delegated to sim_fill_handler module functions.
    """

    def __init__(self, config: dict, notification_service: Any = None) -> None:
        sim_cfg = config.get("sim", config.get("paper_sim", {}))
        initial_balance = to_decimal(sim_cfg.get("initial_balance", 10000))

        self.state = SimTradeState(initial_balance)
        self._config = config
        self._last_prices: dict[str, Decimal] = {}
        self._sim_time: float | None = None

        self._notification_service = notification_service
        # Entry notifications are fired by the portfolio dispatcher *after*
        # SL/TP orders have been placed, so the entry card can include them.
        # Fills still come from sim because they happen on tick, not on signal.
        self._fires_entry_notification: bool = False
        self._fires_fill_notification: bool = True
        self._pending_indicators: dict[str, dict[str, float]] = {}  # staging for entry indicators

        # Fill simulator for pending SL/TP order management and fill detection
        self._sim_instance: FillSimulator | None = FillSimulator(TickFillMode(), MAKER_FEE, TAKER_FEE)
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

    def fetch_balance(self, params: dict | None = None) -> dict:
        with self.state.lock:
            bal = float(self.state.balance)
        return {
            "free": {"USDT": bal},
            "used": {"USDT": 0.0},
            "total": {"USDT": bal},
            "USDT": {"free": bal, "used": 0.0, "total": bal},
        }

    def fetch_positions(self, symbols: list[str] | None = None) -> list[dict]:
        with self.state.lock:
            result = []
            for sym, pos in self.state.positions.items():
                if symbols and sym not in symbols:
                    continue
                last_price = self._last_prices.get(sym, pos.entry_price)
                upnl = (last_price - pos.entry_price) * pos.amount
                result.append(
                    {
                        "symbol": sym,
                        "contracts": float(pos.amount),
                        "side": "long",
                        "entryPrice": float(pos.entry_price),
                        "unrealizedPnl": float(upnl),
                    }
                )
        return result

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        with self.state.lock:
            return [self._order_to_dict(o) for o in self._sim.get_pending_orders(symbol)]

    def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
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
        price: Decimal | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        params = params or {}
        reduce_only = bool(params.get("reduceOnly", False))
        stop_price = to_decimal(params.get("stopPrice")) if params.get("stopPrice") else None
        amount = to_decimal(amount)
        price = to_decimal(price) if price else None

        if self.state.is_paused and not reduce_only:
            logger.warning(f"[SimExchange] Paused (post-liquidation) — rejecting {order_type} {side} for {symbol}")
            return None

        if amount <= Decimal("0"):
            logger.warning(f"[SimExchange] Rejecting {order_type} {side} {symbol}: non-positive amount {amount}")
            return None

        # Stash indicator snapshot for entry notifications
        if params.get("_indicators") and not reduce_only:
            self._pending_indicators[symbol] = params["_indicators"]

        # reduceOnly guard: skip if no position exists
        if reduce_only:
            with self.state.lock:
                if symbol not in self.state.positions:
                    logger.debug(f"[SimExchange] reduceOnly order for {symbol} skipped — no open position")
                    return None

        order_id = str(uuid.uuid4())
        order_info: dict[str, Any] = {}
        if order_type == "stop_market" and params.get("soft_sl_price") is not None:
            order_info["soft_sl_price"] = to_decimal(params["soft_sl_price"])
        po = PendingOrder(
            id=order_id,
            symbol=symbol,
            order_type=order_type,
            side=side,
            amount=amount,
            price=price,
            trigger_price=stop_price,
            reduce_only=reduce_only,
            status="pending",
            info=order_info,
        )

        # Market BUY (entry) → immediate fill or pending_open
        if order_type == "market" and side == "BUY" and not reduce_only:
            last_price = self._last_prices.get(symbol, Decimal("0"))
            if last_price > Decimal("0"):
                self._sim.add_order(po)
                execute_fill_from_order(self, po, last_price)
                logger.info(
                    f"[SimExchange] Entry filled immediately ({order_id[:8]}) — {symbol} {amount} @ {last_price}"
                )
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
            execute_fill_from_order(self, po, last_price)
            return self._po_to_dict(po)

        # stop_market SL or limit TP → wait for tick scanner
        self._sim.add_order(po)
        logger.debug(
            f"[SimExchange] Order queued ({order_id[:8]}) — {order_type} {side} {symbol} @ {stop_price or price}"
        )

        if order_type == "stop_market" and side == "SELL" and stop_price:
            soft_sl_raw = params.get("soft_sl_price")
            risk_sl = to_decimal(soft_sl_raw) if soft_sl_raw is not None else None
            link_sl_to_position(self, symbol, order_id, stop_price, risk_sl_price=risk_sl)

        return self._po_to_dict(po)

    # ── Sim-specific hooks ───────────────────────────────────────

    def on_kline_open(self, symbol: str, open_price: Decimal) -> None:
        open_price = to_decimal(open_price)
        with self.state.lock:
            orders = [o for o in self._sim.get_pending_orders(symbol) if o.status == "pending_open"]
        for order in orders:
            logger.info(f"[SimExchange] Filling entry order at candle open {open_price} — {symbol}")
            execute_fill_from_order(self, order, open_price)

    def on_tick(self, symbol: str, price: Decimal, timestamp: float) -> None:
        price = to_decimal(price)
        self._last_prices[symbol] = price

        fill_results = self._sim.process_market_data(
            symbol,
            price,
            self._get_position_amount,
        )

        for fr in fill_results:
            execute_fill_from_result(self, fr)

        check_liquidation(self)

    def is_paused(self) -> bool:
        return self.state.is_paused

    # ── Dict conversion ─────────────────────────────────────────

    @staticmethod
    def _order_to_dict(po: PendingOrder) -> dict[str, Any]:
        return {
            "id": po.id,
            "symbol": po.symbol,
            "type": po.order_type,
            "side": po.side,
            "amount": float(po.amount),
            "price": float(po.price) if po.price else None,
            "stopPrice": float(po.trigger_price) if po.trigger_price else None,
            "reduceOnly": po.reduce_only,
            "status": po.status,
            "filled": 0.0,
            "fillPrice": None,
            "timestamp": int(time.time() * 1000),
        }

    _po_to_dict = _order_to_dict
