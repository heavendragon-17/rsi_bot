#!/usr/bin/env python
"""
Regression test: run identical backtests, dump results as JSON for comparison.

Usage:
    python tests/regression_backtest.py > results.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backtest.engine.backtest_engine import BacktestEngine
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy
from app.trading.strategy.rsi_momentum import RsiMomentumStrategy

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "regression_btc_2k.csv")

CONFIGS = [
    {
        "name": "rsi_no_retest",
        "strategy_class": RsiNoRetestStrategy,
        "config": {
            "symbols": ["BTC/USDT"],
            "timeframe": "15m",
            "bot": {"timeframe": "15m"},
            "strategy": "rsi_no_retest",
            "backtest": {"initial_balance": 10000},
            "risk": {"leverage": 10, "risk_per_trade_pct": 0.02},
            "strategy_params": {
                "nr_lookback": 30,
                "nr_max_above_ema21": 3,
                "nr_rsi_spread_min": 2.5,
                "nr_sl_mode": "lowest_close",
                "nr_tp_count": 1,
                "tp1_close_pct": 1.0,
            },
        },
    },
    {
        "name": "rsi_momentum",
        "strategy_class": RsiMomentumStrategy,
        "config": {
            "symbols": ["BTC/USDT"],
            "timeframe": "15m",
            "bot": {"timeframe": "15m"},
            "strategy": "rsi_momentum",
            "backtest": {"initial_balance": 10000},
            "risk": {"leverage": 10, "risk_per_trade_pct": 0.02},
        },
    },
]


def serialize(obj):
    """JSON-safe serialization for Decimal and other types."""
    from decimal import Decimal
    import datetime
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def extract_comparable(results: dict, name: str) -> dict:
    """Extract the fields we compare for regression."""
    round_trips = results.get("round_trips", [])

    trades = []
    for rt in round_trips:
        trades.append({
            "entry_time": str(rt.get("entry_time", "")),
            "exit_time": str(rt.get("exit_time", "")),
            "pnl": float(rt.get("pnl", 0)),
            "entry_price": float(rt.get("entry_price", 0)),
            "exit_price": float(rt.get("exit_price", 0)),
            "side": str(rt.get("side", "")),
            "symbol": str(rt.get("symbol", "")),
        })

    return {
        "name": name,
        "final_balance": float(results.get("final_balance", 0)),
        "net_profit": float(results.get("net_profit", 0)),
        "net_profit_pct": float(results.get("net_profit_pct", 0)),
        "max_drawdown_pct": float(results.get("drawdown", {}).get("max_drawdown_pct", 0)),
        "sharpe_ratio": float(results.get("risk_metrics", {}).get("sharpe_ratio", 0)),
        "sortino_ratio": float(results.get("risk_metrics", {}).get("sortino_ratio", 0)),
        "total_trades": len(trades),
        "trades": trades,
    }


def main():
    import logging

    # Silence all logging so only JSON goes to stdout
    logging.disable(logging.CRITICAL)
    try:
        import structlog
        structlog.configure(
            processors=[structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.BoundLogger,
            logger_factory=structlog.PrintLoggerFactory(file=open(os.devnull, "w")),
        )
    except Exception:
        pass

    all_results = {}
    for cfg_entry in CONFIGS:
        name = cfg_entry["name"]
        engine = BacktestEngine(
            data_path=DATA_PATH,
            strategy_class=cfg_entry["strategy_class"],
            config=cfg_entry["config"],
        )
        results = engine.run()
        all_results[name] = extract_comparable(results, name)

    # Write to file if --out is given, else stdout
    output = json.dumps(all_results, indent=2, default=serialize)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
