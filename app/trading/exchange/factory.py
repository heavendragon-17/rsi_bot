"""
Exchange Factory - Environment Mode Separation
===============================================
Implements four distinct modes:
  - mock:  MockExchange (in-memory, no network calls, historical data)
  - sim:   SimExchange (local order simulation against live Binance aggTrade data)
  - paper: Real exchange connected to Testnet
  - live:  Real exchange connected to Mainnet

Credentials are loaded from environment variables using naming convention:
  {EXCHANGE}_TESTNET_API_KEY / {EXCHANGE}_TESTNET_SECRET  (paper mode)
  {EXCHANGE}_API_KEY / {EXCHANGE}_SECRET                   (live mode)

Custom DEX Adapters:
  To add a new DEX, create `app/services/execution/dex/{name}_adapter.py`
  with a class named `{Name}Adapter` (e.g., `lighter` -> `LighterAdapter`).
  The factory will auto-discover it without any code changes here.
"""
from __future__ import annotations

import os
import logging
import importlib
from typing import Any, Dict

from app.core.interfaces import IExchange

logger = logging.getLogger(__name__)


# Mapping of config exchange names to CCXT class names and env var prefixes
EXCHANGE_CONFIG = {
    'binanceusdm': {
        'ccxt_class': 'binanceusdm',
        'env_prefix': 'BINANCE',
    },
    'binance': {
        'ccxt_class': 'binanceusdm',
        'env_prefix': 'BINANCE',
    },
    # Add more CCXT exchanges here as needed
}


def _get_credentials(env_prefix: str, mode: str) -> tuple:
    """
    Load credentials from environment variables.
    
    Paper mode: {PREFIX}_TESTNET_API_KEY, {PREFIX}_TESTNET_SECRET_KEY
    Live mode:  {PREFIX}_API_KEY, {PREFIX}_SECRET_KEY
    """
    if mode == "paper":
        api_key = os.getenv(f"{env_prefix}_TESTNET_API_KEY")
        secret = os.getenv(f"{env_prefix}_TESTNET_SECRET_KEY")
    else:  # live
        api_key = os.getenv(f"{env_prefix}_API_KEY")
        secret = os.getenv(f"{env_prefix}_SECRET_KEY")
    
    return api_key, secret


def _load_custom_adapter(exchange_name: str, config: Dict[str, Any]) -> IExchange:
    """
    Dynamically load a custom DEX adapter.
    
    Convention:
      - Module: app.services.execution.dex.{name}_adapter
      - Class:  {Name}Adapter (first letter capitalized)
    
    Example: 'lighter' -> app.services.execution.dex.lighter_adapter.LighterAdapter
    """
    module_name = f"app.services.execution.dex.{exchange_name}_adapter"
    class_name = f"{exchange_name.capitalize()}Adapter"
    
    try:
        module = importlib.import_module(module_name)
        adapter_class = getattr(module, class_name)
        return adapter_class(config)
    except ImportError as e:
        raise ValueError(
            f"Could not load adapter for '{exchange_name}'. "
            f"Module '{module_name}' not found or import failed: {e}"
        )
    except AttributeError:
        raise ValueError(
            f"Module '{module_name}' found, but class '{class_name}' not defined."
        )


def create_exchange(config: Dict[str, Any], notification_service=None) -> IExchange:
    """
    Create an exchange instance based on the bot mode.

    Args:
        config: Configuration dict with structure:
            bot:
              mode: "mock" | "sim" | "paper" | "live"
            exchange:
              name: "binanceusdm" | "lighter" | etc.
        notification_service: Optional NotificationService injected into SimExchange.

    Returns:
        IExchange instance
    """
    mode = config.get("bot", {}).get("mode", "mock").lower()
    exchange_name = config.get("exchange", {}).get("name", "binanceusdm").lower()

    # ===== 1. Sim Mode =====
    if mode == "sim":
        from app.trading.exchange.sim.sim_exchange import SimExchange
        sim_cfg = config.get("sim", config.get("paper_sim", {}))
        initial_balance = sim_cfg.get("initial_balance", 10000)
        logger.info(f"Factory: Created SimExchange (sim mode, balance={initial_balance})")
        exc = SimExchange(config, notification_service=notification_service)
        if notification_service and hasattr(notification_service, "attach_exchange"):
            notification_service.attach_exchange(exc)
            notification_service.start_command_polling()
        return exc

    if mode == "mock":
        from app.backtest.mock_exchange import MockExchange
        backtest_cfg = config.get("backtest", {})
        initial_balance = backtest_cfg.get("initial_balance", 10000.0)
        leverage = config.get("risk", {}).get("leverage", 1)
        logger.info(f"Factory: Created MockExchange (balance={initial_balance}, leverage={leverage})")
        exc = MockExchange(initial_balance=initial_balance, leverage=leverage)
        if notification_service and hasattr(notification_service, "attach_exchange"):
            notification_service.attach_exchange(exc)
            notification_service.start_command_polling()
        return exc
    
    # ===== 2. CCXT Exchanges (Binance, etc.) =====
    # Return BinanceAdapter (wraps CCXT, implements IExchange)
    # instead of raw CCXT — ensures normalized order type translation
    if exchange_name in EXCHANGE_CONFIG:
        from app.trading.exchange.binance_adapter import BinanceAdapter

        if mode == "live":
            logger.warning("=" * 60)
            logger.warning("WARNING: RUNNING IN LIVE TRADING MODE - REAL MONEY AT RISK")
            logger.warning("=" * 60)

        adapter = BinanceAdapter(config)
        logger.info(f"Factory: Created BinanceAdapter in {mode.upper()} mode.")
        if notification_service and hasattr(notification_service, "attach_exchange"):
            notification_service.attach_exchange(adapter)
            notification_service.start_command_polling()
        return adapter
    
    # ===== 3. Custom DEX Adapters (Lighter, Hyperliquid, etc.) =====
    adapter = _load_custom_adapter(exchange_name, config)

    if mode == "paper":
        logger.info(f"Factory: Created {exchange_name.capitalize()}Adapter in PAPER (Testnet) mode.")
    else:
        logger.warning("=" * 60)
        logger.warning(f"WARNING: RUNNING {exchange_name.upper()} IN LIVE MODE - REAL MONEY AT RISK")
        logger.warning("=" * 60)
    
    if notification_service and hasattr(notification_service, "attach_exchange"):
        notification_service.attach_exchange(adapter)
        notification_service.start_command_polling()

    return adapter
