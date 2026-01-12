import pandas as pd
import numpy as np
from app.backtest.engine import BacktestEngine
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.core.portfolio import PortfolioManager
from unittest.mock import MagicMock, patch
import pytest

# Mock strategy to avoid complex logic
class MockStrategy(RsiNoRetestStrategy):
    def __init__(self, config):
        self.config = config
        self.indicators = MagicMock()
        # Mock compute to return df with indicators
        # IMPORTANT: The engine replaces its df with the result of compute.
        # So compute must return the dataframe!
        self.indicators.compute.side_effect = lambda df, **kwargs: df.copy()
        self.lookback = 30

    def analyze(self, symbol, df):
        return None

def test_engine_window_slicing():
    # Setup mock data
    n_rows = 600
    dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='15min')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': np.linspace(100, 200, n_rows),
        'high': np.linspace(101, 201, n_rows),
        'low': np.linspace(99, 199, n_rows),
        'close': np.linspace(100, 200, n_rows),
        'volume': np.random.rand(n_rows) * 1000
    })

    # Mock read_csv to return our df
    with patch('pandas.read_csv', return_value=df):
        config = {
            "symbols": ["BTC/USDT"],
            "bot": {"timeframe": "15m"},
            "strategy": {},
            "backtest": {"initial_balance": 1000}
        }

        # Initialize engine
        # We need to patch MockExchange too as it might do things
        with patch('app.backtest.engine.MockExchange'), \
             patch('app.backtest.engine.PortfolioManager') as MockPortfolio:

            engine = BacktestEngine("dummy_path", MockStrategy, config)

            # Verify _full_df is populated
            assert len(engine._full_df) == n_rows, f"Engine df empty! {len(engine._full_df)}"

            # Spy on strategy.analyze
            engine.strategy.analyze = MagicMock(return_value=None)

            # Patch the constant
            # We patch MAX_LOOKBACK_WINDOW to 50 for testing.
            # In engine.py, warmup_period is hardcoded to 220.
            # So loop starts at i=220.
            # start_idx = max(0, 220 - 50) = 170.
            # df_slice = iloc[170:221]. Length = 51.
            with patch('app.backtest.engine.MAX_LOOKBACK_WINDOW', 50):
                engine.run()

                # Check calls to analyze
                assert engine.strategy.analyze.called

                # Get the last call arguments
                # Last i = 599.
                # start_idx = 599 - 50 = 549.
                # slice = 549:600. Length = 51.
                args, _ = engine.strategy.analyze.call_args
                symbol, df_slice = args

                # Verify max window size was respected
                assert len(df_slice) == 51

                # Verify first call (i=220)
                # slice from 170 to 221 -> 51 rows
                first_call_args = engine.strategy.analyze.call_args_list[0]
                args, _ = first_call_args
                _, df_slice_first = args
                assert len(df_slice_first) == 51

if __name__ == "__main__":
    try:
        test_engine_window_slicing()
        print("Test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
