
import sys
import os
import pandas as pd
import pytest

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.indicators import Indicators

def test_indicators_cache_lru():
    """Test that indicators cache works as an LRU cache."""
    indicators = Indicators(enable_cache=True)
    indicators._cache_size = 2  # Set small size for testing

    # Create dummy dataframes with unique properties for cache keys
    # Key relies on ts and length
    df1 = pd.DataFrame({"ts": [100], "close": [100.0]})
    df2 = pd.DataFrame({"ts": [200], "close": [200.0]})
    df3 = pd.DataFrame({"ts": [300], "close": [300.0]})

    # 1. Compute for df1 -> Cache: [df1]
    res1 = indicators.compute(df1, symbol="SYM", timeframe="5m")
    assert len(indicators._cache) == 1

    # 2. Compute for df2 -> Cache: [df1, df2]
    # Note: Insertion order is preserved. New items go to end.
    res2 = indicators.compute(df2, symbol="SYM", timeframe="5m")
    assert len(indicators._cache) == 2

    # 3. Compute for df1 again -> Cache: [df2, df1]
    # df1 is accessed, so it moves to the end (MRU position).
    res1_hit = indicators.compute(df1, symbol="SYM", timeframe="5m")
    assert res1_hit is res1  # Should be exact same object

    # Verify order: df2 first (LRU), df1 second (MRU)
    keys_step3 = list(indicators._cache.keys())
    key1 = ("SYM", "5m", 100, 1)
    key2 = ("SYM", "5m", 200, 1)
    assert keys_step3[0] == key2
    assert keys_step3[1] == key1

    # 4. Compute for df3 -> Cache: [df1, df3]
    # Size exceeds 2. Pop first item (df2). Add df3 to end.
    res3 = indicators.compute(df3, symbol="SYM", timeframe="5m")
    assert len(indicators._cache) == 2

    # Check keys in cache
    keys = list(indicators._cache.keys())
    key3 = ("SYM", "5m", 300, 1)

    # Expected: [df1, df3]
    # df1 was MRU, became LRU relative to df3. df2 was evicted.
    assert keys[0] == key1
    assert keys[1] == key3

    # Verify df2 is evicted
    assert key2 not in indicators._cache

def test_indicators_cache_disabled():
    """Test that cache can be disabled."""
    indicators = Indicators(enable_cache=False)

    df1 = pd.DataFrame({"ts": [100], "close": [100.0]})

    res1 = indicators.compute(df1, symbol="SYM", timeframe="5m")
    assert len(indicators._cache) == 0

    res2 = indicators.compute(df1, symbol="SYM", timeframe="5m")
    assert res1 is not res2  # Should be different objects (new copies)
