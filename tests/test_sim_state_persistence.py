"""
tests/test_sim_state_persistence.py

Sim balance + session anchor must survive a bot restart (deploy) so the user
doesn't see their running session P&L wiped on every upgrade.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.trading.exchange.sim.sim_exchange import SimExchange
from app.trading.exchange.sim.sim_state import SimTradeState


@pytest.fixture()
def snapshot_path(tmp_path, monkeypatch):
    path = tmp_path / "rsi_bot_sim_state.json"
    monkeypatch.setattr("app.core.constants.SIM_STATE_FILE_PATH", str(path))
    return str(path)


def test_snapshot_round_trip(snapshot_path):
    state = SimTradeState(Decimal("10000"))
    state.balance = Decimal("11535.11")
    state.total_fees_paid = Decimal("12.34")
    state.total_funding_paid = Decimal("0.5")

    state.write_snapshot(snapshot_path)

    fresh = SimTradeState(Decimal("10000"))
    assert fresh.try_restore({"initial_balance": 10000}, snapshot_path) is True
    assert fresh.balance == Decimal("11535.11")
    assert fresh.initial_balance == Decimal("10000")
    assert fresh.total_fees_paid == Decimal("12.34")
    assert fresh.total_funding_paid == Decimal("0.5")


def test_restore_no_snapshot_returns_false(snapshot_path):
    state = SimTradeState(Decimal("10000"))
    assert state.try_restore({"initial_balance": 10000}, snapshot_path) is False
    assert state.balance == Decimal("10000")


def test_restore_discards_when_initial_balance_changed(snapshot_path):
    SimTradeState(Decimal("10000")).write_snapshot(snapshot_path)

    fresh = SimTradeState(Decimal("20000"))
    assert fresh.try_restore({"initial_balance": 20000}, snapshot_path) is False
    assert fresh.balance == Decimal("20000")
    # Mismatched snapshot is unlinked so it can't pollute future starts.
    assert not os.path.exists(snapshot_path)


def test_reset_clears_snapshot(snapshot_path):
    state = SimTradeState(Decimal("10000"))
    state.balance = Decimal("11000")
    state.write_snapshot(snapshot_path)
    assert os.path.exists(snapshot_path)

    state.reset()

    assert not os.path.exists(snapshot_path)


def test_sim_exchange_restores_balance_on_init(snapshot_path):
    seed = SimTradeState(Decimal("10000"))
    seed.balance = Decimal("11535.11")
    seed.write_snapshot(snapshot_path)

    cfg = {
        "bot": {"mode": "sim"},
        "sim": {"initial_balance": 10000, "telegram_token": ""},
        "risk": {"leverage": 10},
    }
    ex = SimExchange(cfg, notification_service=MagicMock())

    assert ex.state.balance == Decimal("11535.11")
    assert ex.state.initial_balance == Decimal("10000")


def test_sim_exchange_starts_fresh_when_config_changed(snapshot_path):
    seed = SimTradeState(Decimal("10000"))
    seed.balance = Decimal("11535.11")
    seed.write_snapshot(snapshot_path)

    cfg = {
        "bot": {"mode": "sim"},
        "sim": {"initial_balance": 25000, "telegram_token": ""},
        "risk": {"leverage": 10},
    }
    ex = SimExchange(cfg, notification_service=MagicMock())

    assert ex.state.balance == Decimal("25000")
    assert ex.state.initial_balance == Decimal("25000")


def test_corrupt_snapshot_is_safe(snapshot_path):
    with open(snapshot_path, "w") as f:
        f.write("{not valid json")

    state = SimTradeState(Decimal("10000"))
    assert state.try_restore({"initial_balance": 10000}, snapshot_path) is False
    assert state.balance == Decimal("10000")


def test_snapshot_payload_shape(snapshot_path):
    state = SimTradeState(Decimal("10000"))
    state.balance = Decimal("11000")
    state.total_fees_paid = Decimal("3.21")
    state.write_snapshot(snapshot_path)

    with open(snapshot_path) as f:
        data = json.load(f)
    assert set(data.keys()) >= {"balance", "initial_balance", "total_fees_paid", "total_funding_paid"}
    assert data["balance"] == "11000"
    assert data["initial_balance"] == "10000"
