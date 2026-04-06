"""
Backtest Config Builder
=======================
Single source of truth for building the config dict that BacktestEngine expects.
Used by both the CLI (app/backtest/backtest.py) and the API (app/api/routes/backtest.py).

CLI path: ``load_yaml=True`` (default) — loads config.yaml as the base so
  fields like tp1_close_pct that the CLI never passes are inherited.

API/UI path: ``load_yaml=False`` — starts from an empty dict so that
  *every* parameter comes explicitly from the request, not from config.yaml.
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
    load_yaml: bool = True,
    # --- Risk params that PositionSizer / SLTPManager read ---
    tp1_close_pct: float | None = None,
    tp2_close_pct: float | None = None,
    max_position_size_pct: float | None = None,
    min_sl_distance_pct: float | None = None,
    use_risk_based_sizing: bool | None = None,
    use_initial_capital_for_risk: bool | None = None,
    # --- Fee params that BacktestEngine reads ---
    taker_fee: float | None = None,
    maker_fee: float | None = None,
) -> dict:
    """
    Build the config dict that BacktestEngine.__init__() expects.

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
    load_yaml : bool
        If True (default, CLI path), load config.yaml as base dict.
        If False (API/UI path), start from empty dict so every parameter
        is explicitly controlled by the caller.
    tp1_close_pct : float | None
        Fraction to close at TP1.  None → not set (inherits from yaml or
        code default in SLTPManager).
    tp2_close_pct : float | None
        Fraction to close at TP2.
    max_position_size_pct : float | None
        Max margin fraction per trade.
    min_sl_distance_pct : float | None
        Minimum SL distance; trades with tighter SL are capped.
    use_risk_based_sizing : bool | None
        Whether to size positions based on SL distance.
    use_initial_capital_for_risk : bool | None
        Whether to use initial capital (vs current balance) for risk calc.
    taker_fee : float | None
        Taker fee rate for market / stop-market orders.
    maker_fee : float | None
        Maker fee rate for limit orders.
    """
    # ---- Base config ----
    if load_yaml and base_config_path and os.path.exists(base_config_path):
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

    # Backtest initial balance (no duration when yaml is skipped)
    config.setdefault("backtest", {})
    config["backtest"]["initial_balance"] = initial_balance

    # Risk params — always set the core ones
    config.setdefault("risk", {})
    config["risk"]["leverage"] = leverage
    config["risk"]["risk_per_trade_pct"] = risk_per_trade_pct

    # Extended risk params — only set if explicitly provided so that
    # CLI path (load_yaml=True) keeps using the yaml values while
    # API path (load_yaml=False) must pass them all.
    if tp1_close_pct is not None:
        config["risk"]["tp1_close_pct"] = tp1_close_pct
    if tp2_close_pct is not None:
        config["risk"]["tp2_close_pct"] = tp2_close_pct
    if max_position_size_pct is not None:
        config["risk"]["max_position_size_pct"] = max_position_size_pct
    if min_sl_distance_pct is not None:
        config["risk"]["min_sl_distance_pct"] = min_sl_distance_pct
    if use_risk_based_sizing is not None:
        config["risk"]["use_risk_based_sizing"] = use_risk_based_sizing
    if use_initial_capital_for_risk is not None:
        config["risk"]["use_initial_capital_for_risk"] = use_initial_capital_for_risk
    if taker_fee is not None:
        config["risk"]["taker_fee"] = taker_fee
    if maker_fee is not None:
        config["risk"]["maker_fee"] = maker_fee

    # Optional strategy param overrides
    if params:
        config.setdefault("strategy_params", {})
        config["strategy_params"].update(params)

    return config
