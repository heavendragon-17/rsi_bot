## 2024-05-23 - Single-Slot Cache Thrashing
**Learning:** The `Indicators` class used a single-slot cache `(key, value)`. Strategies computing indicators for multiple timeframes (e.g., 5m + 1h) or multiple symbols in a loop caused 100% cache misses due to thrashing. This is a common anti-pattern in stateful helper classes shared across contexts.
**Action:** Use `OrderedDict` or `lru_cache` to implement a small LRU buffer (size ~32) when a component handles multiple alternating contexts (e.g., symbol + timeframe tuples).
