"""
Lighter DEX Adapter
===================
Adapter for Lighter exchange implementing IFuturesExchange interface.
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

import os
import logging
import asyncio
from typing import Any, Dict, List, Optional
from decimal import Decimal

import ccxt

from app.core.interfaces import IFuturesExchange

logger = logging.getLogger(__name__)

# Lighter SDK imports
try:
    import lighter
    from lighter import SignerClient
    from lighter.api import AccountApi, OrderApi
    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK import failed. Run: pip install git+https://github.com/elliottech/lighter-python.git")


# Base URLs
LIGHTER_TESTNET_URL = "https://testnet.zklighter.elliot.ai"
LIGHTER_MAINNET_URL = "https://mainnet.zklighter.elliot.ai"


class LighterAdapter(IFuturesExchange):
    """
    Lighter exchange adapter implementing IFuturesExchange.
    
    Wraps the ASYNC Lighter Python SDK to provide SYNCHRONOUS CCXT-compatible interface.
    Uses asyncio.run() for each call to bridge the gap.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the Lighter adapter.
        
        Args:
            config: Bot configuration dict
        """
        if not LIGHTER_SDK_AVAILABLE:
            raise RuntimeError(
                "Lighter SDK not installed. "
                "Run: pip install git+https://github.com/elliottech/lighter-python.git"
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
            raise ValueError("LIGHTER_L1_ADDRESS is required in .env (your wallet public address)")
        
        # Determine mode (paper = testnet, live = mainnet)
        mode = config.get("bot", {}).get("mode", "paper").lower()
        if mode == "paper" or mode == "mock":
            self.base_url = os.getenv("LIGHTER_BASE_URL", LIGHTER_TESTNET_URL)
        else:
            self.base_url = os.getenv("LIGHTER_BASE_URL", LIGHTER_MAINNET_URL)
        
        logger.info(f"LighterAdapter: Connecting to {self.base_url} with Account Index {self.account_index}")
        
        # Symbol cache
        self._symbol_map: Dict[str, str] = {}

    def _sanitize_log_message(self, message: Any) -> str:
        """Redact sensitive info from log messages."""
        msg = str(message)
        if self.secret_key and self.secret_key in msg:
             msg = msg.replace(self.secret_key, "[REDACTED_SECRET]")
        return msg

    def _get_client(self):
        """
        Create and return a NEW SignerClient instance.
        Since we are bridging async->sync with asyncio.run(), we generally create a new client/session 
        wrapped in the coroutine to avoid event loop attachment issues, OR we try to manage a persistent loop.
        
        For simplicity and robustness in this sync codebase, we initialize inside the async wrapper.
        """
        # This helper returns the kwargs needed to init client
        return {
            "url": self.base_url,
            "api_private_keys": {self.api_key_index: self.secret_key},
            "account_index": self.account_index
        }

    async def _cleanup_client(self, client):
        if client and hasattr(client, 'api_client'):
             await client.api_client.close()

    # ===== Symbol Mapping =====
    
    def _to_lighter_symbol(self, ccxt_symbol: str) -> int:
        """
        Convert CCXT symbol to Lighter Market Index.
        Lighter SignerClient create_order expects market_symbol as int (market_id) or similar?
        Docs say market_symbol. 
        SDK implementation: create_order(market_symbol, ...)
        But Lighter usually uses market IDs (integers).
        We might need to map "BTC/USDT" -> 1.
        
        TODO: Need to fetch market info to map symbols dynamically.
        For now, defaulting to hardcoded or assuming 1 for BTC-PERP if testnet.
        """
        # TEMP: Hardcoded mapping for Testnet
        if "BTC" in ccxt_symbol:
            return 1 # Example ID for BTC-PERP
        if "ETH" in ccxt_symbol:
            return 2 # Example ID for ETH-PERP
            
        logger.warning(f"Unknown symbol {ccxt_symbol}, defaulting to 1")
        return 1
    
    def _to_ccxt_symbol(self, market_id: int) -> str:
        """
        Convert Lighter market ID to CCXT format.
        """
        # TEMP: Hardcoded reverse mapping
        if market_id == 1:
            return "BTC/USDT"
        if market_id == 2:
            return "ETH/USDT"
        return f"UNKNOWN-{market_id}"
    
    # ===== Helper to run async code =====
    
    def _run_async(self, coro):
        """Run coroutine in a new event loop."""
        return asyncio.run(coro)

    # ===== IFuturesExchange Interface =====
    
    def fetch_balance(self, params: Dict = {}) -> Dict:
        """
        Fetch account balance in CCXT format.
        
        Uses accounts_by_l1_address to get account info including collateral.
        """
        async def _fetch():
            client = SignerClient(**self._get_client())
            try:
                account_api = AccountApi(client.api_client)
                
                # Query account by L1 address
                resp = await account_api.accounts_by_l1_address(self.l1_address)
                
                # Parse response
                raw = resp.to_dict() if hasattr(resp, 'to_dict') else {}
                
                # Find our sub-account by index
                sub_accounts = raw.get('sub_accounts', [])
                account_data = None
                for acc in sub_accounts:
                    if acc.get('index') == self.account_index:
                        account_data = acc
                        break
                
                if not account_data:
                    logger.warning(f"Account index {self.account_index} not found in response")
                    return {
                        'info': raw,
                        'free': {'USDT': 0.0},
                        'used': {'USDT': 0.0},
                        'total': {'USDT': 0.0}
                    }
                
                # Parse balance from collateral field
                collateral_str = account_data.get('collateral', '0')
                try:
                    total_balance = float(collateral_str)
                except (ValueError, TypeError):
                    total_balance = 0.0
                
                # available_balance if present
                available_str = account_data.get('available_balance', '')
                try:
                    free_balance = float(available_str) if available_str else total_balance
                except (ValueError, TypeError):
                    free_balance = total_balance
                
                used_balance = total_balance - free_balance
                
                return {
                    'info': account_data,
                    'free': {'USDT': free_balance, 'USDC': free_balance},
                    'used': {'USDT': used_balance, 'USDC': used_balance},
                    'total': {'USDT': total_balance, 'USDC': total_balance}
                }
                
            except Exception as e:
                sanitized_msg = self._sanitize_log_message(e)
                logger.error(f"fetch_balance failed: {sanitized_msg}")
                raise ccxt.ExchangeError(f"Lighter fetch_balance error: {sanitized_msg}")
            finally:
                await self._cleanup_client(client)
                
        return self._run_async(_fetch())

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Create an order."""
        async def _create():
            client = SignerClient(**self._get_client())
            try:
                params_local = params or {}
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
                        # extra attributes?
                    )
                else: # limit
                    if not price_float:
                        raise ValueError("Price required for limit order")
                    resp = await client.create_order(
                        market_symbol=market_id,
                        side=side_lower,
                        size=amount_float,
                        price=price_float,
                        order_type="ORDER_TYPE_LIMIT"
                    )
                
                # Parse resp
                raw = resp.to_dict() if hasattr(resp, 'to_dict') else str(resp)
                
                return {
                    'id': str(raw.get('id', '')),
                    'info': raw,
                    'status': 'open' 
                }
                
            except Exception as e:
                logger.error(f"Async create_order failed: {self._sanitize_log_message(e)}")
                raise
            finally:
                await self._cleanup_client(client)
        
        try:
            return self._run_async(_create())
        except Exception as e:
             # Map exceptions
             raise ccxt.ExchangeError(f"Lighter create_order error: {self._sanitize_log_message(e)}")

    def cancel_order(self, order_id: str, symbol: str = None, params: Dict = {}) -> bool:
        """Cancel order."""
        async def _cancel():
            client = SignerClient(**self._get_client())
            try:
                await client.cancel_order(
                    order_index=int(order_id)
                )
                return True
            except Exception as e:
                logger.error(f"Async cancel_order failed: {self._sanitize_log_message(e)}")
                return False
            finally:
                await self._cleanup_client(client)
                
        return self._run_async(_cancel())

    def fetch_order(self, order_id: str, symbol: str = None, params: Dict = {}) -> Dict:
        """
        Fetch order details.
        
        Note: Lighter SDK may require querying order history or active orders.
        """
        async def _fetch():
            client = SignerClient(**self._get_client())
            try:
                order_api = OrderApi(client.api_client)
                
                # Try to get order by index
                # SDK might have get_order or similar
                if hasattr(order_api, 'get_order'):
                    resp = await order_api.get_order(index=int(order_id))
                    raw = resp.to_dict() if hasattr(resp, 'to_dict') else {}
                    return {
                        'id': order_id,
                        'status': raw.get('status', 'unknown'),
                        'info': raw
                    }
                else:
                    # Fallback - return minimal info
                    logger.warning("fetch_order: get_order method not available in SDK")
                    return {'id': order_id, 'status': 'unknown', 'info': {}}
                    
            except Exception as e:
                logger.error(f"fetch_order failed: {self._sanitize_log_message(e)}")
                return {'id': order_id, 'status': 'error', 'info': {'error': self._sanitize_log_message(e)}}
            finally:
                await self._cleanup_client(client)
                
        return self._run_async(_fetch())

    def fetch_positions(self, symbols: Optional[List[str]] = None, params: Dict = {}) -> List[Dict]:
        """
        Fetch open positions in CCXT format.
        
        Uses account data from accounts_by_l1_address which includes position info.
        """
        async def _fetch():
            client = SignerClient(**self._get_client())
            try:
                account_api = AccountApi(client.api_client)
                
                # Query account by L1 address
                resp = await account_api.accounts_by_l1_address(self.l1_address)
                raw = resp.to_dict() if hasattr(resp, 'to_dict') else {}
                
                # Find our sub-account
                sub_accounts = raw.get('sub_accounts', [])
                account_data = None
                for acc in sub_accounts:
                    if acc.get('index') == self.account_index:
                        account_data = acc
                        break
                
                if not account_data:
                    return []
                
                # Extract positions if present
                # Lighter might store positions in account_data['positions'] or similar
                # Based on SDK exploration, we need to check actual field names
                positions = []
                raw_positions = account_data.get('positions', [])
                
                for pos in raw_positions:
                    size = float(pos.get('size', 0))
                    if size == 0:
                        continue
                    
                    market_id = pos.get('market_index', pos.get('market', 0))
                    symbol = self._to_ccxt_symbol(market_id)
                    
                    # Filter by requested symbols
                    if symbols and symbol not in symbols:
                        continue
                    
                    positions.append({
                        'symbol': symbol,
                        'side': 'long' if size > 0 else 'short',
                        'contracts': abs(size),
                        'contractSize': 1.0,
                        'entryPrice': float(pos.get('entry_price', 0)),
                        'markPrice': float(pos.get('mark_price', 0)),
                        'unrealizedPnl': float(pos.get('unrealized_pnl', 0)),
                        'liquidationPrice': float(pos.get('liquidation_price', 0)),
                        'leverage': float(pos.get('leverage', 1)),
                        'info': pos,
                    })
                
                return positions
                
            except Exception as e:
                logger.error(f"fetch_positions failed: {self._sanitize_log_message(e)}")
                return []
            finally:
                await self._cleanup_client(client)
                
        return self._run_async(_fetch())

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        return True

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List[Any]]:
         raise NotImplementedError("Lighter fetch_ohlcv not implemented")
