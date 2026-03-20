
import unittest
import sys
import os
import pandas as pd
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.trading.strategy.rsi_no_retest import RsiNoRetestStrategy
from app.backtest.mock_exchange import MockExchange
from app.trading.portfolio.manager import PortfolioManager, Position
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.actions import PartialClose, MoveSL
from app.data.indicators import Indicators

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

    def test_partial_tp_and_sl_move(self):
        symbol = "BTC/USDT"

        # 1. Setup a fake trade with Entry @ 100, SL @ 90
        # Risk = 10. R = 10.
        # TP1 (1R) = 110. Lock Profit (0.2R) = 100 + (10*0.2) = 102.
        entry_price = Decimal("100")
        sl_price = Decimal("90")
        soft_sl = Decimal("90")

        # Build ContextSnapshot carrying trade metadata (new stateless API)
        ctx = ContextSnapshot(
            state="SCANNING",
            soft_sl_price=soft_sl,
            meta={
                "entry_price": entry_price,
                "sl_price": soft_sl,
                "soft_sl_price": soft_sl,
                "original_soft_sl": soft_sl,
                "tp1_price": Decimal("110"),
                "tp2_price": Decimal("120"),
                "tp3_price": Decimal("130"),
                "moved_sl_to_entry": False,
                "pending_candle_sl": False,
            },
        )

        # Build PositionSnapshot (tp_hit flags come from portfolio, not context)
        position = PositionSnapshot(
            has_position=True,
            symbol=symbol,
            side="BUY",
            entry_price=entry_price,
            current_sl=sl_price,
            soft_sl=soft_sl,
            tp1_hit=False,
            tp2_hit=False,
            tp3_hit=False,
        )

        # Mock Portfolio Position (for the execution phase)
        initial_amount = Decimal("2")
        self.portfolio.positions[symbol] = Position(
            symbol=symbol,
            amount=initial_amount,
            entry_price=entry_price,
            side='BUY',
            timestamp=datetime.now(),
            sl_price=sl_price,
            sl_order_id='mock_sl_id',
        )

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
                "rsi_14": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
                "ema21": 100.0, "ema200": 90.0, "closed": True
            })

        # Add the trigger row (Index -1)
        data.append({
            "date": timestamps[-1],
            "open": 105.0, "high": 111.0, "low": 105.0, "close": 108.0,
            "rsi_14": 60.0, "rsi_ema9": 60.0, "rsi_wma45": 50.0,
            "ema21": 100.0, "ema200": 90.0, "closed": True
        })

        df_mock = pd.DataFrame(data, index=timestamps)

        # Mock indicators (also patch Indicators.last to avoid global state pollution
        # from test_dynamic_tp.py which patches it with high=105.0)
        last_vals = {
            "close": 108.0, "high": 111.0, "low": 105.0, "open": 105.0,
            "ema21": 100.0, "rsi_ema9": 60.0, "rsi_wma45": 50.0,
        }
        self.strategy.indicators.compute = lambda df, **ks: df_mock
        Indicators.last = lambda df: last_vals

        # 3. Analyze - Should return MoveSL action (lock profit triggered at +0.5R)
        result = self.strategy.analyze(symbol, df_mock, position=position, context=ctx)

        print("\nGenerated Result:", result)

        # Verify action is MoveSL
        move_sl_action = next((a for a in result.actions if isinstance(a, MoveSL)), None)
        self.assertIsNotNone(move_sl_action, "Should have generated a MoveSL action for lock profit")
        self.assertTrue("MOVE_SL_LOCK_PROFIT" in move_sl_action.reason)

        # KEY CHECK: Does action carry correct new SL (lock profit)?
        # Risk = 10. Lock Profit target = 0.2R net of fees.
        # R = entry - sl = 100 - 90 = 10
        # target_net_profit = 0.2 * 10 = 2
        # Exit fee rate = 0.0005 (taker for stop_market)
        # Entry fee = 100 * 0.0005 = 0.05
        # 100 * 1.0005 + 2 = 102.05
        # exit * 0.9995 = 102.05
        # expected_sl = 102.05 / 0.9995 = 102.101...
        expected_sl = Decimal("102.10105052526263")
        self.assertIsNotNone(move_sl_action.new_sl_price)
        self.assertAlmostEqual(float(move_sl_action.new_sl_price), float(expected_sl), places=2)

        # 4. Simulate Portfolio Handling via execute_partial_close (new runner flow)

        # Mock create_order to track calls
        executed_orders = []
        def mock_create_order(symbol, order_type=None, side=None, amount=None, price=None, params=None):
            order = {
                'id': 'new_ord_id',
                'symbol': symbol,
                'order_type': order_type,
                'side': side,
                'amount': amount,
                'price': price,
                'params': params or {},
            }
            executed_orders.append(order)
            return order

        # Also mock cancel_order to not fail on the old SL
        self.exchange.cancel_order = lambda oid, sym: True
        self.exchange.create_order = mock_create_order

        # Run portfolio logic using new execute_partial_close path
        # In the new design, partial close is manual or triggered separately from the MoveSL,
        # but we can still test execute_partial_close using the price from move_sl_action as a test.
        self.portfolio.execute_partial_close(symbol, "TP1", new_sl_price=move_sl_action.new_sl_price)

        # 5. Verify Portfolio Actions
        # Should have 2 actions:
        # a) Market Sell (TP1) for 50% amount (1.0) with reduceOnly
        # b) stop_market SL of 1.0 at lock_profit price (102) with reduceOnly

        # Check Position Amount: 2.0 -> 1.0 (50% close)
        pos = self.portfolio.positions[symbol]
        self.assertEqual(pos.amount, Decimal("1.0"))
        self.assertTrue(pos.tp1_hit)

        # Check Executed Orders
        print("\nExecuted Orders:", executed_orders)

        tp_orders = [o for o in executed_orders if o.get('order_type') == 'market']
        self.assertEqual(len(tp_orders), 1)
        self.assertEqual(tp_orders[0]['amount'], Decimal("1.0"))
        # TP exit should have reduceOnly
        self.assertTrue(tp_orders[0]['params'].get('reduceOnly'))

        sl_orders = [o for o in executed_orders if o.get('order_type') == 'stop_market']
        self.assertTrue(len(sl_orders) >= 1)
        last_sl_order = sl_orders[-1]

        # SL price is in params.stopPrice for stop_market orders
        self.assertAlmostEqual(float(last_sl_order['params']['stopPrice']), float(expected_sl), places=2)
        self.assertEqual(last_sl_order['amount'], Decimal("1.0"))
        self.assertTrue(last_sl_order['params'].get('reduceOnly'))

if __name__ == '__main__':
    unittest.main()
