"""Tests for exchange factory + BinanceAdapter order-type translation."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import ccxt
import pytest

from app.core.exceptions import (
    ConnectionError,
    ExchangeError,
    InsufficientFundsError,
    OrderNotFoundError,
    OrderRejectedError,
    RateLimitError,
)
from app.trading.exchange.binance_adapter import (
    _get_credentials,
    _to_external_symbol,
)
from app.trading.exchange.factory import (
    EXCHANGE_CONFIG,
    _load_custom_adapter,
    create_exchange,
)


class TestSymbolNormalize:
    def test_already_futures(self):
        assert _to_external_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"

    def test_slash_no_colon(self):
        assert _to_external_symbol("BTC/USDT") == "BTC/USDT:USDT"

    def test_no_slash_usdt_suffix(self):
        assert _to_external_symbol("BTCUSDT") == "BTC/USDT:USDT"

    def test_empty(self):
        assert _to_external_symbol("") == ""

    def test_lowercase(self):
        assert _to_external_symbol("btcusdt") == "BTC/USDT:USDT"

    def test_unknown_pattern(self):
        assert _to_external_symbol("XYZ") == "XYZ"


class TestGetCredentials:
    def test_paper_env_missing_raises(self, monkeypatch):
        monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_TESTNET_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            _get_credentials("paper")

    def test_live_env_missing_raises(self, monkeypatch):
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            _get_credentials("live")

    def test_paper_env_present(self, monkeypatch):
        monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
        monkeypatch.setenv("BINANCE_TESTNET_SECRET_KEY", "s")
        api, sec = _get_credentials("paper")
        assert (api, sec) == ("k", "s")


@pytest.fixture
def mock_ccxt_exchange():
    with patch("app.trading.exchange.binance_adapter.ccxt") as MockCcxt:
        mock_exchange = MagicMock()
        MockCcxt.binanceusdm.return_value = mock_exchange
        # Re-expose exception classes for except branches
        MockCcxt.InsufficientFunds = ccxt.InsufficientFunds
        MockCcxt.InvalidOrder = ccxt.InvalidOrder
        MockCcxt.OrderNotFound = ccxt.OrderNotFound
        MockCcxt.RateLimitExceeded = ccxt.RateLimitExceeded
        MockCcxt.NetworkError = ccxt.NetworkError
        MockCcxt.BaseError = ccxt.BaseError
        mock_exchange.load_markets.return_value = {}
        yield mock_exchange


def _mk_adapter(mock_exchange, monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET_KEY", "s")
    from app.trading.exchange.binance_adapter import BinanceAdapter
    adapter = BinanceAdapter({"bot": {"mode": "paper"}})
    return adapter


class TestBinanceAdapter:
    def test_init_paper_sandbox(self, mock_ccxt_exchange, monkeypatch):
        _mk_adapter(mock_ccxt_exchange, monkeypatch)
        mock_ccxt_exchange.set_sandbox_mode.assert_called_with(True)

    def test_create_market_order(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.return_value = {"id": "123"}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        result = adapter.create_order("BTC/USDT", "market", "buy", Decimal("1"))
        assert result == {"id": "123"}

    def test_create_stop_market_translation(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.return_value = {"id": "s"}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        adapter.create_order(
            "BTCUSDT", "stop_market", "sell", Decimal("1"),
            params={"stopPrice": 95.0, "reduceOnly": True},
        )
        call = mock_ccxt_exchange.create_order.call_args
        assert call.kwargs["type"] == "STOP_MARKET"
        assert call.kwargs["params"]["stopPrice"] == 95.0
        assert call.kwargs["params"]["reduceOnly"] is True

    def test_create_limit_has_gtc(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.return_value = {"id": "L"}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        adapter.create_order("BTCUSDT", "limit", "sell", Decimal("1"), price=Decimal("110"))
        call = mock_ccxt_exchange.create_order.call_args
        assert call.kwargs["params"]["timeInForce"] == "GTC"

    def test_create_trailing_stop(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.return_value = {"id": "T"}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        adapter.create_order(
            "BTCUSDT", "trailing_stop", "sell", Decimal("1"),
            params={"callbackRate": 1.5},
        )
        call = mock_ccxt_exchange.create_order.call_args
        assert call.kwargs["type"] == "TRAILING_STOP_MARKET"
        assert call.kwargs["params"]["callbackRate"] == 1.5

    def test_create_order_insufficient_funds_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.side_effect = ccxt.InsufficientFunds("no money")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(InsufficientFundsError):
            adapter.create_order("BTC", "market", "buy", Decimal("1"))

    def test_create_order_invalid_order_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.side_effect = ccxt.InvalidOrder("rejected")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(OrderRejectedError):
            adapter.create_order("BTC", "market", "buy", Decimal("1"))

    def test_create_order_rate_limit_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.create_order.side_effect = ccxt.RateLimitExceeded("slow")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(RateLimitError):
            adapter.create_order("BTC", "market", "buy", Decimal("1"))

    def test_fetch_order(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_order.return_value = {"id": "1"}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.fetch_order("1", "BTC/USDT") == {"id": "1"}

    def test_fetch_order_not_found_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_order.side_effect = ccxt.OrderNotFound("gone")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(OrderNotFoundError):
            adapter.fetch_order("1", "BTC")

    def test_cancel_order(self, mock_ccxt_exchange, monkeypatch):
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.cancel_order("1", "BTC/USDT") is True

    def test_cancel_order_not_found_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.cancel_order.side_effect = ccxt.OrderNotFound("nope")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(OrderNotFoundError):
            adapter.cancel_order("1", "BTC")

    def test_cancel_all_orders(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.cancel_all_orders.return_value = [{"id": 1}, {"id": 2}]
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.cancel_all_orders("BTC") == 2

    def test_fetch_open_orders(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_open_orders.return_value = [{"id": 1}]
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.fetch_open_orders("BTC") == [{"id": 1}]

    def test_set_leverage(self, mock_ccxt_exchange, monkeypatch):
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.set_leverage(5, "BTC") is True

    def test_fetch_positions_filters_zero(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_positions.return_value = [
            {"symbol": "BTC", "contracts": 0.0},
            {"symbol": "ETH", "contracts": 1.5},
        ]
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        out = adapter.fetch_positions(["BTC", "ETH"])
        assert len(out) == 1
        assert out[0]["symbol"] == "ETH"

    def test_fetch_balance(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_balance.return_value = {"total": {"USDT": 1000}}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.fetch_balance() == {"total": {"USDT": 1000}}

    def test_fetch_balance_network_error_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_balance.side_effect = ccxt.NetworkError("oops")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(ConnectionError):
            adapter.fetch_balance()

    def test_fetch_balance_base_error_mapped(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_balance.side_effect = ccxt.BaseError("oops")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        with pytest.raises(ExchangeError):
            adapter.fetch_balance()

    def test_fetch_ohlcv(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_ohlcv.return_value = [[1, 2, 3, 4, 5, 6]]
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.fetch_ohlcv("BTC", "5m", limit=100) == [[1, 2, 3, 4, 5, 6]]

    def test_get_precision_info(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.markets = {"BTC/USDT:USDT": {}}
        mock_ccxt_exchange.market.return_value = {
            "precision": {"price": 2, "amount": 3},
        }
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.get_precision_info("BTC") == (2, 3)

    def test_get_precision_info_fallback(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.markets = None
        mock_ccxt_exchange.market.side_effect = Exception("fail")
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.get_precision_info("BTC") == (2, 3)

    def test_fetch_ticker(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_ticker.return_value = {"last": 100}
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.fetch_ticker("BTC") == {"last": 100}

    def test_check_position_active(self, mock_ccxt_exchange, monkeypatch):
        mock_ccxt_exchange.fetch_positions.return_value = [
            {"symbol": "BTC", "contracts": 1.5},
        ]
        adapter = _mk_adapter(mock_ccxt_exchange, monkeypatch)
        assert adapter.check_position_active("BTC") is True


class TestFactory:
    def test_sim_mode_creates_sim_exchange(self):
        with patch("app.trading.exchange.sim.sim_exchange.SimExchange") as MockSim:
            instance = MagicMock()
            MockSim.return_value = instance
            ns = MagicMock()
            ns.attach_exchange = MagicMock()
            ns.start_command_polling = MagicMock()
            result = create_exchange({"bot": {"mode": "sim"}}, notification_service=ns)
            assert result is instance
            ns.attach_exchange.assert_called_once()

    def test_mock_mode_creates_mock_exchange(self):
        with patch("app.backtest.exchange.mock_exchange.MockExchange") as MockEx:
            instance = MagicMock()
            MockEx.return_value = instance
            result = create_exchange({"bot": {"mode": "mock"}, "backtest": {"initial_balance": 5000}, "risk": {"leverage": 5}})
            MockEx.assert_called_once_with(initial_balance=5000, leverage=5)
            assert result is instance

    def test_custom_adapter_import_missing(self, monkeypatch):
        with pytest.raises(ValueError, match="Could not load adapter"):
            _load_custom_adapter("nonexistent_xyz", {})

    def test_binance_ccxt_mode(self, monkeypatch):
        monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
        monkeypatch.setenv("BINANCE_TESTNET_SECRET_KEY", "s")
        with patch("app.trading.exchange.binance_adapter.ccxt") as MockCcxt:
            mock_exchange = MagicMock()
            MockCcxt.binanceusdm.return_value = mock_exchange
            ns = MagicMock()
            config = {"bot": {"mode": "paper"}, "exchange": {"name": "binance"}}
            result = create_exchange(config, notification_service=ns)
            assert result is not None

    def test_exchange_config_mapping(self):
        assert "binance" in EXCHANGE_CONFIG
        assert EXCHANGE_CONFIG["binance"]["env_prefix"] == "BINANCE"
