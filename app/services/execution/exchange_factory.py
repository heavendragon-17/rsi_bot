from __future__ import annotations

from typing import Any, Dict

from app.core.interfaces import IFuturesExchange
from app.backtest.mock_exchange import MockExchange
from app.services.execution.cex.binance_adapter import BinanceAdapter
from app.services.execution.hyperliquid_adapter import HyperliquidAdapter


def create_exchange(config: Dict[str, Any]) -> IFuturesExchange:
    bot_cfg = config.get("bot", {})
    mode = (bot_cfg.get("mode") or "paper").lower()
    provider = (bot_cfg.get("exchange") or "binance").lower()

    if mode == "paper" or mode == "mock":
        # Check if running from backtest (often config doesn't have mode='mock' explicitly but is run via backtest script)
        # Assuming MockExchange is desired for paper/backtest unless specified otherwise
        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        return MockExchange(initial_balance=initial_balance)

    if mode == "live":
        if provider == "binance":
            return BinanceAdapter(config)
        elif provider == "hyperliquid":
            return HyperliquidAdapter(config)
        else:
            raise ValueError(f"Unknown exchange provider: {provider}")

    raise ValueError(f"Unknown bot.mode={mode}. Use 'paper' or 'live'.")
