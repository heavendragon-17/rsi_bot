#!/usr/bin/env python
"""
Regression comparison: run backtests before/after optimization, compare results.

Usage:
    # Capture baseline
    python tests/regression_compare.py capture baseline.json
    # Capture after changes
    python tests/regression_compare.py capture after.json
    # Compare
    python tests/regression_compare.py compare baseline.json after.json
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOLERANCE = 1e-8
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "regression_btc_2k.csv")


def _silence_logging():
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


def _serialize(obj):
    import datetime
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def _extract_comparable(results: dict, name: str) -> dict:
    """Extract fields for regression comparison."""
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
        "max_drawdown_pct": float(
            results.get("drawdown", {}).get("max_drawdown_pct", 0)
        ),
        "sharpe_ratio": float(
            results.get("risk_metrics", {}).get("sharpe_ratio", 0)
        ),
        "sortino_ratio": float(
            results.get("risk_metrics", {}).get("sortino_ratio", 0)
        ),
        "total_trades": len(trades),
        "trades": trades,
    }


def run_single_backtests() -> dict:
    """Run single-symbol backtests for regression."""
    from app.backtest.engine.backtest_engine import BacktestEngine
    from app.trading.strategy.rsi_momentum import RsiMomentumStrategy
    from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy

    configs = [
        {
            "name": "single_rsi_no_retest",
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
            "name": "single_rsi_momentum",
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

    results = {}
    for cfg in configs:
        engine = BacktestEngine(
            data_path=DATA_PATH,
            strategy_class=cfg["strategy_class"],
            config=cfg["config"],
        )
        res = engine.run()
        results[cfg["name"]] = _extract_comparable(res, cfg["name"])
    return results


def run_portfolio_backtests() -> dict:
    """Run portfolio-mode backtests for regression."""
    import pandas as pd

    from app.backtest.engine.backtest_engine import BacktestEngine
    from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
    from app.backtest.engine.portfolio_engine import PortfolioEngine
    from app.backtest.exchange.mock_exchange import MockExchange
    from app.core.constants import WARMUP
    from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy

    strategy_class = RsiNoRetestStrategy
    config = {
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
    }

    strategy_instance = strategy_class(config)
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    prepared = BacktestEngine._prepare_dataframe(df, strategy_instance, "BTC/USDT")

    dfs = {"BTC/USDT": prepared}
    exchange = MockExchange(initial_balance=10000, leverage=10)
    event_source = BatchPortfolioEventSource(dfs, start_idx=WARMUP)
    engine = PortfolioEngine(
        event_source=event_source,
        strategy_class=strategy_class,
        exchange=exchange,
        config=config,
        symbols=["BTC/USDT"],
    )
    res = engine.run()

    return {
        "portfolio_rsi_no_retest": _extract_comparable(res, "portfolio_rsi_no_retest")
    }


def capture(output_path: str):
    """Run all backtests and save results."""
    _silence_logging()
    results = {}
    results.update(run_single_backtests())
    results.update(run_portfolio_backtests())

    output = json.dumps(results, indent=2, default=_serialize)
    with open(output_path, "w") as f:
        f.write(output)
    print(f"Captured {len(results)} test cases to {output_path}")
    for name, res in results.items():
        print(
            f"  {name}: balance={res['final_balance']:.8f}, "
            f"trades={res['total_trades']}, "
            f"sharpe={res['sharpe_ratio']:.8f}"
        )


def compare(baseline_path: str, after_path: str):
    """Compare two regression result files."""
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(after_path) as f:
        after = json.load(f)

    all_pass = True

    for name in baseline:
        if name not in after:
            print(f"FAIL: {name} missing from after results")
            all_pass = False
            continue

        b = baseline[name]
        a = after[name]

        # Compare scalar metrics
        for key in [
            "final_balance", "net_profit", "net_profit_pct",
            "max_drawdown_pct", "sharpe_ratio", "sortino_ratio",
        ]:
            bv = b.get(key, 0)
            av = a.get(key, 0)
            diff = abs(bv - av)
            if diff > TOLERANCE:
                print(f"FAIL: {name}.{key}: {bv} -> {av} (diff={diff:.2e})")
                all_pass = False
            else:
                print(f"  OK: {name}.{key} = {bv:.8f}")

        # Compare trade count
        if b["total_trades"] != a["total_trades"]:
            print(
                f"FAIL: {name}.total_trades: {b['total_trades']} -> {a['total_trades']}"
            )
            all_pass = False
        else:
            print(f"  OK: {name}.total_trades = {b['total_trades']}")

        # Compare trade-by-trade
        for i, (bt, at) in enumerate(zip(b["trades"], a["trades"], strict=False)):
            for field in ["entry_time", "exit_time", "side", "symbol"]:
                if bt[field] != at[field]:
                    print(
                        f"FAIL: {name}.trades[{i}].{field}: "
                        f"{bt[field]} -> {at[field]}"
                    )
                    all_pass = False
            for field in ["pnl", "entry_price", "exit_price"]:
                diff = abs(bt[field] - at[field])
                if diff > TOLERANCE:
                    print(
                        f"FAIL: {name}.trades[{i}].{field}: "
                        f"{bt[field]} -> {at[field]} (diff={diff:.2e})"
                    )
                    all_pass = False

    if all_pass:
        print("\n=== ALL REGRESSION CHECKS PASSED ===")
    else:
        print("\n=== REGRESSION FAILURES DETECTED ===")
    return all_pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python regression_compare.py capture <output.json>")
        print("       python regression_compare.py compare <baseline.json> <after.json>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "capture":
        capture(sys.argv[2] if len(sys.argv) > 2 else "/tmp/regression.json")
    elif cmd == "compare":
        if len(sys.argv) < 4:
            print("Usage: compare <baseline.json> <after.json>")
            sys.exit(1)
        ok = compare(sys.argv[2], sys.argv[3])
        sys.exit(0 if ok else 1)
