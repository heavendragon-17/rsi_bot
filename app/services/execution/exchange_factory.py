"""
Exchange Factory
================
Creates exchange instances based on config.

Config structure:
  exchange:
    provider: 'binance'    # binance, hyperliquid
    mode: 'mock'           # mock, paper, live
"""
from __future__ import annotations

from typing import Any, Dict

from app.core.interfaces import IFuturesExchange


def create_exchange(config: Dict[str, Any]) -> IFuturesExchange:
    """
    Create exchange based on config.
    
    Supports:
    - mock: MockExchange for backtesting
    - paper: Testnet/paper trading
    - live: Real trading
    """
    exchange_cfg = config.get("exchange", {})
    provider = exchange_cfg.get("provider", "binance").lower()
    mode = exchange_cfg.get("mode", "mock").lower()
    
    # Backward compatibility: check bot.mode if exchange.mode not set
    # Note: old bot.mode='paper' is now treated as 'mock' (for backtest)
    if "mode" not in exchange_cfg:
        bot_cfg = config.get("bot", {})
        old_mode = bot_cfg.get("mode", "mock").lower()
        # Map old 'paper' to 'mock' for backtest compatibility
        mode = "mock" if old_mode == "paper" else old_mode
    
    # Mock mode (backtesting)
    if mode == "mock":
        from app.backtest.mock_exchange import MockExchange
        backtest_cfg = config.get("backtest", {})
        initial_balance = backtest_cfg.get("initial_balance", 10000.0)
        leverage = config.get("risk", {}).get("leverage", 1)
        fee_config = backtest_cfg.get("fees", {})
        return MockExchange(
            initial_balance=initial_balance,
            leverage=leverage,
            fee_config=fee_config
        )
    
    # Binance
    if provider == "binance":
        from app.services.execution.cex.binance_adapter import BinanceAdapter
        if mode == "paper":
            return BinanceAdapter(config, testnet=True)
        elif mode == "live":
            return BinanceAdapter(config, testnet=False)
    
    # Hyperliquid
    if provider == "hyperliquid":
        from app.services.execution.hyperliquid_adapter import HyperliquidExchange
        return HyperliquidExchange(config)
    
    raise ValueError(f"Unknown exchange provider/mode: {provider}/{mode}")

