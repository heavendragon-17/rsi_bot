import os
from decimal import Decimal
from unittest.mock import patch

import ccxt
import pytest

from app.core.exceptions import (
    InsufficientFundsError,
    OrderNotFoundError,
    OrderRejectedError,
)
from app.trading.exchange.hyperliquid_adapter import HyperliquidAdapter, _to_external_symbol


# ==============================================================================
# Normalization Tests
# ==============================================================================
def test_to_external_symbol():
    assert _to_external_symbol("BTC/USDT") == "BTC/USDC:USDC"
    assert _to_external_symbol("ETHUSDT") == "ETH/USDC:USDC"
    assert _to_external_symbol("SOL") == "SOL/USDC:USDC"
    assert _to_external_symbol("BTC/USDC:USDC") == "BTC/USDC:USDC"
    assert _to_external_symbol("wBTC") == "WBTC/USDC:USDC"


# ==============================================================================
# Adapter Tests
# ==============================================================================


@pytest.fixture
def mock_env():
    with patch.dict(
        os.environ,
        # This is an intentionally fake credential used only by mocked tests.
        {
            "HYPERLIQUID_WALLET_ADDRESS": "0xMockWalletAddress",
            "HYPERLIQUID_PRIVATE_KEY": "MockPrivateKey123",
        },  # pragma: allowlist secret
    ):
        yield


@pytest.fixture
def mock_ccxt():
    with patch("ccxt.hyperliquid") as mock_exchange:
        instance = mock_exchange.return_value
        instance.load_markets.return_value = None
        yield instance


@pytest.fixture
def adapter(mock_env, mock_ccxt):
    return HyperliquidAdapter({"bot": {"mode": "paper"}})


def test_initialization(mock_env, mock_ccxt):
    adapter = HyperliquidAdapter()
    mock_ccxt.set_sandbox_mode.assert_called_with(True)
    mock_ccxt.load_markets.assert_called_once()
    assert adapter._mode == "paper"


def test_create_order_market(adapter, mock_ccxt):
    mock_ccxt.create_order.return_value = {"id": "123", "status": "open"}

    res = adapter.create_order(symbol="BTC/USDT", order_type="market", side="buy", amount=Decimal("0.1"))

    assert res["id"] == "123"
    mock_ccxt.create_order.assert_called_with(
        symbol="BTC/USDC:USDC", type="MARKET", side="BUY", amount=0.1, price=None, params={}
    )


def test_create_order_limit_with_reduce_only(adapter, mock_ccxt):
    mock_ccxt.create_order.return_value = {"id": "124"}

    adapter.create_order(
        symbol="ETH",
        order_type="limit",
        side="sell",
        amount=Decimal("1.5"),
        price=Decimal("3000.0"),
        params={"reduceOnly": True, "timeInForce": "IOC"},
    )

    mock_ccxt.create_order.assert_called_with(
        symbol="ETH/USDC:USDC",
        type="LIMIT",
        side="SELL",
        amount=1.5,
        price=3000.0,
        params={"reduceOnly": True, "timeInForce": "IOC"},
    )


def test_create_order_stop_market(adapter, mock_ccxt):
    adapter.create_order(
        symbol="SOL", order_type="stop_market", side="sell", amount=Decimal("10"), params={"stopPrice": "150.0"}
    )

    mock_ccxt.create_order.assert_called_with(
        symbol="SOL/USDC:USDC",
        type="STOP",  # Hyperliquid mapped stop type
        side="SELL",
        amount=10.0,
        price=None,
        params={"stopPrice": 150.0},
    )


def test_create_order_trailing_stop_raises_exception(adapter):
    with pytest.raises(OrderRejectedError) as exc:
        adapter.create_order(symbol="BTC", order_type="trailing_stop", side="sell", amount=Decimal("1"))
    assert "Trailing stops are not supported" in str(exc.value)


def test_cancel_order(adapter, mock_ccxt):
    adapter.cancel_order("ord_1", "BTC")
    mock_ccxt.cancel_order.assert_called_with("ord_1", "BTC/USDC:USDC")


def test_error_mapping_insufficient_funds(adapter, mock_ccxt):
    mock_ccxt.create_order.side_effect = ccxt.InsufficientFunds("No money")
    with pytest.raises(InsufficientFundsError):
        adapter.create_order("BTC", "market", "buy", Decimal("1"))


def test_error_mapping_order_not_found(adapter, mock_ccxt):
    mock_ccxt.fetch_order.side_effect = ccxt.OrderNotFound("Not found")
    with pytest.raises(OrderNotFoundError):
        adapter.fetch_order("bad_id", "BTC")


def test_fetch_positions_filters_zero(adapter, mock_ccxt):
    mock_ccxt.fetch_positions.return_value = [
        {"symbol": "BTC/USDC:USDC", "contracts": 1.5},
        {"symbol": "ETH/USDC:USDC", "contracts": 0.0},
    ]

    positions = adapter.fetch_positions(["BTC"])
    mock_ccxt.fetch_positions.assert_called_with(["BTC/USDC:USDC"])

    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTC/USDC:USDC"


def test_set_leverage(adapter, mock_ccxt):
    adapter.set_leverage(20, "BTC")
    mock_ccxt.set_leverage.assert_called_with(20, "BTC/USDC:USDC")
