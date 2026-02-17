"""
Exchange Factory - Environment Mode Separation
===============================================
Implements three distinct modes:
  - mock:  MockExchange (in-memory, no network calls)
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

from app.core.interfaces import IFuturesExchange
from app.backtest.mock_exchange import MockExchange

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


def _load_custom_adapter(exchange_name: str, config: Dict[str, Any]) -> IFuturesExchange:
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


def create_exchange(config: Dict[str, Any]) -> IFuturesExchange:
    """
    Create an exchange instance based on the bot mode.
    
    Args:
        config: Configuration dict with structure:
            bot:
              mode: "mock" | "paper" | "live"
            exchange:
              name: "binanceusdm" | "lighter" | etc.
    
    Returns:
        IFuturesExchange instance
    """
    mode = config.get("bot", {}).get("mode", "mock").lower()
    exchange_name = config.get("exchange", {}).get("name", "binanceusdm").lower()
    
    # ===== 1. Mock Mode =====
    if mode == "mock":
        backtest_cfg = config.get("backtest", {})
        initial_balance = backtest_cfg.get("initial_balance", 10000.0)
        leverage = config.get("risk", {}).get("leverage", 1)
        logger.info(f"Factory: Created MockExchange (balance={initial_balance}, leverage={leverage})")
        return MockExchange(initial_balance=initial_balance, leverage=leverage)
    
    # ===== 2. CCXT Exchanges (Binance, etc.) =====
    # Return BinanceAdapter (wraps CCXT, implements IFuturesExchange)
    # instead of raw CCXT — ensures normalized order type translation
    if exchange_name in EXCHANGE_CONFIG:
        from app.services.execution.cex.binance_adapter import BinanceAdapter

        if mode == "live":
            logger.warning("=" * 60)
            logger.warning("WARNING: RUNNING IN LIVE TRADING MODE - REAL MONEY AT RISK")
            logger.warning("=" * 60)

        adapter = BinanceAdapter(config)
        logger.info(f"Factory: Created BinanceAdapter in {mode.upper()} mode.")
        return adapter
    
    # ===== 3. Custom DEX Adapters (Lighter, Hyperliquid, etc.) =====
    adapter = _load_custom_adapter(exchange_name, config)
    
    if mode == "paper":
        logger.info(f"Factory: Created {exchange_name.capitalize()}Adapter in PAPER (Testnet) mode.")
    else:
        logger.warning("=" * 60)
        logger.warning(f"WARNING: RUNNING {exchange_name.upper()} IN LIVE MODE - REAL MONEY AT RISK")
        logger.warning("=" * 60)
    
    return adapter
