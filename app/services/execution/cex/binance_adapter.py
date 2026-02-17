"""
Binance USDT-M Futures adapter.
Wraps CCXT binanceusdm. Supports paper (testnet) and live (mainnet).
Translates normalized order types to Binance-native params.
"""
import os
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence
from pathlib import Path

import ccxt

from app.core.interfaces import IFuturesExchange

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions (Symbol Normalization)
# ==============================================================================

def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _to_external_symbol(symbol: str) -> str:
    """Normalize to CCXT futures style: BTC/USDT:USDT"""
    s = (symbol or "").strip().upper()
    if not s:
        return s
    if "/" in s and ":" in s:
        return s
    if "/" in s and ":" not in s:
        return f"{s}:USDT"
    if s.endswith("USDT") and "/" not in s:
        base = s[:-4]
        return f"{base}/USDT:USDT"
    return s


# ==============================================================================
# Credential Loading
# ==============================================================================

def _get_credentials(mode: str):
    """Get API credentials based on mode. Paper uses testnet keys only (safety)."""
    if mode == "paper":
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        secret = os.getenv("BINANCE_TESTNET_SECRET_KEY")
        if not api_key or not secret:
            raise RuntimeError(
                "Paper mode requires BINANCE_TESTNET_API_KEY and "
                "BINANCE_TESTNET_SECRET_KEY in .env"
            )
    else:
        api_key = os.getenv("BINANCE_API_KEY")
        secret = os.getenv("BINANCE_SECRET_KEY")
        if not api_key or not secret:
            raise RuntimeError(
                "Live mode requires BINANCE_API_KEY and "
                "BINANCE_SECRET_KEY in .env"
            )
    return api_key, secret


# ==============================================================================
# BinanceAdapter
# ==============================================================================

class BinanceAdapter(IFuturesExchange):
    """
    Binance USDT-M Futures adapter.
    Wraps CCXT binanceusdm. Supports paper (testnet) and live (mainnet).
    Translates normalized order types to Binance-native params.
    """

    def __init__(self, config: dict = None):
        config = config or {}
        mode = config.get("bot", {}).get("mode", "paper")
        api_key, secret = _get_credentials(mode)

        self._exchange = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

        if mode == "paper":
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()
        self._mode = mode
        logger.info(f"BinanceAdapter initialized in {mode.upper()} mode")

    # ------------------------------------------------------------------
    # IExchange: Order Management
    # ------------------------------------------------------------------

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Translate normalized order types to Binance-native."""
        params = params or {}
        ccxt_params = {}

        # reduceOnly
        if params.get("reduceOnly"):
            ccxt_params["reduceOnly"] = True

        # Order type translation
        actual_type = (order_type or "market").lower()

        if actual_type == "stop_market":
            ccxt_type = "STOP_MARKET"
            ccxt_params["stopPrice"] = float(params["stopPrice"])
        elif actual_type == "stop_limit":
            ccxt_type = "STOP"
            ccxt_params["stopPrice"] = float(params["stopPrice"])
        elif actual_type == "trailing_stop":
            ccxt_type = "TRAILING_STOP_MARKET"
            ccxt_params["callbackRate"] = float(params["callbackRate"])
        else:
            ccxt_type = actual_type.upper()  # market → MARKET, limit → LIMIT

        # timeInForce for limit orders
        if ccxt_type == "LIMIT" and "timeInForce" not in ccxt_params:
            ccxt_params["timeInForce"] = params.get("timeInForce", "GTC")

        ext_symbol = _to_external_symbol(symbol)

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
                f"@ {price or 'market'} → id={result.get('id')}"
            )
            return result
        except Exception as e:
            logger.error(f"Order failed: {side} {actual_type} {amount} {symbol}: {e}")
            return None

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order status by ID."""
        ext_symbol = _to_external_symbol(symbol)
        return self._exchange.fetch_order(order_id, ext_symbol)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        ext_symbol = _to_external_symbol(symbol)
        try:
            self._exchange.cancel_order(order_id, ext_symbol)
            return True
        except Exception as e:
            logger.warning(f"Cancel order {order_id} failed: {e}")
            return False

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        ext_symbol = _to_external_symbol(symbol)
        try:
            result = self._exchange.cancel_all_orders(ext_symbol)
            count = len(result) if isinstance(result, list) else 0
            logger.info(f"Cancelled {count} orders for {symbol}")
            return count
        except Exception as e:
            logger.error(f"Cancel all orders for {symbol} failed: {e}")
            return 0

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all open/pending orders for a symbol."""
        ext_symbol = _to_external_symbol(symbol) if symbol else None
        return self._exchange.fetch_open_orders(ext_symbol)

    # ------------------------------------------------------------------
    # IFuturesExchange: Position & Balance
    # ------------------------------------------------------------------

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        """Set leverage for a symbol."""
        ext_symbol = _to_external_symbol(symbol)
        try:
            self._exchange.set_leverage(leverage, ext_symbol)
            logger.info(f"Leverage set to {leverage}x for {symbol}")
            return True
        except Exception as e:
            logger.warning(f"Set leverage failed for {symbol}: {e}")
            return False

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """Fetch open positions, filtering out zero-size."""
        ext_symbols = [_to_external_symbol(s) for s in symbols] if symbols else None
        positions = self._exchange.fetch_positions(ext_symbols)
        return [p for p in positions if abs(float(p.get("contracts", 0))) > 0]

    def fetch_balance(self, params: Dict = {}) -> Dict:
        """Fetch balance in CCXT format."""
        return self._exchange.fetch_balance(params)

    # ------------------------------------------------------------------
    # IExchange: Market Data
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 500
    ) -> Sequence[Sequence[Any]]:
        """Fetch historical OHLCV candles."""
        ext_symbol = _to_external_symbol(symbol)
        return self._exchange.fetch_ohlcv(ext_symbol, timeframe, limit=limit)

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def get_precision_info(self, symbol: str):
        """Get price and quantity precision from loaded markets."""
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

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker data."""
        ext_symbol = _to_external_symbol(symbol)
        return self._exchange.fetch_ticker(ext_symbol)

    def check_position_active(self, symbol: str) -> bool:
        """Check if a specific symbol has an open position."""
        positions = self.fetch_positions([symbol])
        return len(positions) > 0
