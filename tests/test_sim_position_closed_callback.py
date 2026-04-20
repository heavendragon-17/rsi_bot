"""
tests/test_sim_position_closed_callback.py

When a hard SL fills inside SimExchange, the in-memory position dict on
PortfolioManager must be cleared the same instant — otherwise the deploy
pipeline reads phantom positions from StatusWriter and refuses to upgrade.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.trading.exchange.sim.sim_exchange import SimExchange
from app.trading.exchange.sim.sim_state import SimTradeState
from app.trading.portfolio.manager import PortfolioManager
from app.trading.portfolio.models import Position

SYMBOL = "BTC/USDT"


def _config() -> dict:
    return {
        "bot": {"mode": "sim"},
        "sim": {"initial_balance": 10000, "telegram_token": ""},
        "risk": {"leverage": 10, "risk_per_trade_pct": 0.02, "tp1_close_pct": 0.5, "tp2_close_pct": 0.5},
        "backtest": {"initial_balance": 10000},
        "symbols": [SYMBOL],
    }


@pytest.fixture()
def sim_exchange(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.core.constants.SIM_STATE_FILE_PATH",
        str(tmp_path / "rsi_bot_sim_state.json"),
    )
    return SimExchange(_config(), notification_service=MagicMock())


def test_register_position_closed_callback_runs_on_fire(sim_exchange):
    received: list[str] = []
    sim_exchange.register_position_closed_callback(received.append)

    sim_exchange._fire_position_closed(SYMBOL)

    assert received == [SYMBOL]


def test_callback_failure_does_not_propagate(sim_exchange):
    def boom(_symbol):
        raise RuntimeError("listener crash")

    received: list[str] = []
    sim_exchange.register_position_closed_callback(boom)
    sim_exchange.register_position_closed_callback(received.append)

    # Must not raise; subsequent listeners still fire.
    sim_exchange._fire_position_closed(SYMBOL)
    assert received == [SYMBOL]


def test_portfolio_manager_clears_position_on_fire(sim_exchange):
    pm = PortfolioManager(sim_exchange, _config())
    pm.positions[SYMBOL] = Position(
        symbol=SYMBOL,
        side="BUY",
        amount=Decimal("0.01"),
        entry_price=Decimal("50000"),
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
    )

    sim_exchange._fire_position_closed(SYMBOL)

    assert SYMBOL not in pm.positions


def test_callback_is_noop_for_unknown_symbol(sim_exchange):
    pm = PortfolioManager(sim_exchange, _config())
    pm.positions["ETH/USDT"] = Position(
        symbol="ETH/USDT",
        side="BUY",
        amount=Decimal("0.1"),
        entry_price=Decimal("3000"),
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
    )

    sim_exchange._fire_position_closed("BTC/USDT")

    assert "ETH/USDT" in pm.positions
