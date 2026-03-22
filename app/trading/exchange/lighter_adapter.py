"""
Lighter DEX Adapter
===================
Adapter for Lighter exchange implementing IExchange interface.
Wraps the lighter-python SDK (Async) to match CCXT interface standards (Sync).

SDK: https://github.com/elliottech/lighter-python
API Docs: https://apidocs.lighter.xyz/docs/get-started-for-programmers-1

Environment Variables:
    LIGHTER_SECRET_KEY: API private key
    LIGHTER_ACCOUNT_INDEX: Account index
    LIGHTER_API_KEY_INDEX: API key index (default: 2)
    LIGHTER_BASE_URL: Base URL (default: testnet)
"""

from __future__ import annotations

import asyncio
import structlog
import os
from decimal import Decimal
from typing import Any

from app.core.exceptions import ExchangeError
from app.core.interfaces import IExchange
from app.trading.exchange import lighter_queries

logger = structlog.get_logger(__name__)

# Lighter SDK imports
try:
    import lighter  # noqa: F401
    from lighter import SignerClient
    from lighter.api import AccountApi, OrderApi  # noqa: F401

    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning(
        "Lighter SDK import failed. " "Run: pip install git+https://github.com/elliottech/lighter-python.git"
    )


# Base URLs
LIGHTER_TESTNET_URL = "https://testnet.zklighter.elliot.ai"
LIGHTER_MAINNET_URL = "https://mainnet.zklighter.elliot.ai"


class LighterAdapter(IExchange):
    """
    Lighter exchange adapter implementing IExchange.

    Wraps the ASYNC Lighter Python SDK to provide SYNCHRONOUS
    CCXT-compatible interface. Uses asyncio.run() for each call.
    """

    def __init__(self, config: dict):
        """
        Initialize the Lighter adapter.

        Args:
            config: Bot configuration dict
        """
        if not LIGHTER_SDK_AVAILABLE:
            raise RuntimeError(
                "Lighter SDK not installed. " "Run: pip install git+https://github.com/elliottech/lighter-python.git"
            )

        self.config = config or {}

        # Load credentials from environment
        self.secret_key = os.getenv("LIGHTER_SECRET_KEY")
        if not self.secret_key:
            raise ValueError("Missing LIGHTER_SECRET_KEY environment variable")

        # API key index (user specified as 2)
        self.api_key_index = int(os.getenv("LIGHTER_API_KEY_INDEX", "2"))

        # Account index (required for SignerClient)
        self.account_index = os.getenv("LIGHTER_ACCOUNT_INDEX")
        if self.account_index:
            self.account_index = int(self.account_index)
        else:
            raise ValueError("LIGHTER_ACCOUNT_INDEX is required in .env")

        # L1 Address (required for querying account balance/positions)
        self.l1_address = os.getenv("LIGHTER_L1_ADDRESS")
        if not self.l1_address:
            raise ValueError("LIGHTER_L1_ADDRESS is required in .env " "(your wallet public address)")

        # Determine mode (paper = testnet, live = mainnet)
        mode = config.get("bot", {}).get("mode", "paper").lower()
        if mode == "paper" or mode == "mock":
            self.base_url = os.getenv("LIGHTER_BASE_URL", LIGHTER_TESTNET_URL)
        else:
            self.base_url = os.getenv("LIGHTER_BASE_URL", LIGHTER_MAINNET_URL)

        logger.info(f"LighterAdapter: Connecting to {self.base_url} " f"with Account Index {self.account_index}")

        # Symbol cache
        self._symbol_map: dict[str, str] = {}

    def _get_client(self):
        """
        Return kwargs needed to init a new SignerClient instance.

        Since we bridge async->sync with asyncio.run(), we create a new
        client per call to avoid event loop attachment issues.
        """
        return {
            "url": self.base_url,
            "api_private_keys": {self.api_key_index: self.secret_key},
            "account_index": self.account_index,
        }

    async def _cleanup_client(self, client):
        """Close the API client session."""
        if client and hasattr(client, "api_client"):
            await client.api_client.close()

    # ===== Symbol Mapping =====

    def _to_lighter_symbol(self, ccxt_symbol: str) -> int:
        """
        Convert CCXT symbol to Lighter Market Index.

        TODO: Fetch market info to map symbols dynamically.
        For now, hardcoded mapping for testnet.
        """
        if "BTC" in ccxt_symbol:
            return 1
        if "ETH" in ccxt_symbol:
            return 2

        logger.warning(f"Unknown symbol {ccxt_symbol}, defaulting to 1")
        return 1

    def _to_ccxt_symbol(self, market_id: int) -> str:
        """Convert Lighter market ID to CCXT format."""
        if market_id == 1:
            return "BTC/USDT"
        if market_id == 2:
            return "ETH/USDT"
        return f"UNKNOWN-{market_id}"

    # ===== Helper to run async code =====

    def _run_async(self, coro):
        """Run coroutine in a new event loop."""
        return asyncio.run(coro)

    # ===== IExchange Interface — Mutations =====

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Decimal | None = None,
        params: dict = None,
    ) -> dict[str, Any] | None:
        """Create an order."""

        async def _create():
            client = SignerClient(**self._get_client())
            try:
                market_id = self._to_lighter_symbol(symbol)

                amount_float = float(amount)
                price_float = float(price) if price else None

                order_type_lower = order_type.lower()
                side_lower = side.lower()

                # SDK Call
                if order_type_lower == "market":
                    resp = await client.create_market_order(
                        market_symbol=market_id,
                        side=side_lower,
                        size=amount_float,
                    )
                else:  # limit
                    if not price_float:
                        raise ValueError("Price required for limit order")
                    resp = await client.create_order(
                        market_symbol=market_id,
                        side=side_lower,
                        size=amount_float,
                        price=price_float,
                        order_type="ORDER_TYPE_LIMIT",
                    )

                # Parse resp
                raw = resp.to_dict() if hasattr(resp, "to_dict") else str(resp)

                return {"id": str(raw.get("id", "")), "info": raw, "status": "open"}

            except Exception as e:
                logger.error(f"Async create_order failed: {e}")
                raise
            finally:
                await self._cleanup_client(client)

        try:
            return self._run_async(_create())
        except Exception as e:
            raise ExchangeError(f"Lighter create_order error: {e}") from e

    def cancel_order(self, order_id: str, symbol: str = None, params: dict = None) -> bool:
        """Cancel order."""
        if params is None:
            params = {}

        async def _cancel():
            client = SignerClient(**self._get_client())
            try:
                await client.cancel_order(order_index=int(order_id))
                return True
            except Exception as e:
                logger.error(f"Async cancel_order failed: {e}")
                return False
            finally:
                await self._cleanup_client(client)

        return self._run_async(_cancel())

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        """Set leverage (no-op on Lighter)."""
        return True

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[Any]]:
        """Fetch OHLCV candle data."""
        raise NotImplementedError("Lighter fetch_ohlcv not implemented")

    # ===== IExchange Interface — Queries (delegated) =====

    def fetch_balance(self, params: dict = None) -> dict:
        """Fetch account balance in CCXT format."""
        if params is None:
            params = {}
        return lighter_queries.fetch_balance(self, params)

    def fetch_order(self, order_id: str, symbol: str = None, params: dict = None) -> dict:
        """Fetch order details."""
        if params is None:
            params = {}
        return lighter_queries.fetch_order(self, order_id, symbol, params)

    def fetch_positions(self, symbols: list[str] | None = None, params: dict = None) -> list[dict]:
        """Fetch open positions in CCXT format."""
        if params is None:
            params = {}
        return lighter_queries.fetch_positions(self, symbols, params)

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetch all open/pending orders for a symbol."""
        return lighter_queries.fetch_open_orders(self, symbol)

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        return lighter_queries.cancel_all_orders(self, symbol)
