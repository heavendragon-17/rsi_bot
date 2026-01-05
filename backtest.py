import argparse
import sys
import os
import yaml

# Ensure imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.backtest.engine import BacktestEngine
from app.backtest.portfolio import BacktestPortfolio
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

    # Initialize Portfolio
    portfolio = BacktestPortfolio(initial_balance=args.balance)

    # Initialize Engine
    # Note: We pass the strategy class, not instance, to let Engine manage it if needed,
    # but currently Engine instantiates it.
    engine = BacktestEngine(
        data_path=args.data,
        strategy_class=RsiWmaRetestStrategy,
        portfolio=portfolio,
        config=config
    )

    # Run
    engine.run()

    # Report
    reporter = BacktestReporter(portfolio)
    reporter.generate_report()

if __name__ == "__main__":
    main()
