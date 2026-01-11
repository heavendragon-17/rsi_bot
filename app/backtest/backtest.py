"""
Backtest Runner
================
Run backtests on historical data with configurable symbol and timeframe.
"""
import argparse
import sys
import os
import yaml
import webbrowser

# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Add project root to path
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy

# Path constants
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Run backtest on historical data")
    parser.add_argument("--data", type=str, required=True, help="Path to CSV data file")
    parser.add_argument("--balance", type=float, default=1000.0, help="Initial balance")
    parser.add_argument("--symbol", type=str, default=None, help="Trading symbol (e.g. XPL/USDT). If not provided, inferred from filename")
    parser.add_argument("--timeframe", type=str, default=None, help="Timeframe (e.g. 5m). If not provided, inferred from filename")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "report"), help="Output directory for reports")
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
    os.makedirs(args.output, exist_ok=True)
    print(f"Saving reports to: {args.output}")
    
    reporter = BacktestReporter(
        engine.exchange, 
        config, 
        initial_balance=args.balance, 
        symbol=symbol, 
        timeframe=timeframe
    )
    report_path = reporter.generate_report(output_dir=args.output)
    
    if report_path:
        print(f"Opening report: {report_path}")
        webbrowser.open('file://' + os.path.abspath(report_path))


if __name__ == "__main__":
    main()
