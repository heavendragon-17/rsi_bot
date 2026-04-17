"""
Backtest Config Builder
=======================
Single source of truth for building the config dict that BacktestEngine expects.
Used by both the CLI (app/backtest/backtest.py) and the API (app/api/routes/backtest.py).
"""

import os

import yaml  # type: ignore[import-untyped]


def build_backtest_config(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    initial_balance: float = 10000.0,
    leverage: int = 10,
    risk_per_trade_pct: float = 0.02,
    params: dict = None,
    base_config_path: str = "config.yaml",
) -> dict:
    """
    Build the config dict that BacktestEngine.__init__() expects.

    Loads the base config from YAML, then overrides with the provided params.
    If the YAML file doesn't exist, starts from an empty dict.

    Parameters
    ----------
    symbol : str
        Trading pair, e.g. "BTC/USDT".
    timeframe : str
        Candle timeframe, e.g. "5m".
    strategy_name : str
        Strategy key, e.g. "rsi_no_retest".
    initial_balance : float
        Starting USDT balance for the simulated exchange.
    leverage : int
        Futures leverage multiplier.
    risk_per_trade_pct : float
        Fraction of capital risked per trade (e.g. 0.02 = 2%).
    params : dict | None
        Strategy-specific overrides merged into ``strategy_params``.
    base_config_path : str
        Path to config.yaml (resolved relative to cwd).
    """
    if os.path.exists(base_config_path):
        with open(base_config_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # Core overrides
    config["symbols"] = [symbol]
    config["timeframe"] = timeframe
    config["strategy"] = strategy_name

    # Ensure bot section exists and has required fields
    config.setdefault("bot", {})
    config["bot"]["timeframe"] = timeframe

    # Backtest initial balance
    config.setdefault("backtest", {})
    config["backtest"]["initial_balance"] = initial_balance

    # Risk params
    config.setdefault("risk", {})
    config["risk"]["leverage"] = leverage
    config["risk"]["risk_per_trade_pct"] = risk_per_trade_pct

    # Optional strategy param overrides
    if params:
        config.setdefault("strategy_params", {})
        config["strategy_params"].update(params)

    return config
