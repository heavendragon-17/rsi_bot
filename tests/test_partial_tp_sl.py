
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

class TestPartialTPSL(unittest.TestCase):
    def setUp(self):
        self.config = {
            "strategy_params": {
                "nr_tp1_rr": 1.0,
                "nr_lock_profit_rr": 0.2,
                "nr_move_sl_rr": 0.5,
                "use_active_trades": True
            },
            "risk": {
                "tp1_close_pct": 0.5,
                "leverage": 1,
                "risk_per_trade_pct": 0.02
            },
            "bot": {"timeframe": "1h"},
            "backtest": {"initial_balance": 1000},
            "symbols": ["BTC/USDT"]
        }
        self.exchange = MockExchange()
        self.portfolio = PortfolioManager(self.exchange, self.config)
        self.strategy = RsiNoRetestStrategy(self.config)
        self.strategy.context.trades = {} # Reset trades

    def test_partial_tp_and_sl_move(self):
        symbol = "BTC/USDT"
        
        # 1. Setup a fake trade with Entry @ 100, SL @ 90
        # Risk = 10. R = 10. 
        # TP1 (1R) = 110. Lock Profit (0.2R) = 100 + (10*0.2) = 102.
        entry_price = Decimal("100")
        sl_price = Decimal("90") 
        soft_sl = Decimal("90")
        
        # Mock Context State
        self.strategy.context.open_trade(
            symbol=symbol,
            timeframe="1h",
            side="LONG",
            entry_price=float(entry_price),
            meta={
                "entry_price": entry_price,
                "sl_price": soft_sl,
                "soft_sl_price": soft_sl,
                "original_soft_sl": soft_sl,
                "tp1_price": Decimal("110"),
                "tp2_price": Decimal("120"),
                "tp3_price": Decimal("130"),
                "tp1_hit": False,
                "tp2_hit": False,
                "tp3_hit": False,
                "moved_sl_to_entry": False,
            },
            now_ts=datetime.now()
        )
        
        # Mock Portfolio Position
        initial_amount = Decimal("2")
        self.portfolio.positions[symbol] = type('Position', (object,), {
            'symbol': symbol,
            'amount': initial_amount, 
            'entry_price': entry_price, 
            'sl_order_id': 'mock_sl_id',
            'tp1_hit': False, 'tp2_hit': False, 'tp3_hit': False,
            'side': 'BUY',
            'sl_price': sl_price
        })() # Instantiated object
        
        # Mock Exchange State
        self.exchange.positions[symbol] = initial_amount
        self.exchange.orders = {
            'mock_sl_id': {
                'id': 'mock_sl_id',
                'symbol': symbol,
                'amount': initial_amount,
                'price': float(sl_price),
                'side': 'SELL',
                'type': 'limit',
                'status': 'open'
            }
        }
        
        # 2. Simulate Candle hitting TP1 (High = 111 > 110)
        # We need at least 220 rows to pass strategy validation (len check)
        timestamps = [pd.Timestamp.now() - pd.Timedelta(hours=i) for i in range(220)]
        timestamps.reverse()
        
        data = []
        # Add 219 dummy rows
        for i in range(219):
            data.append({
                "date": timestamps[i],
                "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
                "ema21": 100.0, "ema200": 90.0, "closed": True
            })
            
        # Add the trigger row (Index -1)
        data.append({
            "date": timestamps[-1],
            "open": 105.0, "high": 111.0, "low": 105.0, "close": 108.0,
            "rsi": 60.0, "rsi_ema9": 60.0, "rsi_wma45": 50.0,
            "ema21": 100.0, "ema200": 90.0, "closed": True
        })
        
        df_mock = pd.DataFrame(data, index=timestamps)
        
        # Mock indicators
        self.strategy.indicators.compute = lambda df, **ks: df_mock
        
        # 3. Analyze - Should trigger TP1 Signal
        signal = self.strategy.analyze(symbol, df_mock)
        
        print("\nGenerated Signal:", signal)
        
        # Verify Signal
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "SELL")
        self.assertTrue(signal.reason.startswith("TP1"))
        
        # KEY CHECK: Does signal start with correct SL Price?
        # Lock Profit = 100 + (10 * 0.2) = 102
        expected_sl = Decimal("102")
        self.assertAlmostEqual(float(signal.sl_price), float(expected_sl), places=2)
        
        # 4. Simulate Portfolio Handling
        # We manually call on_signal because backtest loop usually does this
        
        # Mock create_order to track calls
        executed_orders = []
        def mock_create_order(**kwargs):
            executed_orders.append(kwargs)
            return {'id': 'new_ord_id', **kwargs}
            
        self.exchange.create_order = mock_create_order
        
        # Run portfolio logic
        self.portfolio.on_signal(signal)
        
        # 5. Verify Portfolio Actions
        # Should have 2 actions: 
        # a) Market Sell (TP1) for 50% amount (1.0)
        # b) Update SL Order (Cancel/Replace or Update)
        
        # Check Position Amount: 2.0 -> 1.0 (50% close)
        pos = self.portfolio.positions[symbol]
        self.assertEqual(pos.amount, Decimal("1.0"))
        self.assertTrue(pos.tp1_hit)
        
        # Check Executed Orders
        # Expectation: 
        # 1. Market SELL of 1.0 (TP1)
        # 2. Limit SELL (SL) of 1.0 at 102 (Lock Profit)
        
        print("\nExecuted Orders:", executed_orders)
        
        tp_orders = [o for o in executed_orders if o.get('type') == 'market']
        self.assertEqual(len(tp_orders), 1)
        self.assertEqual(tp_orders[0]['amount'], Decimal("1.0"))
        
        sl_orders = [o for o in executed_orders if o.get('type') == 'limit']
        # Depending on _move_sl_to_entry implementation, it might update existing or create new
        # Our mock exchange doesn't implement 'update_stop_loss' so it falls back to cancel+create
        self.assertTrue(len(sl_orders) >= 1)
        last_sl_order = sl_orders[-1]
        
        self.assertEqual(last_sl_order['price'], expected_sl)
        self.assertEqual(last_sl_order['amount'], Decimal("1.0"))

if __name__ == '__main__':
    unittest.main()
