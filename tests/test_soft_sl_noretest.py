
import unittest
import sys
import os
import pandas as pd
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.core.context import StrategyContext
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.backtest.mock_exchange import MockExchange
from app.core.portfolio import PortfolioManager
from app.core.events import SignalEvent

class TestSoftSLNoRetest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "strategy_params": {
                "sl_buffer_pct": 0.01, # Soft SL 1% below computed SL
                "disaster_sl_multiplier": 2.0, # Hard SL 2x further
                "use_active_trades": True
            },
            "bot": {"timeframe": "15m"},
            "risk": {"leverage": 1},
            "backtest": {"initial_balance": 1000},
            "symbols": ["BTC/USDT"]
        }
        self.exchange = MockExchange()
        self.portfolio = PortfolioManager(self.exchange, self.config)
        self.strategy = RsiNoRetestStrategy(self.config)

    def test_soft_sl_activation(self):
        symbol = "BTC/USDT"
        
        # 1. Setup a fake trade in context
        # Assume Entry @ 100, Soft SL @ 95, Hard SL @ 90
        entry_price = Decimal("100")
        soft_sl = Decimal("95") # Close below 95 triggers
        
        # Manually inject trade into context
        self.strategy.context.open_trade(
            symbol=symbol,
            timeframe="15m",
            side="LONG",
            entry_price=float(entry_price),
            meta={
                "entry_price": entry_price,
                "sl_price": soft_sl,
                "soft_sl_price": soft_sl,
                "disaster_sl_price": Decimal("90"), # Hard SL
                "tp_price": Decimal("110"),
                "moved_sl_to_entry": False,
            },
            now_ts=datetime.now()
        )
        
        # Inject position into exchange
        self.exchange.positions[symbol] = Decimal("1")
        self.exchange.margin_used[symbol] = Decimal("100")
        self.exchange.entry_prices[symbol] = entry_price

        # 2. Create mock dataframe with 220 rows (strategy requires len >= 220)
        timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15*i) for i in range(220)]
        timestamps.reverse()
        
        data = []
        # Add 219 dummy rows
        for i in range(219):
            data.append({
                "close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
                "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
                "ema21": 100.0, "ema200": 100.0, "closed": True
            })
            
        # Add the trigger row (Close < Soft SL)
        data.append({
            "close": 94.0,
            "high": 99.0,
            "low": 92.0,
            "open": 98.0,
            "rsi": 45.0,
            "rsi_ema9": 50.0,
            "rsi_wma45": 55.0,
            "ema21": 100.0,
            "ema200": 90.0,
            "closed": True
        })
        
        # Add NEXT candle to trigger the exit (since NoRetest exits at next open)
        data.append({
            "close": 93.0,
            "high": 95.0,
            "low": 91.0,
            "open": 93.9, # Should exit near here
            "rsi": 44.0,
            "rsi_ema9": 50.0,
            "rsi_wma45": 55.0,
            "ema21": 100.0,
            "ema200": 90.0,
            "closed": True
        })

        # Adjust timestamps to match data length
        timestamps = [pd.Timestamp.now() - pd.Timedelta(minutes=15*i) for i in range(len(data))]
        timestamps.reverse()

        df_mock = pd.DataFrame(data, index=timestamps)
        
        # Mock indicators.compute to return our df
        self.strategy.indicators.compute = lambda df, **ks: df_mock
        
        # 3. Run Analyze - First pass (identifies Soft SL hit)
        # We need to run it iteratively to simulate candle updates
        # But analyze() takes the full DF.

        # Simulate passing DF up to trigger candle
        df_trigger = df_mock.iloc[:-1]
        signal1 = self.strategy.analyze(symbol, df_trigger)
        self.assertIsNone(signal1, "Should not exit yet (waiting for next candle)")

        # Verify Pending Flag is set
        trade = self.strategy.context.get_trade(symbol)
        self.assertTrue(trade.meta.get("pending_candle_sl"), "Should have marked pending SL")

        # Simulate passing full DF (next candle open simulation)
        signal = self.strategy.analyze(symbol, df_mock)
        
        print("\nGenerated Signal:", signal)

        # 4. Verify Signal
        self.assertIsNotNone(signal, "Should have generated a signal on next candle")
        self.assertEqual(signal.signal_type, "SELL")
        self.assertEqual(signal.reason, "CLOSE_BY_CANDLE_SL")
        
        # Check Price (should be NEXT OPEN price)
        # Next Open is 93.9
        expected_price = Decimal("93.9")
        self.assertAlmostEqual(float(signal.price), float(expected_price), places=4)

if __name__ == '__main__':
    unittest.main()
