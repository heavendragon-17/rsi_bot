
"""
Verification script for Dynamic TP logic.
Style matches tests/quick_test_lock_profit.py
"""
import sys
import os
import pandas as pd
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.backtest.mock_exchange import MockExchange
from app.core.portfolio import PortfolioManager
from app.core.events import SignalEvent
from app.utils.indicators import Indicators

def create_mock_data():
    # Create enough data for indicators
    timestamps = [pd.Timestamp.now() - pd.Timedelta(hours=i) for i in range(220)]
    timestamps.reverse()
    data = []
    for i in range(220):
        data.append({
            "date": timestamps[i],
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
            "rsi": 50.0, "rsi_ema9": 50.0, "rsi_wma45": 50.0,
            "ema21": 100.0, "closed": True
        })
    df = pd.DataFrame(data, index=timestamps)
    return df

def test_tp_count_1():
    print("Testing TP Count = 1...")
    config = {
        "strategy_params": {
            "nr_tp_count": 1,
            "nr_tp1_rr": 1.0,
            "use_active_trades": True
        },
        "risk": {"tp1_close_pct": 0.5}, # Default shouldn't matter if logic works
        "bot": {"timeframe": "1h"},
        "backtest": {"initial_balance": 1000},
        "symbols": ["BTC/USDT"]
    }
    
    strategy = RsiNoRetestStrategy(config)
    
    # 1. Test Strategy Analysis
    df = create_mock_data()
    # Mock entry: Close > EMA21
    idx = -1
    df.iloc[idx, df.columns.get_loc("close")] = 105.0 
    df.iloc[idx, df.columns.get_loc("ema21")] = 104.0
    
    # Patch indicators
    last = {
        "close": 105.0, "high": 105.0, "low": 105.0, "open":105.0,
        "ema21": 104.0, "rsi_ema9": 60.0, "rsi_wma45": 50.0,
        "ts": datetime.now()
    }
    strategy.indicators.compute = lambda *args, **kwargs: df
    Indicators.last = lambda df: last
    
    # Force state
    strategy.context.transition("BTC/USDT:1h", "CONFIRMING", now_ts=datetime.now())
    
    signal = strategy.analyze("BTC/USDT", df)
    
    if not signal:
        print("FAIL: No signal generated")
        return False
        
    if signal.signal_type != "BUY":
        print(f"FAIL: Signal type is {signal.signal_type}")
        return False
        
    allocs = signal.tp_allocations
    if not allocs:
        print("FAIL: No tp_allocations in signal")
        return False
        
    print(f"  Signal allocations: {allocs}")
    if allocs.get("TP1") != 1.0:
        print(f"FAIL: TP1 allocation is {allocs.get('TP1')}, expected 1.0")
        return False
        
    # 2. Test Portfolio Execution
    exchange = MockExchange()
    pm = PortfolioManager(exchange, config)
    
    # Set fake balance
    exchange.fetch_balance = lambda: {"total": {"USDT": 1000}}
    
    # Seed price for MockExchange (Required for Market Buy)
    exchange.update_candle("BTC/USDT", Decimal("105"), Decimal("105"), Decimal("105"), Decimal("105"), datetime.now())

    # Process BUY
    exchange.update_candle("BTC/USDT", Decimal("105"), Decimal("105"), Decimal("105"), Decimal("105"), datetime.now())
    pm.on_signal(signal)
    
    pos = pm.positions.get("BTC/USDT")
    if not pos:
        print("FAIL: Position not created")
        return False
        
    print(f"  Position created. Amount: {pos.amount}, TP Allocs: {pos.tp_allocations}")
    if pos.tp_allocations["TP1"] != 1.0:
        print("FAIL: Position didn't inherit allocations")
        return False
        
    # Process TP1 HIT
    # Simulate a SELL signal triggering TP1
    sell_signal = SignalEvent(
        symbol="BTC/USDT", 
        signal_type="SELL", 
        price=Decimal("110"), # TP1 Price
        timestamp=datetime.now(), 
        reason="TP1 hit",
        sl_price=Decimal("100")
    )
    
    result = pm.on_signal(sell_signal)
    
    # Should close 100%
    if "BTC/USDT" in pm.positions:
        p = pm.positions["BTC/USDT"]
        print(f"FAIL: Position still exists! Amount: {p.amount}")
        return False
        
    print("PASS: Count 1 Logic verified.")
    return True

def test_tp_count_2():
    print("\nTesting TP Count = 2...")
    config = {
        "strategy_params": {
            "nr_tp_count": 2,
            "nr_tp1_rr": 1.0, 
            "nr_tp2_rr": 2.0,
            "tp1_close_pct": 0.4, # Custom percentage
        },
        "risk": {},
        "bot": {"timeframe": "1h"},
        "backtest": {"initial_balance": 1000},
        "symbols": ["BTC/USDT"]
    }
    
    strategy = RsiNoRetestStrategy(config)
    
    # 1. Strategy Check
    df = create_mock_data()
    strategy.context.transition("BTC/USDT:1h", "CONFIRMING", now_ts=datetime.now())
    
    # Patch
    last = {
        "close": 105.0, "high": 105.0, "low": 105.0, "open":105.0,
        "ema21": 104.0, "rsi_ema9": 60.0, "rsi_wma45": 50.0,
        "ts": datetime.now()
    }
    strategy.indicators.compute = lambda *args, **kwargs: df
    Indicators.last = lambda df: last
    
    signal = strategy.analyze("BTC/USDT", df)
    
    print(f"  Signal allocations: {signal.tp_allocations}")
    if signal.tp_allocations["TP1"] != 0.4:
        print("FAIL: TP1 != 0.4")
        return False
    if signal.tp_allocations["TP2"] != 1.0:
        print("FAIL: TP2 != 1.0")
        return False
        
    print("PASS: Count 2 Logic verified.")
    return True

if __name__ == "__main__":
    try:
        r1 = test_tp_count_1()
        r2 = test_tp_count_2()
        if r1 and r2:
            print("\nALL SPECTS PASSED.")
            sys.exit(0)
        else:
            print("\nSOME TESTS FAILED.")
            sys.exit(1)
    except Exception as e:
        print(f"\nCRASH: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
