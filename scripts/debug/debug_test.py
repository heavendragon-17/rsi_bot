# Simple test to debug MockExchange
import yaml

from app.backtest.engine.backtest_engine import BacktestEngine
from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy

config = yaml.safe_load(open("config.yaml"))
config["symbols"] = ["BTC/USDT"]

engine = BacktestEngine("app/backtest/data/BTCUSDT_15m.csv", RsiNoRetestStrategy, config)

print(f"Initial balance: {engine.exchange.get_balance()}")
print(f"Leverage: {engine.exchange.leverage}")

engine.run()

print("\n=== Results ===")
print(f"Total trades: {len(engine.exchange.trade_history)}")
print(f"Final balance: {engine.exchange.get_balance()}")

# Show last 5 trades
if engine.exchange.trade_history:
    print("\nLast 5 trades:")
    for trade in engine.exchange.trade_history[-5:]:
        print(f"  {trade['side']} {trade['amount']:.4f} @ {trade['price']:.2f} | PnL: {trade.get('pnl', 'N/A')}")
