"""
Backtest Runner
================
Run backtests on historical data with configurable symbol and timeframe.
"""
import argparse
import sys
import os
import yaml

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy


def load_config() -> dict:
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Run backtest on historical data")
    parser.add_argument("--data", type=str, required=True, help="Path to CSV data file")
    parser.add_argument("--balance", type=float, default=1000.0, help="Initial balance")
    parser.add_argument("--symbol", type=str, default=None, help="Trading symbol (e.g. XPL/USDT). If not provided, inferred from filename")
    parser.add_argument("--timeframe", type=str, default=None, help="Timeframe (e.g. 5m). If not provided, inferred from filename")
    args = parser.parse_args()

    # Load Base Config
    config = load_config()

    # Override backtest settings
    if 'backtest' not in config:
        config['backtest'] = {}
    config['backtest']['initial_balance'] = args.balance

    # Determine symbol
    if args.symbol:
        symbol = args.symbol
    else:
        # Infer from filename: XPLUSDT_5m.csv -> XPL/USDT
        filename = os.path.basename(args.data)
        base = filename.replace('.csv', '').split('_')[0]
        # Try to split into symbol/USDT
        if base.endswith('USDT'):
            symbol = base[:-4] + '/USDT'
        elif base.endswith('USDC'):
            symbol = base[:-4] + '/USDC'
        else:
            symbol = base + '/USDT'  # Default assumption
    
    # Determine timeframe
    if args.timeframe:
        timeframe = args.timeframe
    else:
        # Infer from filename: XPLUSDT_5m.csv -> 5m
        filename = os.path.basename(args.data)
        parts = filename.replace('.csv', '').split('_')
        timeframe = parts[1] if len(parts) > 1 else config.get('timeframe', '5m')
    
    # Override config with command line values
    config['symbols'] = [symbol]
    config['timeframe'] = timeframe
    config['bot']['timeframe'] = timeframe

    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print("-" * 40)

    # Initialize Engine
    engine = BacktestEngine(
        data_path=args.data,
        strategy_class=RsiNoRetestStrategy,
        config=config
    )

    # Run
    engine.run()

    # Report
    reporter = BacktestReporter(engine.exchange, initial_balance=args.balance)
    reporter.generate_report()


if __name__ == "__main__":
    main()
