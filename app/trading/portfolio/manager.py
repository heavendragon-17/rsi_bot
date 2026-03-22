"""
Layer 3: Execution - Portfolio Manager (Facade)
================================================
Thin facade over decomposed portfolio components.
Preserves the original PortfolioManager API for backward compatibility.

Components:
- Position (models.py) — position dataclass
- PositionSizer (position_sizer.py) — risk-based sizing
- SLTPManager (sl_tp_manager.py) — SL/TP placement, tracking, partial closes
- NotificationDispatcher (notification_dispatch.py) — entry/exit notifications
- TradeExecutor (trade_executor.py) — entry/exit orchestration
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.core.events import SignalEvent
from app.core.interfaces import IExchange

# Re-export Position so existing imports keep working:
#   from app.trading.portfolio.manager import PortfolioManager, Position
from app.trading.portfolio.models import Position  # noqa: F401
from app.trading.portfolio.notification_dispatch import NotificationDispatcher
from app.trading.portfolio.position_sizer import PositionSizer
from app.trading.portfolio.sl_tp_manager import SLTPManager
from app.trading.portfolio.trade_executor import TradeExecutor

logger = structlog.get_logger()


class PortfolioManager:
    """Facade over decomposed portfolio components.

    Uses normalized order type vocabulary:
    - SL placed as stop_market (not limit) with reduceOnly=True
    - TP placed as limit with reduceOnly=True
    - All exit orders include reduceOnly=True
    """

    def __init__(self, exchange: IExchange, config: dict, notification_service=None):
        self.exchange = exchange
        self.config = config
        self.positions: dict[str, Position] = {}

        # Compose components — all share the same positions dict by reference
        self._sizer = PositionSizer(config, exchange)
        self._sl_tp = SLTPManager(exchange, config)
        self._dispatcher = NotificationDispatcher(notification_service, exchange)
        self._executor = TradeExecutor(
            exchange,
            self.positions,
            self._sizer,
            self._sl_tp,
            self._dispatcher,
        )

        # Expose config values that tests/consumers may read
        self.leverage = self._sizer.leverage
        self.initial_capital = self._sizer.initial_capital
        self.tp1_close_pct = self._sl_tp.tp1_close_pct
        self.tp2_close_pct = self._sl_tp.tp2_close_pct

    # ---- Delegate to TradeExecutor ----

    def on_signal(self, signal: SignalEvent):
        """Process a trading signal."""
        return self._executor.on_signal(signal)

    def close_position(
        self,
        symbol: str,
        _percentage: Decimal = Decimal("1.0"),
        price: Decimal = None,
        reason: str = "MANUAL",
    ) -> None:
        """Close position (full exit)."""
        self._executor._handle_full_exit(symbol, price=price, exit_reason=reason)

    # ---- Delegate to SLTPManager ----

    def move_stop_loss(self, symbol: str, new_sl_price: Decimal) -> bool:
        """Move the stop loss order to a new price level."""
        return self._sl_tp.move_sl(symbol, self.positions, new_sl_price)

    def sync_tp_fills(self, symbol: str) -> None:
        """Check if any TP orders have filled."""
        self._sl_tp.sync_tp_fills(symbol, self.positions)

    def execute_partial_close(
        self,
        symbol: str,
        tp_level: str,
        new_sl_price: Decimal | None = None,
    ):
        """Execute partial close for TP levels."""
        return self._sl_tp.execute_partial_close(
            symbol,
            self.positions,
            tp_level,
            new_sl_price=new_sl_price,
            exchange_sync_fn=self._executor.sync_from_exchange,
        )

    # ---- Delegate to PositionSizer ----

    def _calculate_position_size(
        self,
        balance: Decimal,
        entry_price: Decimal,
        sl_price: Decimal | None,
    ) -> Decimal:
        """Backward-compatible delegate for position sizing."""
        return self._sizer.calculate(balance, entry_price, sl_price)

    def sync_balance(self) -> Decimal:
        return self._sizer.sync_balance()

    # ---- Position queries (kept inline) ----

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def get_position_snapshot(self, symbol: str):
        """Return a read-only PositionSnapshot for the strategy."""
        from app.core.snapshots import PositionSnapshot

        if symbol not in self.positions:
            return PositionSnapshot(has_position=False, symbol=symbol)
        pos = self.positions[symbol]
        if pos.sl_price is not None and pos.entry_price is not None:
            lock_profit_triggered = pos.sl_price > pos.entry_price if pos.is_long() else pos.sl_price < pos.entry_price
        else:
            lock_profit_triggered = False
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

    def sync_from_exchange(self) -> None:
        """Make portfolio positions consistent with exchange positions."""
        self._executor.sync_from_exchange()

    # ---- Static helpers (backward compat) ----

    @staticmethod
    def _sl_exit_reason(sl_price: Decimal, entry_price: Decimal, position_side: str = "BUY") -> str:
        """Dynamic exit reason based on SL price vs entry."""
        return SLTPManager.sl_exit_reason(sl_price, entry_price, position_side)
