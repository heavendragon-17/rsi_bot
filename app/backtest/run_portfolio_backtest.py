"""
Unified Portfolio Backtest CLI
==============================
Runs a true unified portfolio backtest across multiple symbols.
"""

import os
import sys
import yaml
import argparse
import pandas as pd
from decimal import Decimal

# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Ensure we can import from app
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.backtest.portfolio_engine import PortfolioEngine
from app.backtest.portfolio_event_source import PortfolioEventSource
from app.backtest.mock_exchange import MockExchange
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
import ccxt
from app.backtest.download_data import download_data, calculate_candle_limit
from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.core.logging import setup_logging
import structlog

logger = structlog.get_logger()

# Strategy mapping
STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}

# Path constants
SYMBOLS_PATH = os.path.join(SCRIPT_DIR, "symbols.txt")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
REPORT_DIR = os.path.join(SCRIPT_DIR, "report")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _enrich_round_trips(results: dict, debug_rows: list) -> dict:
    """Join entry_spread and above_count from strategy debug rows into round_trips."""
    buy_lookup = {
        (str(r.get("symbol", "")), str(r.get("timestamp", ""))): r
        for r in debug_rows
        if r.get("signal") == "BUY"
    }
    rt_list = results.get("round_trips", [])
    if not rt_list or not buy_lookup:
        return results

    enriched = []
    for rt in rt_list:
        rt = dict(rt)
        sym = str(rt.get("symbol", ""))
        try:
            entry_ts = str(pd.Timestamp(rt["entry_time"])) if rt.get("entry_time") else ""
        except Exception:
            entry_ts = str(rt.get("entry_time", ""))
        match = buy_lookup.get((sym, entry_ts))
        rt["entry_rsi_ema9"] = round(float(match["rsi_ema9"]), 4) if match and match.get("rsi_ema9") is not None else None
        rt["entry_rsi_wma45"] = round(float(match["rsi_wma45"]), 4) if match and match.get("rsi_wma45") is not None else None
        rt["entry_spread"] = round(float(match["spread"]), 4) if match and match.get("spread") is not None else None
        rt["above_count"] = int(match["above_count"]) if match and match.get("above_count") is not None else None
        enriched.append(rt)

    results = dict(results)
    results["round_trips"] = enriched
    return results


def run_portfolio_analysis(config: dict, strategy_name: str, timeframe: str):
    symbols = config.get("symbols", [])
    
    # Alternatively fetch symbols from txt
    if os.path.exists(SYMBOLS_PATH) and not symbols:
        with open(SYMBOLS_PATH, "r") as f:
            symbols = [line.strip() for line in f if line.strip()]
            
    if not symbols:
         logger.error("No symbols found in config or symbols.txt")
         return
         
    strategy_class = STRATEGY_MAP.get(strategy_name)
    if not strategy_class:
        logger.error(f"Unknown strategy: {strategy_name}")
        return

    dfs = {}
    missing_data_symbols = []

    # Calculate dynamic candle limit
    duration_cfg = config.get("backtest", {}).get("duration", {})
    days = duration_cfg.get("days", 0)
    months = duration_cfg.get("months", 0)
    years = duration_cfg.get("years", 0)
    
    try:
        limit = calculate_candle_limit(timeframe, days=days, months=months, years=years)
    except ValueError as e:
        logger.error(f"Error calculating candle limit: {e}")
        limit = 8832 # Fallback

    # 1. Verify / download Data
    for symbol in symbols:
         safe_symbol = symbol.replace('/', '')
         data_file = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
         
         needs_download = False
         if not os.path.exists(data_file):
              needs_download = True
         else:
              # Check if the file has enough rows and is up to date
              row_count = 0
              last_line = ""
              with open(data_file, 'r', encoding='utf-8') as f:
                  for line in f:
                      if line.strip():
                          row_count += 1
                          last_line = line
              row_count -= 1 # subtract header
              
              if row_count < int(limit * 0.95): # 5% margin for missing data/downtime
                  needs_download = True
              else:
                  # Check recency based on the last row
                  try:
                      last_ts_str = last_line.split(',')[0].strip()
                      last_ts = pd.to_datetime(last_ts_str, errors='coerce')
                      
                      tf_str = timeframe.replace('m', 'min').replace('h', 'H').replace('d', 'D')
                      tf_delta = pd.to_timedelta(tf_str)
                      now_utc7 = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
                      
                      if pd.notna(last_ts) and (now_utc7 - last_ts) > (tf_delta * 2):
                          needs_download = True
                  except Exception as e:
                      logger.warning(f"Error checking data recency for {symbol}: {e}")
                      needs_download = True
                  
                  
         if needs_download:
              missing_data_symbols.append((symbol, safe_symbol, data_file))

    if missing_data_symbols:
         logger.warning(f"Data missing or insufficient for {len(missing_data_symbols)} symbols. Attempting to download...")
         # Create one shared exchange with markets loaded once — avoids N redundant API calls
         shared_exchange = ccxt.binanceusdm()
         print("Loading Binance Futures market list...")
         shared_exchange.load_markets()
         print(f"Markets loaded. Starting download for {len(missing_data_symbols)} symbol(s)...")
         for symbol, safe_symbol, data_file in missing_data_symbols:
               try:
                    download_data(symbol, timeframe, limit, DATA_DIR, exchange=shared_exchange)
                    if not os.path.exists(data_file):
                         logger.critical(f"Failed to fully download data for {symbol}. Stopping.")
                         sys.exit(1)
               except Exception as e:
                    logger.critical(f"Exception during download for {symbol}: {e}")
                    sys.exit(1)
                    
    # 2. Load all CSVs and pre-compute indicators
    strategy_instance = strategy_class(config)
    for symbol in symbols:
         safe_symbol = symbol.replace('/', '')
         data_file = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
         df = pd.read_csv(data_file)
         if limit > 0:
             df = df.tail(limit).reset_index(drop=True)
         df["timestamp"] = pd.to_datetime(df["timestamp"])
         
         # The base _prepare_dataframe modifies index and computes indicators
         prepared_df = BacktestEngine._prepare_dataframe(df, strategy_instance, symbol)
         dfs[symbol] = prepared_df

    # 3. Execution Setup
    balance = config.get("backtest", {}).get("initial_balance", 10000)
    
    risk_cfg = config.get("risk", {})
    leverage = risk_cfg.get("leverage", 10)
    taker_fee = float(risk_cfg.get("taker_fee", 0.0005))   # 0.05%
    maker_fee = float(risk_cfg.get("maker_fee", 0.0002))   # 0.02%

    exchange = MockExchange(
        initial_balance=balance,
        leverage=leverage,
        taker_fee=taker_fee,
        maker_fee=maker_fee,
    )
    
    event_source = PortfolioEventSource(dfs, start_idx=220)
    
    engine = PortfolioEngine(
         event_source=event_source,
         strategy_class=strategy_class,
         exchange=exchange,
         config=config,
         symbols=symbols
    )

    # 4. Run Backtest
    print(f"\n--- Unified Portfolio Backtest ---")
    print(f"Strategy: {strategy_name}")
    print(f"Symbols: {len(symbols)}")
    print(f"Initial Balance: ${balance}")
    print(f"Leverage: {leverage}x\n")

    def progress(data):
        pct = data.get("pct", 0)
        sys.stdout.write(f"\rProgress: {pct:3d}%")
        sys.stdout.flush()

    results = engine.run(on_progress=progress)
    print("\n[DONE] Backtest Complete")

    # **EXPORT PER-CANDLE DEBUG CSV**
    debug_rows = getattr(engine.strategy, "_debug_rows", [])
    if debug_rows:
        debug_path = os.path.join(REPORT_DIR, "debug_csv", f"debug_PORTFOLIO_{timeframe}.csv")
        engine.strategy.export_debug_csv(debug_path)
        print(f"Portfolio debug CSV: {debug_path}")
        # Enrich round_trips with per-trade entry_spread and above_count
        results = _enrich_round_trips(results, debug_rows)

    # 5. Extract and print results
    metrics = results.get("metrics", {})
    profit = results.get("net_profit", 0.0)
    profit_pct = results.get("net_profit_pct", 0.0)
    final = results.get("final_balance", balance)
    
    print("\n--- Summary ---")
    print(f"Final Balance: ${final:.2f}")
    print(f"Net Profit: ${profit:.2f} ({profit_pct:+.2f}%)")
    print(f"Total Trades: {metrics.get('total_trades', 0)}")
    print(f"Win Rate: {metrics.get('win_rate', 0):.2f}%")
    
    dd = results.get("drawdown", {})
    print(f"Max Drawdown: {dd.get('max_drawdown_pct', 0):.2f}% (-${dd.get('max_drawdown_value', 0):.2f})")

    # Save minimal report for debug
    reporter = BacktestReporter(
            results,
            symbol="PORTFOLIO",
            timeframe=timeframe,
            strategy_name=strategy_name,
            leverage=leverage,
            strategy_params={**strategy_class.DEFAULT_CONFIG, **config.get("strategy_params", {})},
        )
    os.makedirs(REPORT_DIR, exist_ok=True)
    html_content = reporter._generate_html_report(return_only=True, output_dir=REPORT_DIR)
    report_path = os.path.join(REPORT_DIR, "portfolio_backtest_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
         f.write(html_content)
    print(f"Report saved to: {report_path}")

    # Save JSON report for AI agent debugging
    import json
    import numpy as np

    def safe_serialize(obj):
        if isinstance(obj, (pd.Timestamp, pd.DatetimeIndex)):
            return obj.isoformat()
        if isinstance(obj, pd.Series):
            return obj.to_list()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        if hasattr(obj, "item"):
            return obj.item()
        from datetime import datetime, date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return str(obj)

    json_report_path = os.path.join(REPORT_DIR, "portfolio_backtest_report.json")
    try:
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, default=safe_serialize, indent=2)
        print(f"AI Debug Report saved to: {json_report_path}")
    except Exception as e:
        logger.error(f"Failed to generate JSON debug report: {e}")

    
    # Auto-open report in browser
    import webbrowser
    try:
        webbrowser.open(f"file://{os.path.abspath(report_path)}")
    except Exception as e:
        print(f"Could not auto-open report: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Unified Portfolio Backtest")
    parser.add_argument(
        "--strategy", 
        type=str, 
        default=None,
        choices=list(STRATEGY_MAP.keys()),
        help="Strategy to use (default: from config.yaml)"
    )
    args = parser.parse_args()

    # Load Config
    config = load_config()
    timeframe = config.get("timeframe", "15m")
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")
    
    # Ensure logs folder + structured logging
    setup_logging(level="DEBUG", log_file="backtest.log", console=False)

    run_portfolio_analysis(config, strategy_name, timeframe)
