# Live Bot Architecture

> Complete specification for the live trading bot (`main.py` → `app/`).

---

## Startup Flow

```
main.py
  1. Load .env (API keys, Telegram tokens)
  2. AppConfig.from_yaml("config.yaml") — typed config with validation
  3. Init TelegramBot (falls back to NullNotifier on failure)
  4. create_exchange(config) — factory returns adapter based on mode
  5. MultiSymbolRunner(config, exchange, strategy_class, notifier).start()
  6. runner.wait() with SIGINT/SIGTERM graceful shutdown
```

## Data Ingestion

### BinanceStreamManager (`app/services/market_data/stream_manager.py`)

**WebSocket connection**: `wss://fstream.binance.com/stream?streams={symbol}@kline_{timeframe}`

Multiplexes all symbol streams over a single WebSocket connection.

**Startup sequence**:
1. **Historical fetch**: CCXT `fetch_ohlcv()` for `history_limit` (default 300) candles per symbol
2. Normalize via `DataNormalizer.normalize_ccxt()` → store in `MarketDataStore`
3. **Live stream**: WebSocket messages → `DataNormalizer.normalize_binance()` → `MarketEvent`

**Symbol normalization**:
- Input: `BTC/USDT` or `BTCUSDT`
- Stream symbol: `btcusdt` (lowercase for WS)
- CCXT symbol: `BTC/USDT:USDT` (with `:USDT` suffix for futures)

**Error recovery**: WebSocket disconnect → auto-reconnect after 2s delay.

### MarketDataStore (`app/services/market_data/store.py`)

**Thread-safe storage** for candle data with per-symbol locks.

```python
# Internal structure
Dict[str, pd.DataFrame]  # symbol → DataFrame

# DataFrame columns
Float:   open, high, low, close, volume, closed
Decimal: open_dec, high_dec, low_dec, close_dec  # for precise calcs
```

**Candle update logic**:
- Same timestamp as last row → **update** (in-progress candle)
- New timestamp → **append** (previous candle closed)
- Memory cap: `MAX_CANDLES_IN_RAM = 6000`

**Access**: `get_dataframe(symbol)` returns a **copy** to prevent concurrent modification.

## Strategy Execution

### Strategy Loading (`app/strategies/loader.py`)

```python
STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}
```

### Stateless Analyze Pattern

```python
def analyze(
    symbol: str,
    df: pd.DataFrame,
    position: Optional[PositionSnapshot] = None,
    context: Optional[ContextSnapshot] = None,
) -> AnalysisResult
```

- **Pure function**: No mutable `self.context` read/write during analyze
- **Inputs**: Read-only snapshots of position state and context state machine
- **Outputs**: Typed actions + new context snapshot
- **Test-friendly**: Inject any context state without global state pollution

### Entry State Machine

```
SCANNING ──[reclaim detected + pullback filter]──→ CONFIRMING
CONFIRMING ──[RSI spread ≥ threshold]──→ emit OpenPosition, → SCANNING
CONFIRMING ──[RSI spread < threshold]──→ reset → SCANNING
```

### Position Management (with position)

Checked in priority order:

1. **Candle-Close SL Exit**: If `pending_candle_sl=True` from previous candle → market close at current open
2. **TP Logic** (TP3 → TP2 → TP1):
   - TP3: Full exit, state → SCANNING
   - TP2: Partial close (50% remaining), keep SL
   - TP1: Partial close (50%), move SL to lock_profit_price (+0.2R above entry)
3. **SL Movement** (at +0.5R): Move SL to lock_profit_price, set `moved_sl_to_entry=True`
4. **Soft SL Guard**: If close ≤ soft_sl_price → set `pending_candle_sl=True` (deferred to next candle)

### Dual SL System

| SL Type | Price | Mechanism | Purpose |
|---------|-------|-----------|---------|
| Hard SL | Entry - 3x SL distance | `stop_market` on exchange | Disaster protection |
| Soft SL | Lowest close in lookback | Candle-close check in strategy | Tight risk control |

The soft SL uses a 2-candle pattern: candle N closes below soft SL → flag set → candle N+1 opens → market close at open price.

## MultiSymbolRunner (`app/core/runner.py`)

### Architecture

- **1 shared Exchange** (thread-safe via locks)
- **N threads** — one daemon thread per symbol
- **1 shared MarketDataStore** (thread-safe)
- **Per-symbol**: Strategy instance, PortfolioManager instance, ContextSnapshot

### Startup Sequence

```
runner.start()
  1. Set leverage for all symbols via exchange.set_leverage()
  2. Cleanup orphan positions from previous run
  3. Start market data stream (BinanceStreamManager)
  4. For sim mode: start PaperTradeStreamManager + PaperFundingScheduler
  5. Sleep 2s for initial data population
  6. Spawn one daemon thread per symbol
```

### Per-Symbol Loop

```python
while running:
    df = store.get_dataframe(symbol)
    if df is None or empty or last candle not closed:
        sleep(1); continue

    # Skip duplicate processing
    if current_timestamp == last_processed_ts:
        sleep(0.5); continue

    # Sim mode: notify PaperExchange of candle open price
    if sim_mode: exchange.on_kline_open(symbol, open_price)

    # Get read-only snapshots
    position = portfolio.get_position_snapshot(symbol)
    context = contexts.get(symbol, ContextSnapshot(state="SCANNING"))

    # Analyze (pure function)
    result = strategy.analyze(symbol, df, position=position, context=context)

    # Persist new context
    contexts[symbol] = result.new_context

    # Dispatch actions
    for action in result.actions:
        OpenPosition  → portfolio.on_signal(convert_to_SignalEvent)
        ClosePosition → portfolio.close_position(...)
        MoveSL        → portfolio.move_stop_loss(...)
        PartialClose  → portfolio.execute_partial_close(...)

    # Sync TP fills from exchange (polling-based)
    if symbol in portfolio.positions:
        portfolio.sync_tp_fills(symbol)

    sleep(0.1)
```

### Orphan Position Cleanup

On startup, fetches all positions from exchange, cancels all orders, market-closes remaining positions with `reduceOnly=True`, sends Telegram notification.

## Portfolio Manager (`app/core/portfolio.py`)

### Position Sizing

**Risk-based formula**:
```
risk_capital = initial_capital (if use_initial_capital_for_risk) else current_balance
risk_amount = risk_capital * risk_per_trade_pct
sl_distance_pct = |entry - sl| / entry
position_notional = risk_amount / sl_distance_pct
position_size = position_notional / entry_price
```

**Safety checks**: Rejects `sl_distance_pct ≤ 0`, warns if `< 0.3%`, caps to max position size.

### Entry Flow

```
1. Market BUY: create_order(type="market", side="BUY", amount=size)
2. Hard SL:    create_order(type="stop_market", side="SELL", stopPrice=disaster_sl, reduceOnly=True)
3. TP Orders:  limit orders for TP1/TP2/TP3 with reduceOnly=True
```

**TP Allocations**:
- TP1: `remaining * tp1_close_pct` (e.g., 50%)
- TP2: `remaining * tp2_close_pct` (e.g., 50% of what's left)
- TP3: `remaining * 1.0` (close all)

### TP Fill Sync (`sync_tp_fills()`)

Called after each candle close. For each TP order:
1. `exchange.fetch_order(order_id, symbol)`
2. If filled → update position amount, set `tp_hit=True`
3. If TP1 filled and position remains → move SL to breakeven
4. If amount ≤ 1e-8 → cleanup position

### SL Movement (`_move_sl_to_entry()`)

Cancels old SL order, places new `stop_market` at target price. Exit reason determined dynamically:
- `sl_price > entry` → "LOCK_PROFIT"
- `sl_price == entry` → "BREAKEVEN"
- `sl_price < entry` → "STOP_LOSS"

## Exchange Adapters

### BinanceAdapter (`app/services/execution/cex/binance_adapter.py`)

Wraps CCXT `binanceusdm`. Thread-safe via `threading.Lock`.

**Key methods**: `create_order()`, `fetch_order()`, `cancel_order()`, `cancel_all_orders()`, `fetch_positions()`, `fetch_balance()`, `set_leverage()`, `fetch_open_orders()`

### DEX Adapters

Custom adapters loaded dynamically:
- Module: `app.services.execution.dex.{name}_adapter`
- Class: `{Name}Adapter`
- Available: `HyperliquidAdapter`, `LighterAdapter`

## Indicators (`app/utils/indicators.py`)

Uses `pandas_ta` with manual fallback.

**Computed columns**: `rsi`, `rsi_ema9`, `rsi_wma45`, `ema21`, `ema200`

**Caching**: Key = `(symbol, timeframe, last_timestamp, df_length)`. Avoids recomputation on duplicate data.

**Key helpers**:
- `get_mode()` → "BULLISH" or "NEUTRAL" (EMA alignment)
- `calculate_price_at_rsi()` → inverse RSI lookup
- `check_wma_retest()` → RSI retesting WMA45 within distance

## Telegram Notifications (`app/services/notification/telegram_bot.py`)

- HTTP POST to `https://api.telegram.org/bot{token}/sendMessage`
- Supports inline URL buttons via `reply_markup`
- Falls back to `NullNotifier` on initialization failure
- Sends on: bot startup, trade execution, shutdown

## Graceful Shutdown

```
SIGINT/SIGTERM received
  → runner.stop()
  → Signal threads to exit via running.clear()
  → Stop market stream
  → Join threads with 5s timeout
  → Log exit status
```
