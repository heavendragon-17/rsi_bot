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
from app.backtest.config_builder import build_backtest_config
from app.trading.strategy.loader import STRATEGY_MAP
# Path constants
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Run backtest on historical data")
    parser.add_argument("--data", type=str, required=True, help="Path to CSV data file")
    parser.add_argument("--balance", type=float, default=None, help="Initial balance (default: from config)")
    parser.add_argument("--symbol", type=str, default=None, help="Trading symbol (e.g. XPL/USDT). If not provided, inferred from filename")
    parser.add_argument("--timeframe", type=str, default=None, help="Timeframe (e.g. 5m). If not provided, inferred from filename")
    parser.add_argument("--output", type=str, default=os.path.join(SCRIPT_DIR, "report"), help="Output directory for reports")
    parser.add_argument(
        "--strategy", 
        type=str, 
        default=None,
        choices=list(STRATEGY_MAP.keys()),
        help="Strategy to use (default: from config.yaml)"
    )
    args = parser.parse_args()

    # Load base config once to read defaults
    base_config = load_config()

    # Get strategy from config or CLI override
    strategy_name = args.strategy or base_config.get("strategy", "rsi_wma_retest")
    if strategy_name not in STRATEGY_MAP:
        print(f"Error: Unknown strategy '{strategy_name}'. Available: {list(STRATEGY_MAP.keys())}")
        sys.exit(1)
    strategy_class = STRATEGY_MAP[strategy_name]

    # Determine balance
    balance = args.balance or base_config.get('backtest', {}).get('initial_balance', 10000)

    # Determine symbol
    if args.symbol:
        symbol = args.symbol
    else:
        # Infer from filename: BTCUSDT_5m.csv -> BTC/USDT
        filename = os.path.basename(args.data)
        base = filename.replace('.csv', '').split('_')[0]
        if base.endswith('USDT'):
            symbol = base[:-4] + '/USDT'
        elif base.endswith('USDC'):
            symbol = base[:-4] + '/USDC'
        else:
            symbol = base + '/USDT'

    # Determine timeframe
    if args.timeframe:
        timeframe = args.timeframe
    else:
        # Infer from filename: BTCUSDT_5m.csv -> 5m
        filename = os.path.basename(args.data)
        parts = filename.replace('.csv', '').split('_')
        timeframe = parts[1] if len(parts) > 1 else base_config.get('timeframe', '5m')

    # Build engine config via shared config builder (single source of truth)
    config = build_backtest_config(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        initial_balance=float(balance),
    )

    print(f"Strategy: {strategy_name}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Balance: ${balance:,.2f}")
    print("-" * 40)

    # Initialize Engine
    engine = BacktestEngine(
        data_path=args.data,
        strategy_class=strategy_class,
        config=config
    )

    # Run — returns pre-computed results dict
    results = engine.run()

    # Report
    os.makedirs(args.output, exist_ok=True)
    print(f"Saving reports to: {args.output}")

    leverage = config.get("risk", {}).get("leverage", 1)
    reporter = BacktestReporter(
        results,
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        leverage=leverage,
        strategy_params={**strategy_class.DEFAULT_CONFIG, **config.get("strategy_params", {})},
    )
    report_path = reporter.generate_report(output_dir=args.output)
    
    if report_path:
        print(f"Opening report: {report_path}")
        webbrowser.open('file://' + os.path.abspath(report_path))


if __name__ == "__main__":
    main()

