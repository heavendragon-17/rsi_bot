# SPEC: Live Trading Execution + MockExchange Upgrade

> Wires `PortfolioManager` to real Binance execution (paper → live) and upgrades `MockExchange` to match real exchange order semantics. Single normalized order vocabulary shared across both.

---

## Status Quo

| Component               | Current State                                                     | Problem                                                                                        |
| ----------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `main.py`               | Signal-only (execution commented out)                             | No trades execute                                                                              |
| `PortfolioManager`      | Places SL as `type="limit"`                                       | Wrong order type for real exchange — limit orders fill immediately if price is above limit     |
| `BinanceSignalExecutor` | Standalone polling loops                                          | Duplicates PM logic, architecturally wrong — **DELETE**                                        |
| `BinanceAdapter`        | Has both live (CCXT) and paper (`UMFuturesPaperClient`)           | Paper client is a custom wrapper around `binance-connector`, not CCXT — inconsistent interface |
| `MockExchange`          | Only `LIMIT` and custom `place_stop_loss()`/`place_take_profit()` | Doesn't use normalized order types; `create_order()` doesn't handle `stop_market`              |
| `exchange_factory.py`   | Returns raw CCXT object for paper/live                            | Raw CCXT doesn't implement `IFuturesExchange` — no `update_stop_loss()`, no `reduceOnly`       |
| Startup                 | No leverage setting, no position cleanup                          | Leverage defaults to exchange setting; orphan positions survive restarts                       |

---

## Design Decisions (from interview)

| # | Decision |
|---|---|
| 1 | Use `PortfolioManager` as sole execution path. Delete `BinanceSignalExecutor`. |
| 2 | PM uses **normalized order type vocabulary**. Each adapter translates to exchange-native types. |
| 3 | SL orders use `stop_market` (not `limit`). All SL/TP orders include `reduceOnly=true`. |
| 4 | TP1/TP2/TP3 placed as limit orders on exchange. |
| 5 | Paper mode = Binance Testnet via CCXT `set_sandbox_mode(True)` (not custom `UMFuturesPaperClient`). |
| 6 | LFT polling for fill detection: check order status after each candle close (~15m interval). |
| 7 | On restart: auto-close all open positions, cancel all orders, Telegram alert, start fresh. |
| 8 | Set leverage on startup via `exchange.set_leverage()`. |
| 9 | Pre-execution guard: `fetch_positions()` before soft SL exit to prevent double-sell race. |
| 10 | `MockExchange` upgraded to use same normalized order types as real exchange. |

---

## Normalized Order Type Vocabulary

`PortfolioManager` speaks this vocabulary. Every adapter must translate it.

| PM Order Type | `params` | Binance Translation | MockExchange Translation |
|---|---|---|---|
| `market` | `{reduceOnly?}` | `MARKET` | Immediate fill at current price |
| `limit` | `{reduceOnly?, timeInForce?}` | `LIMIT` + `GTC` | Pending, fill when price crosses |
| `stop_market` | `{stopPrice, reduceOnly?}` | `STOP_MARKET` + `stopPrice` | Pending, trigger when price crosses stop (opposite to limit) |
| `stop_limit` | `{stopPrice, reduceOnly?}` | `STOP` + `stopPrice` + `price` | Pending, trigger → limit order |
| `trailing_stop` | `{callbackRate, reduceOnly?}` | `TRAILING_STOP_MARKET` + `callbackRate` | Pending, dynamic trigger |

### `reduceOnly` Safety Rule

**Every exit order (SL, TP, soft SL close) MUST include `reduceOnly=true` in params.**

This prevents:
- SL filling after position is already closed → accidentally opening a SHORT
- Soft SL market sell firing after hard SL already triggered → same problem
- TP limit filling after manual close → unintended SHORT

The adapter passes `reduceOnly` to the exchange. `MockExchange` enforces it by capping sell amount at current position size (already does this with tolerance check, but must also skip order if position is zero).

---

## Architecture Changes

### Layer Diagram (after changes)

```
Strategy.analyze() → SignalEvent
        ↓
PortfolioManager.on_signal()
  - Decides order types (market, stop_market, limit)
  - Adds reduceOnly=true for all exits
  - Adds stopPrice for SL orders
  - Calls exchange.create_order(normalized_type, params)
        ↓
IFuturesExchange.create_order()
  - BinanceAdapter: translates to CCXT/Binance params
  - MockExchange: handles internally
  - Future adapters: translate to their native API
```

### Interface Changes (`app/core/interfaces.py`)

Add to `IFuturesExchange`:

```python
@abstractmethod
def create_order(
    self,
    symbol: str,
    order_type: str,  # normalized: market, limit, stop_market, stop_limit, trailing_stop
    side: str,
    amount: Decimal,
    price: Optional[Decimal] = None,
    params: Optional[Dict[str, Any]] = None,  # stopPrice, reduceOnly, callbackRate, etc.
) -> Optional[Dict[str, Any]]:
    """
    Create an order using normalized order types.
    Adapter translates to exchange-native format.
    """
    pass

@abstractmethod
def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch all open/pending orders for a symbol."""
    pass

@abstractmethod
def cancel_all_orders(self, symbol: str) -> int:
    """Cancel all open orders for a symbol. Returns count cancelled."""
    pass
```

---

## Component Changes

### 1. Delete `BinanceSignalExecutor`

**Delete file:** `app/services/execution/cex/binance_signal_executor.py`

Remove all references from `main.py` (already commented out, just delete the comments).

### 2. New `BinanceAdapter` (rewrite)

**File:** `app/services/execution/cex/binance_adapter.py`

Replace the current dual-client adapter with a clean CCXT-only wrapper that implements `IFuturesExchange`.

```python
class BinanceAdapter(IFuturesExchange):
    """
    Binance USDT-M Futures adapter.
    Wraps CCXT binanceusdm. Supports paper (testnet) and live (mainnet).
    Translates normalized order types to Binance-native params.
    """

    def __init__(self, config: dict):
        mode = config.get("bot", {}).get("mode", "paper")
        api_key, secret = _get_credentials(mode)

        self._exchange = ccxt.binanceusdm({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        })

        if mode == "paper":
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        """Translate normalized order types to Binance."""
        params = params or {}
        ccxt_params = {}

        # reduceOnly
        if params.get('reduceOnly'):
            ccxt_params['reduceOnly'] = True

        # Order type translation
        if order_type == 'stop_market':
            ccxt_type = 'STOP_MARKET'
            ccxt_params['stopPrice'] = float(params['stopPrice'])
        elif order_type == 'stop_limit':
            ccxt_type = 'STOP'
            ccxt_params['stopPrice'] = float(params['stopPrice'])
        elif order_type == 'trailing_stop':
            ccxt_type = 'TRAILING_STOP_MARKET'
            ccxt_params['callbackRate'] = float(params['callbackRate'])
        else:
            ccxt_type = order_type.upper()  # market, limit

        return self._exchange.create_order(
            symbol=_to_external_symbol(symbol),
            type=ccxt_type,
            side=side.upper(),
            amount=float(amount),
            price=float(price) if price else None,
            params=ccxt_params,
        )
```

**Key methods to implement:**
- `create_order()` — type translation + `reduceOnly`
- `cancel_order(order_id, symbol)` — delegates to CCXT
- `cancel_all_orders(symbol)` — `self._exchange.cancel_all_orders(symbol)`
- `fetch_positions(symbols)` — delegates to CCXT, filters zero positions
- `fetch_balance()` — delegates to CCXT
- `fetch_open_orders(symbol)` — `self._exchange.fetch_open_orders(symbol)`
- `set_leverage(leverage, symbol)` — `self._exchange.set_leverage(leverage, symbol)`
- `fetch_ohlcv()` — delegates to CCXT
- `get_precision_info(symbol)` — reads from `self._exchange.markets`

**Delete:** `UMFuturesPaperClient` class (no longer needed — CCXT sandbox mode replaces it).

### 3. `PortfolioManager` Changes

**File:** `app/core/portfolio.py`

#### 3a. BUY signal → place entry + SL + TP orders

```python
def _handle_buy_signal(self, signal, balance):
    # ... existing position sizing logic ...

    # 1. Market BUY
    order = self.exchange.create_order(
        symbol=signal.symbol,
        order_type="market",
        side="BUY",
        amount=amount,
        price=signal.price,  # hint for MockExchange
    )

    # 2. Place hard SL as STOP_MARKET (reduceOnly)
    if signal.sl_price:
        sl_order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type="stop_market",
            side="SELL",
            amount=amount,
            params={
                "stopPrice": signal.sl_price,
                "reduceOnly": True,
            },
        )
        pos.sl_order_id = sl_order.get("id")

    # 3. Place TP limit orders (reduceOnly)
    tp_orders = self._place_tp_orders(signal, amount)
    pos.tp_order_ids = tp_orders  # {"TP1": order_id, "TP2": order_id, ...}
```

#### 3b. New method: `_place_tp_orders()`

```python
def _place_tp_orders(self, signal, total_amount):
    """Place TP1/TP2/TP3 as limit orders on exchange."""
    tp_order_ids = {}
    remaining = total_amount

    levels = [
        ("TP1", signal.tp1_price, self.tp1_close_pct),
        ("TP2", signal.tp2_price, self.tp2_close_pct),
        ("TP3", signal.tp3_price, Decimal("1.0")),  # close all remaining
    ]

    for label, tp_price, pct in levels:
        if tp_price is None:
            continue
        close_amount = remaining * pct
        if close_amount <= 0:
            continue

        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type="limit",
            side="SELL",
            amount=close_amount,
            price=tp_price,
            params={"reduceOnly": True},
        )
        if order and order.get("id"):
            tp_order_ids[label] = order["id"]

        remaining -= close_amount

    return tp_order_ids
```

#### 3c. TP fill detection (polling after candle close)

Add to `on_signal()` or as a separate method called from `MultiSymbolRunner`:

```python
def sync_tp_fills(self, symbol):
    """
    Check if any TP orders have filled. Update position accordingly.
    Called after each candle close (polling approach for LFT).
    """
    if symbol not in self.positions:
        return

    pos = self.positions[symbol]

    for tp_level, order_id in list(pos.tp_order_ids.items()):
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            if order.get("status") in ("closed", "filled"):
                filled_amount = Decimal(str(order.get("filled", 0)))
                pos.amount -= filled_amount
                setattr(pos, f"{tp_level.lower()}_hit", True)
                del pos.tp_order_ids[tp_level]

                # Move SL to breakeven after TP1
                if tp_level == "TP1":
                    self._move_sl_to_entry(symbol)
        except Exception as e:
            logging.warning(f"Failed to check {tp_level} order {order_id}: {e}")

    # Cleanup if fully closed
    if pos.amount <= Decimal("1e-8"):
        self._cleanup_position(symbol)
```

#### 3d. Soft SL pre-execution guard

```python
def _handle_soft_sl_exit(self, signal):
    """Execute soft SL with pre-execution position check."""
    # Pre-execution guard: verify position still exists on exchange
    positions = self.exchange.fetch_positions([signal.symbol])
    has_exchange_position = any(
        p.get("contracts", 0) > 0 for p in positions
    )

    if not has_exchange_position:
        # Hard SL already fired — just cleanup local state
        self.positions.pop(signal.symbol, None)
        return None

    # Position exists, safe to close
    return self._handle_full_sell(signal.symbol, exit_reason="SOFT_SL")
```

#### 3e. `_move_sl_to_entry()` changes

Replace the current limit-based SL move with cancel + replace stop_market:

```python
def _move_sl_to_entry(self, symbol, new_price=None, new_amount=None):
    pos = self.positions.get(symbol)
    if not pos:
        return False

    target_price = new_price or pos.entry_price
    amount = new_amount or pos.amount

    # Cancel existing SL
    if pos.sl_order_id:
        try:
            self.exchange.cancel_order(pos.sl_order_id, symbol)
        except Exception:
            pass

    # Place new STOP_MARKET
    sl_order = self.exchange.create_order(
        symbol=symbol,
        order_type="stop_market",
        side="SELL",
        amount=amount,
        params={
            "stopPrice": target_price,
            "reduceOnly": True,
        },
    )
    if sl_order:
        pos.sl_order_id = sl_order.get("id")
        return True
    return False
```

#### 3f. Add `tp_order_ids` to `Position` dataclass

```python
@dataclass
class Position:
    # ... existing fields ...
    tp_order_ids: Dict[str, str] = field(default_factory=dict)  # {"TP1": order_id, ...}
```

### 4. `MockExchange` Upgrade

**File:** `app/backtest/mock_exchange.py`

#### 4a. `create_order()` handles all normalized types

Replace the current `create_order()` with one that handles the full vocabulary:

```python
def create_order(self, symbol, order_type, side, amount, price=None, params=None):
    params = params or {}
    amount = to_decimal(amount)
    actual_type = (order_type or "market").lower()
    reduce_only = params.get("reduceOnly", False)

    # MARKET → immediate fill
    if actual_type == "market":
        if reduce_only:
            current_pos = self.positions.get(symbol, Decimal("0"))
            if current_pos <= 0:
                return None  # No position to reduce
            amount = min(amount, current_pos)
        return self._execute_order(symbol, side, amount, ...)

    # LIMIT → pending, fill when price crosses
    if actual_type == "limit":
        return self._place_pending_order(symbol, side, amount,
            trigger_price=price, order_subtype="limit",
            reduce_only=reduce_only, params=params)

    # STOP_MARKET → pending, trigger when price crosses stop
    if actual_type == "stop_market":
        stop_price = to_decimal(params.get("stopPrice", price))
        return self._place_pending_order(symbol, side, amount,
            trigger_price=stop_price, order_subtype="stop_market",
            reduce_only=reduce_only, params=params)

    # STOP_LIMIT → pending, trigger at stop → limit at price
    if actual_type == "stop_limit":
        stop_price = to_decimal(params.get("stopPrice"))
        return self._place_pending_order(symbol, side, amount,
            trigger_price=stop_price, limit_price=price,
            order_subtype="stop_limit",
            reduce_only=reduce_only, params=params)

    # TRAILING_STOP → not needed for backtest MVP
    if actual_type == "trailing_stop":
        callback_rate = Decimal(str(params.get("callbackRate", 1)))
        return self._place_pending_order(symbol, side, amount,
            trigger_price=None, order_subtype="trailing_stop",
            reduce_only=reduce_only, callback_rate=callback_rate,
            params=params)
```

#### 4b. `update_candle()` trigger logic

The trigger logic must distinguish between order types:

| Order | Trigger Condition (SELL side, LONG position) |
|---|---|
| `limit` (TP) | `high >= trigger_price` → fill at `trigger_price` |
| `stop_market` (SL) | `low <= trigger_price` → fill at `trigger_price` |
| `stop_limit` | `low <= stop_price` → becomes limit order at `limit_price` |
| `trailing_stop` | Track highest price, trigger when price drops by `callback_rate%` from peak |

#### 4c. `reduceOnly` enforcement in `update_candle()`

Before executing a triggered pending order:

```python
if order.get("reduce_only"):
    current_pos = self.positions.get(symbol, Decimal("0"))
    if current_pos <= Decimal("0"):
        orders_to_remove.append(order_id)  # Cancel, no position to reduce
        continue
    # Cap amount at current position
    fill_amount = min(to_decimal(order["amount"]), current_pos)
```

This prevents the over-sell → accidental SHORT scenario.

#### 4d. Remove old `place_stop_loss()` and `place_take_profit()` methods

These are replaced by `create_order(order_type="stop_market")` and `create_order(order_type="limit", params={"reduceOnly": True})`.

Keep `update_stop_loss()` as an internal convenience but have it work by cancelling + re-creating a `stop_market` order (same pattern as real exchange).

#### 4e. `cancel_all_orders(symbol)` and `fetch_open_orders(symbol)`

Add these methods to match the interface:

```python
def cancel_all_orders(self, symbol):
    to_cancel = [oid for oid, o in self.pending_orders.items() if o["symbol"] == symbol]
    for oid in to_cancel:
        self.pending_orders.pop(oid)
    return len(to_cancel)

def fetch_open_orders(self, symbol=None):
    orders = []
    for oid, o in self.pending_orders.items():
        if symbol and o["symbol"] != symbol:
            continue
        orders.append({**o, "id": oid})
    return orders
```

### 5. `exchange_factory.py` Changes

The factory must return `IFuturesExchange` instances (not raw CCXT):

```python
def create_exchange(config):
    mode = config.get("bot", {}).get("mode", "mock")
    exchange_name = config.get("exchange", {}).get("name", "binanceusdm")

    if mode == "mock":
        return MockExchange(...)

    if exchange_name in ("binanceusdm", "binance"):
        return BinanceAdapter(config)  # wraps CCXT, implements IFuturesExchange

    # Custom DEX adapters
    return _load_custom_adapter(exchange_name, config)
```

**Key change:** For paper/live Binance, return `BinanceAdapter` (which wraps CCXT internally), not raw CCXT. This ensures all exchanges go through the same `IFuturesExchange` interface.

### 6. `MultiSymbolRunner` Changes

**File:** `app/core/runner.py`

#### 6a. Startup flow

```python
def start(self):
    # 1. Set leverage for all symbols
    for symbol in self.symbols:
        leverage = self.config.get("risk", {}).get("leverage", 1)
        try:
            self.exchange.set_leverage(leverage, symbol)
        except Exception as e:
            logger.warning(f"Failed to set leverage for {symbol}: {e}")

    # 2. Close orphan positions from previous run
    self._cleanup_on_startup()

    # 3. Start stream and threads (existing logic)
    self._start_stream()
    ...
```

#### 6b. Startup cleanup

```python
def _cleanup_on_startup(self):
    """Close all open positions and cancel all orders. Telegram alert."""
    positions = self.exchange.fetch_positions()

    if not positions:
        logger.info("No orphan positions found on startup.")
        return

    logger.warning(f"Found {len(positions)} orphan positions. Closing all...")

    for pos in positions:
        symbol = pos["symbol"]
        amount = Decimal(str(pos.get("contracts", 0)))
        side = "SELL" if pos.get("side") == "long" else "BUY"

        # Cancel all orders first
        try:
            self.exchange.cancel_all_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to cancel orders for {symbol}: {e}")

        # Market close
        try:
            self.exchange.create_order(
                symbol=symbol,
                order_type="market",
                side=side,
                amount=amount,
                params={"reduceOnly": True},
            )
            logger.info(f"Closed orphan position: {symbol} {amount}")
        except Exception as e:
            logger.error(f"Failed to close orphan position {symbol}: {e}")

    # Telegram alert
    if self.telegram:
        self.telegram.send_message(
            f"⚠️ Bot restarted. Closed {len(positions)} orphan positions."
        )
```

#### 6c. TP fill sync in main loop

```python
def _run_symbol_loop(self, symbol):
    # ... existing setup ...

    while self.running.is_set():
        # ... existing candle processing ...

        # After processing candle, sync TP fills
        if symbol in portfolio.positions:
            portfolio.sync_tp_fills(symbol)

        # ... rest of loop ...
```

### 7. `main.py` Changes

Replace signal-only mode with full execution:

```python
from app.services.execution.exchange_factory import create_exchange
from app.core.runner import MultiSymbolRunner
from app.strategies.loader import load_strategy

def main():
    config = load_config()
    mode = config.get("bot", {}).get("mode", "paper")

    # Create exchange via factory (returns IFuturesExchange)
    exchange = create_exchange(config)

    # Create runner with execution
    runner = MultiSymbolRunner(config, exchange, telegram)
    runner.start()
    runner.wait()
```

The `MultiSymbolRunner` already handles per-symbol threads with Strategy + PortfolioManager. `main.py` just wires components and starts.

---

## `.env` Changes

```bash
# Paper mode (Binance Testnet)
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_SECRET_KEY=your_testnet_secret

# Live mode (Binance Mainnet)
BINANCE_API_KEY=your_live_key
BINANCE_SECRET_KEY=your_live_secret
```

Paper mode uses `BINANCE_TESTNET_*` keys exclusively. No fallback to live keys (safety).

---

## Order Lifecycle (End-to-End)

### Entry Flow
```
Strategy emits BUY SignalEvent
  → PM._handle_buy_signal()
    → exchange.create_order("market", "BUY", amount)           # entry
    → exchange.create_order("stop_market", "SELL", amount,     # hard SL
        params={stopPrice, reduceOnly=True})
    → exchange.create_order("limit", "SELL", tp1_amount,       # TP1
        price=tp1_price, params={reduceOnly=True})
    → exchange.create_order("limit", "SELL", tp2_amount,       # TP2
        price=tp2_price, params={reduceOnly=True})
    → exchange.create_order("limit", "SELL", tp3_amount,       # TP3
        price=tp3_price, params={reduceOnly=True})
```

### TP1 Fill Flow
```
After candle close:
  → PM.sync_tp_fills(symbol)
    → exchange.fetch_order(tp1_order_id)  → status="filled"
    → pos.amount -= filled_amount
    → pos.tp1_hit = True
    → PM._move_sl_to_entry(symbol)
      → exchange.cancel_order(old_sl_id)
      → exchange.create_order("stop_market", "SELL", remaining_amount,
          params={stopPrice=entry_price, reduceOnly=True})
    → Resize TP2/TP3 if needed (amount changed)
```

### Soft SL Flow
```
Strategy emits SELL with reason="SOFT_SL" or "MOVE_SL"
  → PM.on_signal()
    → Pre-execution guard: exchange.fetch_positions([symbol])
    → Position exists?
      YES → exchange.cancel_all_orders(symbol)  # cancel SL + remaining TPs
          → exchange.create_order("market", "SELL", pos.amount,
              params={reduceOnly=True})
      NO  → Just cleanup local state (hard SL already fired)
```

### Hard SL Fill Flow
```
Exchange triggers STOP_MARKET server-side
  → Next candle close: PM.sync_tp_fills() or PM.sync_from_exchange()
    → Position no longer on exchange
    → Cancel remaining TP orders
    → Cleanup local Position
```

### Restart Flow
```
Bot starts:
  → exchange.set_leverage(10, symbol) for each symbol
  → exchange.fetch_positions() → found 2 orphan positions
  → For each: cancel_all_orders(symbol) → market close (reduceOnly)
  → Telegram: "⚠️ Bot restarted. Closed 2 orphan positions."
  → Start normal scanning
```

---

## MockExchange ↔ Real Exchange Parity Matrix

| Behavior | MockExchange | BinanceAdapter |
|---|---|---|
| Market fill | Immediate at current/signal price | Immediate at market price |
| Limit TP | Pending, triggers on `high >= price` | Exchange-managed GTC limit |
| Stop Market SL | Pending, triggers on `low <= stopPrice` | Exchange-managed STOP_MARKET |
| `reduceOnly` | Cap amount at position, skip if no position | Exchange enforces natively |
| Partial close | Reduces `pos.amount`, adjusts margin | Exchange reduces position |
| SL after partial TP | Cancel + re-place with new amount | Cancel + re-place with new amount |
| Fee deduction | `balance -= notional * fee_rate` | Exchange deducts from balance |

---

## Files Changed

| File | Action | Description |
|---|---|---|
| `app/services/execution/cex/binance_signal_executor.py` | **DELETE** | Replaced by PortfolioManager |
| `app/services/execution/cex/binance_adapter.py` | **REWRITE** | CCXT-only, implements IFuturesExchange, normalized order types |
| `app/core/interfaces.py` | **EDIT** | Add `fetch_open_orders()`, `cancel_all_orders()` to IFuturesExchange. Update `create_order()` signature with `params`. |
| `app/core/portfolio.py` | **EDIT** | stop_market SL, limit TP placement, sync_tp_fills(), pre-execution guard, reduceOnly on all exits |
| `app/backtest/mock_exchange.py` | **EDIT** | Handle all normalized order types in create_order(), reduceOnly enforcement, remove old place_stop_loss()/place_take_profit() |
| `app/services/execution/exchange_factory.py` | **EDIT** | Return BinanceAdapter (not raw CCXT) for paper/live |
| `app/core/runner.py` | **EDIT** | Startup leverage + orphan cleanup, TP fill sync in loop |
| `app/core/events.py` | No change | SignalEvent already has all needed fields |
| `main.py` | **EDIT** | Wire up exchange factory + runner with execution |
| `.env.example` | **EDIT** | Add BINANCE_TESTNET_API_KEY/SECRET_KEY |
| `tests/` | **ADD** | Tests for normalized order types, reduceOnly, TP/SL lifecycle |

---

## Migration Path for Other Exchanges

When adding a new exchange (e.g., Bybit, OKX, or a custom DEX):

1. Create `app/services/execution/{cex|dex}/{name}_adapter.py`
2. Implement `IFuturesExchange`
3. In `create_order()`, translate the normalized vocabulary to native API:
   - Map `stop_market` → exchange's equivalent
   - Map `reduceOnly` → exchange's param name
   - If exchange doesn't support a type (e.g., DEX without stop orders), raise `NotImplementedError` or simulate locally
4. Add to `EXCHANGE_CONFIG` in factory (for CCXT-based) or auto-discover (for custom)

`PortfolioManager` code stays unchanged — it only speaks normalized types.

---

## Test Plan

| Test | Validates |
|---|---|
| `test_normalized_order_types` | MockExchange handles market, limit, stop_market, stop_limit correctly |
| `test_reduce_only_prevents_short` | Selling more than position with reduceOnly=true caps at position or skips |
| `test_tp_sl_lifecycle` | BUY → SL placed as stop_market → TP1 fills → SL moved to breakeven → TP2 fills |
| `test_soft_sl_race_condition` | Hard SL fires, then soft SL signal arrives → no double-sell |
| `test_startup_cleanup` | Runner finds orphan positions, closes them, alerts Telegram |
| `test_binance_adapter_translation` | Normalized types translate to correct CCXT params |
| `test_partial_tp_with_sl_resize` | After TP1 fill, SL order amount matches remaining position |

---

## Out of Scope (Future Work)

- Real Tick Data backtest engine (separate plan)
- WebSocket user data stream for fill detection (HFT only, not needed for LFT)
- Multi-asset portfolio (currently single position per symbol)
- SHORT positions (current strategy is LONG-only)
- Trailing stop implementation in MockExchange (placeholder only)
