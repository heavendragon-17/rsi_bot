from __future__ import annotations

from typing import Any, Dict

from app.core.interfaces import IExchange
from app.backtest.mock_exchange import MockExchange
from app.services.execution.cex.binance_adapter import BinanceAdapter


def create_exchange(config: Dict[str, Any]) -> IExchange:
    bot_cfg = config.get("bot", {})
    mode = (bot_cfg.get("mode") or "paper").lower()

    if mode == "paper":
        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        return MockExchange(initial_balance=initial_balance)

    if mode == "live":
        return BinanceAdapter(config)

    raise ValueError(f"Unknown bot.mode={mode}. Use 'paper' or 'live'.")
