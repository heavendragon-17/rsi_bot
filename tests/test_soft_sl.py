
import unittest
import sys
import os
import pandas as pd
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.core.context import StrategyContext
from app.trading.strategy.rsi_wma_retest import RsiWmaRetestStrategy
from app.backtest.mock_exchange import MockExchange
from app.trading.portfolio.manager import PortfolioManager
from app.core.events import SignalEvent

class TestSoftSL(unittest.TestCase):
    def setUp(self):
        self.config = {
            "strategy_params": {
                "sl_buffer_pct": 0.01, # Soft SL 1% below R40
                "disaster_sl_multiplier": 2.0, # Hard SL 2x further
                "use_active_trades": True
            },
            "bot": {"timeframe": "1h"},
            "risk": {"leverage": 1},
            "backtest": {"initial_balance": 1000},
            "symbols": ["BTC/USDT"]
        }
        self.exchange = MockExchange()
        self.portfolio = PortfolioManager(self.exchange, self.config)
        self.strategy = RsiWmaRetestStrategy(self.config)
        self.strategy.context.trades = {} # Reset trades

    def test_soft_sl_activation(self):
        symbol = "BTC/USDT"
        
        # 1. Setup a fake trade in context (Skip Entry Logic for simplicity)
        # Assume Entry @ 100, Soft SL @ 90, Hard SL @ 80
        entry_price = Decimal("100")
        soft_sl = Decimal("95") # Close below 95 triggers
        
        # Manually inject trade into context
        self.strategy.context.open_trade(
            symbol=symbol,
            timeframe="1h",
            side="LONG",
            entry_price=float(entry_price),
            meta={
                "soft_sl_price": soft_sl,
                "disaster_sl_price": Decimal("80"), # Hard SL
                "tp1_price": Decimal("110"),
                "tp2_price": Decimal("120"),
                "tp3_price": Decimal("130"),
                "tp1_hit": False,
                "tp2_hit": False,
                "tp3_hit": False,
            },
            now_ts=datetime.now()
        )
        
        # Inject position into portfolio
        self.portfolio.positions[symbol] = type('obj', (object,), {
            'amount': Decimal("1"), 
            'entry_price': entry_price, 
            'sl_order_id': 'mock_sl_id',
            'tp1_hit': False, 'tp2_hit': False, 'tp3_hit': False,
            'side': 'BUY'
        })
        # Note: MockExchange needs position too for selling
        self.exchange.positions[symbol] = Decimal("1")
        self.exchange.margin_used[symbol] = Decimal("100")
        self.exchange.entry_prices[symbol] = entry_price

        # 2. simulate a candle that closes below Soft SL but above Hard SL
        # Open=98, High=99, Low=92, Close=94. (Soft SL=95, Hard SL=80)
        # We need len(df) >= 220 for the strategy safeguards
        
        timestamps = [pd.Timestamp.now() - pd.Timedelta(hours=i) for i in range(220)]
        timestamps.reverse()
        
        data = []
        # Add 219 dummy rows
        for i in range(219):
            data.append({
                "close": 100.0, "high": 100.0, "low": 100.0, "open": 100.0,
                "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
                "ema21": 100.0, "ema200": 100.0, "closed": True
            })
            
        # Add the trigger row (Index -1)
        data.append({
            "close": 94.0,
            "high": 99.0,
            "low": 92.0,
            "open": 98.0,
            "rsi": 45.0,
            "rsi_ema9": 50.0,
            "rsi_wma45": 55.0, # Just filler
            "ema21": 100.0,
            "ema200": 90.0,
            "closed": True
        })
        
        df_mock = pd.DataFrame(data, index=timestamps)
        
        # Mock indicators response structure which 'analyze' expects
        # The strategy calls indicators.compute -> returns df
        # We need to mock indicators.compute? 
        # Easier to just mock Indicators.last helper or ensure df has columns
        # The strategy does: last = Indicators.last(df_ind)
        # Indicators.last just returns dict of last row
        
        # Overwrite indicators.compute to return our df
        self.strategy.indicators.compute = lambda df, **ks: df_mock
        
        # 3. Run Analyze
        signal = self.strategy.analyze(symbol, df_mock)
        
        print("\nGenerated Signal:", signal)

        # 4. Verify Signal
        self.assertIsNotNone(signal, "Should have generated a signal")
        self.assertEqual(signal.signal_type, "SELL")
        self.assertEqual(signal.reason, "CLOSE_BY_CANDLE_SL")
        
        # Check Price (should have slippage)
        # 94 * (1 - 0.001) = 94 * 0.999 = 93.906
        expected_price = Decimal("94") * Decimal("0.999")
        self.assertAlmostEqual(float(signal.price), float(expected_price), places=4)

if __name__ == '__main__':
    unittest.main()
