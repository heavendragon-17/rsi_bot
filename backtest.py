import argparse
import sys
import os
import yaml

# Ensure imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="Path to CSV data file")
    parser.add_argument("--balance", type=float, default=1000.0, help="Initial balance")
    args = parser.parse_args()

    # Load Base Config
    config = load_config()

    # Override balance in config for backtest context
    if 'backtest' not in config:
        config['backtest'] = {}
    config['backtest']['initial_balance'] = args.balance

    # Initialize Engine
    # Engine now creates MockExchange and PortfolioManager internally based on config
    engine = BacktestEngine(
        data_path=args.data,
        strategy_class=RsiWmaRetestStrategy,
        config=config
    )

    # Run
    engine.run()

    # Report
    # Pass exchange from engine to reporter
    reporter = BacktestReporter(engine.exchange)
    reporter.generate_report()

if __name__ == "__main__":
    main()
