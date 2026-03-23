"""
Lighter DEX Query Functions
============================
Read-only query methods extracted from LighterAdapter.

Each function takes an adapter instance as the first parameter,
using the adapter's _run_async, _get_client, _cleanup_client,
and symbol mapping helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.core.exceptions import ExchangeError

if TYPE_CHECKING:
    from app.trading.exchange.lighter_adapter import LighterAdapter

logger = structlog.get_logger(__name__)

# Lighter SDK imports (guarded)
try:
    from lighter import SignerClient
    from lighter.api import AccountApi, OrderApi

    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False


def _find_sub_account(raw: dict, account_index: int) -> dict | None:
    """Find sub-account by index in API response."""
    sub_accounts = raw.get("sub_accounts", [])
    for acc in sub_accounts:
        if acc.get("index") == account_index:
            return acc
    return None


def fetch_balance(adapter: LighterAdapter, params: dict = None) -> dict:
    """
    Fetch account balance in CCXT format.

    Uses accounts_by_l1_address to get account info including collateral.
    """
    if params is None:
        params = {}

    async def _fetch():
        client = SignerClient(**adapter._get_client())
        try:
            account_api = AccountApi(client.api_client)

            # Query account by L1 address
            resp = await account_api.accounts_by_l1_address(adapter.l1_address)

            # Parse response
            raw = resp.to_dict() if hasattr(resp, "to_dict") else {}

            account_data = _find_sub_account(raw, adapter.account_index)

            if not account_data:
                logger.warning(f"Account index {adapter.account_index} not found in response")
                return {"info": raw, "free": {"USDT": 0.0}, "used": {"USDT": 0.0}, "total": {"USDT": 0.0}}

            # Parse balance from collateral field
            collateral_str = account_data.get("collateral", "0")
            try:
                total_balance = float(collateral_str)
            except (ValueError, TypeError):
                total_balance = 0.0

            # available_balance if present
            available_str = account_data.get("available_balance", "")
            try:
                free_balance = float(available_str) if available_str else total_balance
            except (ValueError, TypeError):
                free_balance = total_balance

            used_balance = total_balance - free_balance

            return {
                "info": account_data,
                "free": {"USDT": free_balance, "USDC": free_balance},
                "used": {"USDT": used_balance, "USDC": used_balance},
                "total": {"USDT": total_balance, "USDC": total_balance},
            }

        except Exception as e:
            logger.error(f"fetch_balance failed: {e}")
            raise ExchangeError(f"Lighter fetch_balance error: {e}") from e
        finally:
            await adapter._cleanup_client(client)

    return adapter._run_async(_fetch())


def fetch_order(
    adapter: LighterAdapter,
    order_id: str,
    symbol: str = None,
    params: dict = None,
) -> dict:
    """
    Fetch order details.

    Note: Lighter SDK may require querying order history or active orders.
    """
    if params is None:
        params = {}

    async def _fetch():
        client = SignerClient(**adapter._get_client())
        try:
            order_api = OrderApi(client.api_client)

            # Try to get order by index
            if hasattr(order_api, "get_order"):
                resp = await order_api.get_order(index=int(order_id))
                raw = resp.to_dict() if hasattr(resp, "to_dict") else {}
                return {"id": order_id, "status": raw.get("status", "unknown"), "info": raw}
            else:
                # Fallback - return minimal info
                logger.warning("fetch_order: get_order method not available in SDK")
                return {"id": order_id, "status": "unknown", "info": {}}

        except Exception as e:
            logger.error(f"fetch_order failed: {e}")
            return {
                "id": order_id,
                "status": "error",
                "info": {"error": str(e)},
            }
        finally:
            await adapter._cleanup_client(client)

    return adapter._run_async(_fetch())


def fetch_positions(
    adapter: LighterAdapter,
    symbols: list[str] | None = None,
    params: dict = None,
) -> list[dict]:
    """
    Fetch open positions in CCXT format.

    Uses account data from accounts_by_l1_address which includes position info.
    """
    if params is None:
        params = {}

    async def _fetch():
        client = SignerClient(**adapter._get_client())
        try:
            account_api = AccountApi(client.api_client)

            # Query account by L1 address
            resp = await account_api.accounts_by_l1_address(adapter.l1_address)
            raw = resp.to_dict() if hasattr(resp, "to_dict") else {}

            account_data = _find_sub_account(raw, adapter.account_index)

            if not account_data:
                return []

            positions = []
            raw_positions = account_data.get("positions", [])

            for pos in raw_positions:
                size = float(pos.get("size", 0))
                if size == 0:
                    continue

                market_id = pos.get("market_index", pos.get("market", 0))
                symbol = adapter._to_ccxt_symbol(market_id)

                # Filter by requested symbols
                if symbols and symbol not in symbols:
                    continue

                positions.append(
                    {
                        "symbol": symbol,
                        "side": "long" if size > 0 else "short",
                        "contracts": abs(size),
                        "contractSize": 1.0,
                        "entryPrice": float(pos.get("entry_price", 0)),
                        "markPrice": float(pos.get("mark_price", 0)),
                        "unrealizedPnl": float(pos.get("unrealized_pnl", 0)),
                        "liquidationPrice": float(pos.get("liquidation_price", 0)),
                        "leverage": float(pos.get("leverage", 1)),
                        "info": pos,
                    }
                )

            return positions

        except Exception as e:
            logger.error(f"fetch_positions failed: {e}")
            return []
        finally:
            await adapter._cleanup_client(client)

    return adapter._run_async(_fetch())


def fetch_open_orders(
    adapter: LighterAdapter,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch all open/pending orders for a symbol.

    Uses the OrderApi to query active orders for the account.
    """

    async def _fetch():
        client = SignerClient(**adapter._get_client())
        try:
            order_api = OrderApi(client.api_client)

            if not hasattr(order_api, "get_active_orders"):
                logger.warning("fetch_open_orders: get_active_orders not available")
                return []

            resp = await order_api.get_active_orders(account_index=adapter.account_index)
            raw = resp.to_dict() if hasattr(resp, "to_dict") else {}
            raw_orders = raw.get("orders", [])

            orders = []
            for order in raw_orders:
                market_id = order.get("market_index", 0)
                order_symbol = adapter._to_ccxt_symbol(market_id)

                if symbol and order_symbol != symbol:
                    continue

                orders.append(
                    {
                        "id": str(order.get("index", "")),
                        "symbol": order_symbol,
                        "side": order.get("side", "unknown"),
                        "price": float(order.get("price", 0)),
                        "amount": float(order.get("size", 0)),
                        "status": "open",
                        "info": order,
                    }
                )

            return orders

        except Exception as e:
            logger.error(f"fetch_open_orders failed: {e}")
            return []
        finally:
            await adapter._cleanup_client(client)

    return adapter._run_async(_fetch())


def cancel_all_orders(adapter: LighterAdapter, symbol: str) -> int:
    """
    Cancel all open orders for a symbol. Returns count cancelled.

    Fetches open orders first, then cancels each one.
    """
    open_orders = fetch_open_orders(adapter, symbol=symbol)

    cancelled = 0
    for order in open_orders:
        order_id = order.get("id")
        if order_id:
            success = adapter.cancel_order(order_id, symbol=symbol)
            if success:
                cancelled += 1

    return cancelled
