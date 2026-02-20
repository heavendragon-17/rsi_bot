"""
Tests for soft SL (candle-close SL) in RsiNoRetestStrategy.

The strategy implements a 2-candle pattern:
  Candle 1: close <= soft_sl  → set pending_candle_sl=True, return DoNothing
  Candle 2: pending_candle_sl → ClosePosition at this candle's open price

This prevents the "wick through SL but close above" false trigger.
"""
import unittest
import pandas as pd
from decimal import Decimal

from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.backtest.mock_exchange import MockExchange
from app.core.portfolio import PortfolioManager
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.actions import ClosePosition, DoNothing
from app.utils.indicators import Indicators


class TestSoftSLNoRetest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "strategy_params": {
                "sl_buffer_pct": 0.0,
                "disaster_sl_multiplier": 2.0,
                "use_active_trades": True,
                "nr_move_sl_rr": 0.5,
                "nr_lock_profit_rr": 0.2,
                "nr_tp1_rr": 1.0,
                "nr_tp2_rr": 2.0,
                "nr_tp3_rr": 3.0,
                "nr_tp_count": 3,
            },
            "bot": {"timeframe": "15m"},
            "risk": {"leverage": 1},
            "backtest": {"initial_balance": 1000},
            "symbols": ["BTC/USDT"],
        }
        self.exchange = MockExchange()
        self.portfolio = PortfolioManager(self.exchange, self.config)
        self.strategy = RsiNoRetestStrategy(self.config)

    def _make_df(self, last_row: dict) -> pd.DataFrame:
        """Create a 220-row DataFrame where the last row has custom values."""
        timestamps = [
            pd.Timestamp.now() - pd.Timedelta(minutes=15 * i) for i in range(220)
        ]
        timestamps.reverse()
        rows = []
        for _ in range(219):
            rows.append(
                {
                    "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                    "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
                    "ema21": 100.0, "ema200": 100.0, "closed": True,
                }
            )
        rows.append(last_row)
        return pd.DataFrame(rows, index=timestamps)

    def test_soft_sl_two_candle_pattern(self):
        """
        Soft SL fires over two candles:
          1. close <= soft_sl  → DoNothing + pending_candle_sl=True
          2. next candle open  → ClosePosition(reason="CLOSE_BY_CANDLE_SL")
        """
        symbol = "BTC/USDT"
        entry_price = Decimal("100")
        soft_sl = Decimal("95")

        position = PositionSnapshot(
            has_position=True,
            symbol=symbol,
            side="BUY",
            entry_price=entry_price,
            current_sl=soft_sl,
            soft_sl=soft_sl,
            tp1_hit=False,
            tp2_hit=False,
            tp3_hit=False,
        )
        base_meta = {
            "entry_price": entry_price,
            "sl_price": soft_sl,
            "soft_sl_price": soft_sl,
            "original_soft_sl": soft_sl,
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
        }

        # ── CANDLE 1: close=94 < soft_sl=95, high=99 < move_trigger=102.5 ──
        ctx1 = ContextSnapshot(state="SCANNING", soft_sl_price=soft_sl, meta=base_meta)

        last1 = {
            "open": 98.0, "high": 99.0, "low": 92.0, "close": 94.0,
            "ema21": 100.0, "rsi_ema9": 50.0, "rsi_wma45": 55.0,
        }
        df1 = self._make_df(
            {"open": 98.0, "high": 99.0, "low": 92.0, "close": 94.0,
             "rsi": 45.0, "rsi_ema9": 50.0, "rsi_wma45": 55.0,
             "ema21": 100.0, "ema200": 90.0, "closed": True}
        )
        self.strategy.indicators.compute = lambda df, **kw: df1
        Indicators.last = lambda df: last1

        result1 = self.strategy.analyze(symbol, df1, position=position, context=ctx1)

        # Should not close yet — just set the flag
        self.assertIsInstance(
            result1.actions[0], DoNothing,
            "Candle-close below soft SL should return DoNothing on same candle",
        )
        self.assertTrue(
            result1.new_context.meta.get("pending_candle_sl"),
            "pending_candle_sl flag must be set in new_context",
        )

        # ── CANDLE 2: pending_candle_sl=True → close at this candle's open ──
        ctx2 = result1.new_context  # carries pending_candle_sl=True
        next_open = Decimal("96")

        last2 = {
            "open": float(next_open), "high": 97.0, "low": 95.0, "close": 97.0,
            "ema21": 100.0, "rsi_ema9": 49.0, "rsi_wma45": 50.0,
        }
        df2 = self._make_df(
            {"open": float(next_open), "high": 97.0, "low": 95.0, "close": 97.0,
             "rsi": 48.0, "rsi_ema9": 49.0, "rsi_wma45": 50.0,
             "ema21": 100.0, "ema200": 90.0, "closed": True}
        )
        self.strategy.indicators.compute = lambda df, **kw: df2
        Indicators.last = lambda df: last2

        result2 = self.strategy.analyze(symbol, df2, position=position, context=ctx2)

        close_action = next(
            (a for a in result2.actions if isinstance(a, ClosePosition)), None
        )
        self.assertIsNotNone(
            close_action, "Should generate ClosePosition on candle after soft SL flag"
        )
        self.assertEqual(close_action.reason, "CLOSE_BY_CANDLE_SL")
        self.assertEqual(
            close_action.price, next_open,
            "Exit price must be the next candle's open (2-candle pattern)",
        )

    def test_wick_below_soft_sl_no_close(self):
        """
        A wick below soft SL (low < soft_sl but close > soft_sl) must NOT trigger close.
        """
        symbol = "BTC/USDT"
        entry_price = Decimal("100")
        soft_sl = Decimal("95")

        position = PositionSnapshot(
            has_position=True,
            symbol=symbol,
            side="BUY",
            entry_price=entry_price,
            current_sl=soft_sl,
            soft_sl=soft_sl,
            tp1_hit=False,
            tp2_hit=False,
            tp3_hit=False,
        )
        meta = {
            "entry_price": entry_price,
            "sl_price": soft_sl,
            "soft_sl_price": soft_sl,
            "original_soft_sl": soft_sl,
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
        }
        ctx = ContextSnapshot(state="SCANNING", soft_sl_price=soft_sl, meta=meta)

        # low=93 wicks through soft_sl=95, but close=97 > soft_sl → no flag
        last = {
            "open": 98.0, "high": 99.0, "low": 93.0, "close": 97.0,
            "ema21": 100.0, "rsi_ema9": 52.0, "rsi_wma45": 50.0,
        }
        df = self._make_df(
            {"open": 98.0, "high": 99.0, "low": 93.0, "close": 97.0,
             "rsi": 52.0, "rsi_ema9": 52.0, "rsi_wma45": 50.0,
             "ema21": 100.0, "ema200": 90.0, "closed": True}
        )
        self.strategy.indicators.compute = lambda df, **kw: df
        Indicators.last = lambda df: last

        result = self.strategy.analyze(symbol, df, position=position, context=ctx)

        has_close = any(isinstance(a, ClosePosition) for a in result.actions)
        self.assertFalse(
            has_close, "Wick below soft SL with close above must NOT trigger ClosePosition"
        )
        self.assertFalse(
            result.new_context.meta.get("pending_candle_sl", False),
            "pending_candle_sl must remain False when close is above soft SL",
        )


if __name__ == "__main__":
    unittest.main()
