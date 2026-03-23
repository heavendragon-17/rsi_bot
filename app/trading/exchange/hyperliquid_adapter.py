"""
Hyperliquid DEX adapter.
Wraps CCXT hyperliquid. Supports paper (testnet) and live (mainnet).
Translates normalized order types to Hyperliquid-native params.

Required env vars:
  HYPERLIQUID_WALLET_ADDRESS - Public wallet address
  HYPERLIQUID_PRIVATE_KEY - Private key
"""

import os
import threading
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import ccxt
import structlog

from app.core.exceptions import (
    ConnectionError,
    ExchangeError,
    InsufficientFundsError,
    OrderNotFoundError,
    OrderRejectedError,
    PositionError,
    RateLimitError,
)
from app.core.interfaces import IExchange

logger = structlog.get_logger()


# Symbol normalization
def _to_external_symbol(symbol: str) -> str:
    """Normalize to CCXT hyperliquid style (assumes USDC base): e.g. BTC/USDC:USDC"""
    s = (symbol or "").strip().upper()
    if not s:
        return s

    # Already formatted properly
    if "/" in s and ":" in s:
        return s

    # Example format: BTC/USDT -> BTC/USDC:USDC
    if "/" in s and ":" not in s:
        base = s.split("/")[0]
        return f"{base}/USDC:USDC"

    # Example format: BTCUSDT -> BTC/USDC:USDC
    if s.endswith("USDT"):
        base = s[:-4]
        return f"{base}/USDC:USDC"
    elif s.endswith("USDC"):
        base = s[:-4]
        return f"{base}/USDC:USDC"

    # Example format -> BTC -> BTC/USDC:USDC
    return f"{s}/USDC:USDC"


def _get_credentials():
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
    if not wallet or not private_key:
        raise RuntimeError(
            "Hyperliquid integration requires HYPERLIQUID_WALLET_ADDRESS and " "HYPERLIQUID_PRIVATE_KEY in .env"
        )
    return wallet, private_key


class HyperliquidAdapter(IExchange):
    """
    Hyperliquid Adapter via CCXT.
    """

    def __init__(self, config: dict = None):
        self._lock = threading.Lock()
        config = config or {}

        mode = config.get("bot", {}).get("mode", "paper")
        wallet, private_key = _get_credentials()

        self._exchange = ccxt.hyperliquid(
            {
                "walletAddress": wallet,
                "privateKey": private_key,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
            }
        )

        if mode == "paper":
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()
        self._mode = mode
        logger.info(f"HyperliquidAdapter initialized in {mode.upper()} mode")

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
        ccxt_params = {}

        # reduceOnly
        if params.get("reduceOnly"):
            ccxt_params["reduceOnly"] = True

        actual_type = (order_type or "market").lower()

        if actual_type == "trailing_stop":
            raise OrderRejectedError("Trailing stops are not supported by Hyperliquid/CCXT.")
        elif actual_type == "stop_market":
            ccxt_type = "STOP"
            ccxt_params["stopPrice"] = float(params["stopPrice"])
        elif actual_type == "stop_limit":
            ccxt_type = "STOP"
            ccxt_params["stopPrice"] = float(params["stopPrice"])
        else:
            ccxt_type = actual_type.upper()

        if ccxt_type == "LIMIT" and "timeInForce" not in ccxt_params:
            ccxt_params["timeInForce"] = params.get("timeInForce", "GTC")

        ext_symbol = _to_external_symbol(symbol)

        with self._lock:
            try:
                result = self._exchange.create_order(
                    symbol=ext_symbol,
                    type=ccxt_type,
                    side=side.upper(),
                    amount=float(amount),
                    price=float(price) if price else None,
                    params=ccxt_params,
                )
                logger.info(
                    f"Order placed: {side} {actual_type} {amount} {symbol} "
                    f"@ {price or 'market'} -> id={result.get('id')}"
                )
                return result
            except ccxt.InsufficientFunds as e:
                raise InsufficientFundsError(str(e), original=e) from e
            except ccxt.InvalidOrder as e:
                raise OrderRejectedError(str(e), original=e) from e
            except ccxt.OrderNotFound as e:
                raise OrderNotFoundError(str(e), original=e) from e
            except ccxt.RateLimitExceeded as e:
                raise RateLimitError(str(e), original=e) from e
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        ext_symbol = _to_external_symbol(symbol)
        with self._lock:
            try:
                return self._exchange.fetch_order(order_id, ext_symbol)
            except ccxt.OrderNotFound as e:
                raise OrderNotFoundError(str(e), original=e) from e
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        ext_symbol = _to_external_symbol(symbol)
        with self._lock:
            try:
                self._exchange.cancel_order(order_id, ext_symbol)
                return True
            except ccxt.OrderNotFound as e:
                raise OrderNotFoundError(str(e), original=e) from e
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def cancel_all_orders(self, symbol: str) -> int:
        ext_symbol = _to_external_symbol(symbol)
        with self._lock:
            try:
                result = self._exchange.cancel_all_orders(ext_symbol)
                count = len(result) if isinstance(result, list) else 0
                logger.info(f"Cancelled {count} orders for {symbol}")
                return count
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        ext_symbol = _to_external_symbol(symbol) if symbol else None
        with self._lock:
            try:
                open_orders = self._exchange.fetch_open_orders(ext_symbol)
                return open_orders if open_orders is not None else []
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        ext_symbol = _to_external_symbol(symbol)
        with self._lock:
            try:
                self._exchange.set_leverage(leverage, ext_symbol)
                logger.info(f"Leverage set to {leverage}x for {symbol}")
                return True
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise PositionError(str(e), original=e) from e

    def fetch_positions(self, symbols: list[str] | None = None) -> list[dict]:
        ext_symbols = [_to_external_symbol(s) for s in symbols] if symbols else None
        with self._lock:
            try:
                positions = self._exchange.fetch_positions(ext_symbols)
                return [p for p in positions if abs(float(p.get("contracts", 0))) > 0]
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def fetch_balance(self, params: dict | None = None) -> dict:
        with self._lock:
            try:
                return self._exchange.fetch_balance(params)
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> Sequence[Sequence[Any]]:
        ext_symbol = _to_external_symbol(symbol)
        with self._lock:
            try:
                return self._exchange.fetch_ohlcv(ext_symbol, timeframe, limit=limit)
            except ccxt.NetworkError as e:
                raise ConnectionError(str(e), original=e) from e
            except ccxt.BaseError as e:
                raise ExchangeError(str(e), original=e) from e

    def get_precision_info(self, symbol: str):
        ext_symbol = _to_external_symbol(symbol)
        try:
            if not self._exchange.markets:
                self._exchange.load_markets()
            market = self._exchange.market(ext_symbol)
            price_prec = int(market["precision"]["price"])
            qty_prec = int(market["precision"]["amount"])
            return price_prec, qty_prec
        except Exception as e:
            logger.warning(f"Precision fetch error for {symbol}: {e}")
            return 2, 3

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        ext_symbol = _to_external_symbol(symbol)
        return self._exchange.fetch_ticker(ext_symbol)

    def check_position_active(self, symbol: str) -> bool:
        positions = self.fetch_positions([symbol])
        return len(positions) > 0
