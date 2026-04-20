"""
tests/test_portfolio_sync_from_exchange.py

Regression tests for PortfolioManager.sync_from_exchange() — the reconciler
that purges in-memory positions when the exchange no longer reports them
(hard SL filled, manual close on Binance, liquidation, etc.).

Bug history: the previous implementation gated on hasattr(exchange, "positions"),
which was always False (neither SimExchange nor BinanceAdapter expose a
.positions attribute), so stale entries accumulated forever in the portfolio
and blocked the deploy pipeline from ever running.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trading.portfolio.manager import PortfolioManager
from app.trading.portfolio.models import Position

SYMBOL = "BTC/USDT"


def _config() -> dict:
    return {
        "risk": {"leverage": 1, "risk_per_trade_pct": 0.02, "tp1_close_pct": 0.5, "tp2_close_pct": 0.5},
        "backtest": {"initial_balance": 10000},
        "symbols": [SYMBOL],
    }


def _fake_exchange(positions_payload):
    ex = MagicMock()
    ex.fetch_positions = MagicMock(return_value=positions_payload)
    ex.fetch_balance = MagicMock(return_value={"total": {"USDT": 10000.0}, "free": {"USDT": 10000.0}})
    return ex


def _seed_position(pm: PortfolioManager, symbol: str = SYMBOL):
    pm.positions[symbol] = Position(
        symbol=symbol,
        side="BUY",
        amount=Decimal("0.01"),
        entry_price=Decimal("50000"),
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
    )


class TestSyncFromExchange:
    def test_purges_stale_when_exchange_reports_none(self):
        ex = _fake_exchange([])
        pm = PortfolioManager(ex, _config())
        _seed_position(pm)
        assert SYMBOL in pm.positions

        pm.sync_from_exchange()

        assert SYMBOL not in pm.positions
        ex.fetch_positions.assert_called_once()

    def test_keeps_position_still_open_on_exchange(self):
        ex = _fake_exchange([{"symbol": SYMBOL, "contracts": 0.01}])
        pm = PortfolioManager(ex, _config())
        _seed_position(pm)

        pm.sync_from_exchange()

        assert SYMBOL in pm.positions

    def test_treats_zero_contracts_as_closed(self):
        ex = _fake_exchange([{"symbol": SYMBOL, "contracts": 0.0}])
        pm = PortfolioManager(ex, _config())
        _seed_position(pm)

        pm.sync_from_exchange()

        assert SYMBOL not in pm.positions

    def test_no_op_when_local_dict_empty(self):
        ex = _fake_exchange([])
        pm = PortfolioManager(ex, _config())

        pm.sync_from_exchange()

        ex.fetch_positions.assert_not_called()
        assert pm.positions == {}

    def test_swallows_fetch_positions_failure(self):
        ex = _fake_exchange([])
        ex.fetch_positions.side_effect = RuntimeError("network blip")
        pm = PortfolioManager(ex, _config())
        _seed_position(pm)

        # Should not raise; should not purge on transient error either.
        pm.sync_from_exchange()
        assert SYMBOL in pm.positions
