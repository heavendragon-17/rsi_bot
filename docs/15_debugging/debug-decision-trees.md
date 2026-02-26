# Debug Decision Trees

> Structured diagnostic flowcharts: symptom → check → diagnose → fix.

---

## 1. Bot Is Not Entering Trades

```
Is WebSocket connected?
├── NO → Check logs for stream_disconnected errors
│        → Check network, check Binance status
│        → See runbook-websocket-disconnect.md
│
└── YES → Is data fresh? (last candle < 2× timeframe old)
          ├── NO → MarketDataStore not updating
          │        → Check BinanceStreamManager logs
          │        → Restart bot
          │
          └── YES → Is strategy in correct state?
                    ├── Check ContextSnapshot: SCANNING or CONFIRMING?
                    │
                    ├── Stuck in SCANNING → No reclaim detected
                    │   → Check EMA21 crossover conditions
                    │   → Check pullback filter (nr_max_above_ema21)
                    │   → Market may not have pullback pattern
                    │
                    ├── Stuck in CONFIRMING → RSI spread not met
                    │   → Check RSI_EMA9 - RSI_WMA45 vs nr_rsi_spread_min
                    │   → Consider lowering nr_rsi_spread_min
                    │
                    └── State is correct → Check PortfolioManager
                        ├── Already has position? → Only 1 position per symbol
                        ├── Position sizing returns 0? → SL too close (< min_sl_distance_pct)
                        └── Exchange error on entry? → Check InsufficientFunds / OrderRejected
```

---

## 2. Order Was Rejected

```
What error type?
├── InsufficientFundsError
│   ├── Check balance: enough free margin?
│   ├── Check other open positions consuming margin
│   ├── Check leverage: is it set correctly?
│   └── Fix: reduce max_position_size_pct or close other positions
│
├── OrderRejectedError
│   ├── Is it a reduceOnly exit order?
│   │   ├── YES → Position may already be closed (hard SL fired)
│   │   │        → Bot handles this in _handle_soft_sl_exit()
│   │   └── NO → Check order parameters (price, amount, symbol)
│   ├── Check minimum order size
│   └── Check if symbol is available for trading
│
└── RateLimitError
    ├── CCXT has built-in rate limiting (enableRateLimit=True)
    ├── Transient — usually auto-recovers
    └── If persistent: reduce API call frequency, check max_workers
```

---

## 3. SL/TP Not Placed After Entry

```
Did entry order fill?
├── NO → Check order status in logs (order_placed → was it filled?)
│        → Check InsufficientFunds or OrderRejected errors
│
└── YES → Check logs after entry for SL/TP placement
          ├── SL placement failed?
          │   → Check stopPrice validity (below entry for long)
          │   → Check exchange error logs
          │
          ├── TP placement failed?
          │   → Check TP prices (above entry for long)
          │   → Check order amount (minimum size)
          │
          └── No errors but orders missing?
              → Position may have been created but order IDs not stored
              → Restart bot → sync_from_exchange() will detect
```

---

## 4. Backtest Returns Unexpected Results

```
Is data complete?
├── NO → Check CSV for gaps (missing timestamps)
│        → Re-download with larger --limit
│
└── YES → Are strategy params correct?
          ├── Check config override hierarchy
          │   (DEFAULT_CONFIG < config.yaml < UI sidebar)
          ├── Check which strategy is loaded
          │   (verify strategy_name in config)
          │
          └── Params correct → Check engine behavior
              ├── MockExchange fills at exact price (no slippage)
              ├── WARMUP = 220 candles skipped
              ├── All candles marked closed=True
              └── Indicators computed once for full dataset
                  (differs from live where computed incrementally)
```

---

## 5. SSE Stream Not Working

```
Is backtest process running?
├── NO → Check ThreadPoolExecutor
│        → Check for exceptions in job submission
│
└── YES → Is SSE connection open?
          ├── NO → Check browser dev tools → EventSource connection
          │        → Check CORS settings (localhost:5173 allowed?)
          │
          └── YES → Check thread-to-async bridge
                    ├── Is multiprocessing.Queue receiving events?
                    ├── Is polling thread running?
                    └── Is loop.call_soon_threadsafe() working?
                        → Check asyncio event loop state
```
