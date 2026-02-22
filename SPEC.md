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

| #   | Decision                                                                                            |
| --- | --------------------------------------------------------------------------------------------------- |
| 1   | Use `PortfolioManager` as sole execution path. Delete `BinanceSignalExecutor`.                      |
| 2   | PM uses **normalized order type vocabulary**. Each adapter translates to exchange-native types.     |
| 3   | SL orders use `stop_market` (not `limit`). All SL/TP orders include `reduceOnly=true`.              |
| 4   | TP1/TP2/TP3 placed as limit orders on exchange.                                                     |
| 5   | Paper mode = Binance Testnet via CCXT `set_sandbox_mode(True)` (not custom `UMFuturesPaperClient`). |
| 6   | LFT polling for fill detection: check order status after each candle close (~15m interval).         |
| 7   | On restart: auto-close all open positions, cancel all orders, Telegram alert, start fresh.          |
| 8   | Set leverage on startup via `exchange.set_leverage()`.                                              |
| 9   | Pre-execution guard: `fetch_positions()` before soft SL exit to prevent double-sell race.           |
| 10  | `MockExchange` upgraded to use same normalized order types as real exchange.                        |

---

## Normalized Order Type Vocabulary

`PortfolioManager` speaks this vocabulary. Every adapter must translate it.

| PM Order Type   | `params`                      | Binance Translation                     | MockExchange Translation                                     |
| --------------- | ----------------------------- | --------------------------------------- | ------------------------------------------------------------ |
| `market`        | `{reduceOnly?}`               | `MARKET`                                | Immediate fill at current price                              |
| `limit`         | `{reduceOnly?, timeInForce?}` | `LIMIT` + `GTC`                         | Pending, fill when price crosses                             |
| `stop_market`   | `{stopPrice, reduceOnly?}`    | `STOP_MARKET` + `stopPrice`             | Pending, trigger when price crosses stop (opposite to limit) |
| `stop_limit`    | `{stopPrice, reduceOnly?}`    | `STOP` + `stopPrice` + `price`          | Pending, trigger → limit order                               |
| `trailing_stop` | `{callbackRate, reduceOnly?}` | `TRAILING_STOP_MARKET` + `callbackRate` | Pending, dynamic trigger                                     |

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

| Order              | Trigger Condition (SELL side, LONG position)                                |
| ------------------ | --------------------------------------------------------------------------- |
| `limit` (TP)       | `high >= trigger_price` → fill at `trigger_price`                           |
| `stop_market` (SL) | `low <= trigger_price` → fill at `trigger_price`                            |
| `stop_limit`       | `low <= stop_price` → becomes limit order at `limit_price`                  |
| `trailing_stop`    | Track highest price, trigger when price drops by `callback_rate%` from peak |

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

| Behavior            | MockExchange                                | BinanceAdapter                    |
| ------------------- | ------------------------------------------- | --------------------------------- |
| Market fill         | Immediate at current/signal price           | Immediate at market price         |
| Limit TP            | Pending, triggers on `high >= price`        | Exchange-managed GTC limit        |
| Stop Market SL      | Pending, triggers on `low <= stopPrice`     | Exchange-managed STOP_MARKET      |
| `reduceOnly`        | Cap amount at position, skip if no position | Exchange enforces natively        |
| Partial close       | Reduces `pos.amount`, adjusts margin        | Exchange reduces position         |
| SL after partial TP | Cancel + re-place with new amount           | Cancel + re-place with new amount |
| Fee deduction       | `balance -= notional * fee_rate`            | Exchange deducts from balance     |

---

## Files Changed

| File                                                    | Action      | Description                                                                                                                   |
| ------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `app/services/execution/cex/binance_signal_executor.py` | **DELETE**  | Replaced by PortfolioManager                                                                                                  |
| `app/services/execution/cex/binance_adapter.py`         | **REWRITE** | CCXT-only, implements IFuturesExchange, normalized order types                                                                |
| `app/core/interfaces.py`                                | **EDIT**    | Add `fetch_open_orders()`, `cancel_all_orders()` to IFuturesExchange. Update `create_order()` signature with `params`.        |
| `app/core/portfolio.py`                                 | **EDIT**    | stop_market SL, limit TP placement, sync_tp_fills(), pre-execution guard, reduceOnly on all exits                             |
| `app/backtest/mock_exchange.py`                         | **EDIT**    | Handle all normalized order types in create_order(), reduceOnly enforcement, remove old place_stop_loss()/place_take_profit() |
| `app/services/execution/exchange_factory.py`            | **EDIT**    | Return BinanceAdapter (not raw CCXT) for paper/live                                                                           |
| `app/core/runner.py`                                    | **EDIT**    | Startup leverage + orphan cleanup, TP fill sync in loop                                                                       |
| `app/core/events.py`                                    | No change   | SignalEvent already has all needed fields                                                                                     |
| `main.py`                                               | **EDIT**    | Wire up exchange factory + runner with execution                                                                              |
| `.env.example`                                          | **EDIT**    | Add BINANCE_TESTNET_API_KEY/SECRET_KEY                                                                                        |
| `tests/`                                                | **ADD**     | Tests for normalized order types, reduceOnly, TP/SL lifecycle                                                                 |

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

| Test                               | Validates                                                                      |
| ---------------------------------- | ------------------------------------------------------------------------------ |
| `test_normalized_order_types`      | MockExchange handles market, limit, stop_market, stop_limit correctly          |
| `test_reduce_only_prevents_short`  | Selling more than position with reduceOnly=true caps at position or skips      |
| `test_tp_sl_lifecycle`             | BUY → SL placed as stop_market → TP1 fills → SL moved to breakeven → TP2 fills |
| `test_soft_sl_race_condition`      | Hard SL fires, then soft SL signal arrives → no double-sell                    |
| `test_startup_cleanup`             | Runner finds orphan positions, closes them, alerts Telegram                    |
| `test_binance_adapter_translation` | Normalized types translate to correct CCXT params                              |
| `test_partial_tp_with_sl_resize`   | After TP1 fill, SL order amount matches remaining position                     |

---

## Out of Scope (Future Work)

- Real Tick Data backtest engine (separate plan)
- WebSocket user data stream for fill detection (HFT only, not needed for LFT)
- Multi-asset portfolio (currently single position per symbol)
- SHORT positions (current strategy is LONG-only)
- Trailing stop implementation in MockExchange (placeholder only)

---

---

# SPEC: Live Paper Trading (Simulation Mode)

> Simulate trading with live Binance market data and fake money. Uses real-time WebSocket streams for price data, a local `PaperExchange` for order simulation, and a rich Telegram bot for monitoring. Distinct from Binance Testnet paper mode (`paper`) — this runs entirely locally with no exchange API required for order placement.

---

## Status Quo

| Component            | Current State                           | Problem                                                          |
| -------------------- | --------------------------------------- | ---------------------------------------------------------------- |
| `config.yaml` `mode` | `mock`, `paper` (testnet), `live`       | No simulation mode using live data without a real exchange       |
| `BinanceAdapter`     | Sends real orders to testnet or mainnet | Cannot simulate fills locally; testnet is flaky and rate-limited |
| `MockExchange`       | Fills from historical OHLCV only        | Not connected to live data; can't run in real-time               |
| Telegram notifier    | Basic signal alerts only                | No position tracking, P&L reporting, or command interface        |

---

## Design Decisions (from interview)

| #   | Decision                                                                                                                                             |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | New bot mode: `sim` (simulation). Added to `config.yaml` alongside `mock`, `paper`, `live`.                                                          |
| 2   | Mode switch is config-only. Restart required to change mode. No runtime live/sim switching.                                                          |
| 3   | `PaperExchange` implements `IFuturesExchange` fully — `PortfolioManager` uses it transparently.                                                      |
| 4   | Market entry orders fill at the **next candle open price** (realistic execution delay).                                                              |
| 5   | SL/TP/lock-profit fills detected via **aggTrade tick data** sampled at 500ms intervals.                                                              |
| 6   | When a candle gaps through both SL and TP: **first tick hit wins** (chronological order).                                                            |
| 7   | aggTrade stream managed by a separate `PaperTradeStreamManager` class (isolated from kline pipeline).                                                |
| 8   | Paper state is **in-memory only** — resets on restart. No SQLite persistence.                                                                        |
| 9   | Risk params (risk_pct, leverage) inherited from live config — no separate paper section.                                                             |
| 10  | Initial balance set in `config.yaml` under `paper_sim.initial_balance`.                                                                              |
| 11  | Fees: **0.05% taker** (market orders — entry, hard SL, soft SL) and **0.02% maker** (limit TP orders).                                               |
| 12  | Funding rates: **fetched from real Binance API** at 00:00, 08:00, 16:00 UTC. Skip silently on failure.                                               |
| 13  | Same position-overlap logic as live: skip signal if symbol already has open paper position.                                                          |
| 14  | Telegram: same bot token as live (separate token can be configured later via `paper_sim.telegram_token`). All paper messages tagged with `📄 PAPER`. |
| 15  | Message format: **bold header line + monospace structured table** (Combined style).                                                                  |
| 16  | `/paper_toggle` pauses/resumes paper signal execution without restarting the bot.                                                                    |

---

## New Bot Mode: `sim`

In `config.yaml`:

```yaml
bot:
  mode: sim # mock | paper | live | sim

paper_sim:
  initial_balance: 10000 # USDT, starting paper balance
  telegram_token: "" # leave blank to reuse bot.telegram_token
  tick_sample_interval_ms: 500 # aggTrade sampling interval
```

`exchange_factory.py` returns `PaperExchange(config)` when `mode == "sim"`.

---

## Architecture

### Component Map

```
Live Kline Stream (BinanceStreamManager)
    │
    ▼
MarketDataStore ──► Strategy.analyze() ──► SignalEvent
                                                │
                                                ▼
                                        PortfolioManager
                                                │ (calls IFuturesExchange API)
                                                ▼
                                         PaperExchange  ◄──── PaperTradeStreamManager
                                         (IFuturesExchange)      (aggTrade 500ms ticks)
                                                │
                                     ┌──────────┴──────────┐
                                     ▼                      ▼
                              PaperTradeState        PaperFundingScheduler
                       (balance, positions,           (Binance REST API, 8h)
                        orders, trade log)
                                     │
                                     ▼
                          PaperTelegramNotifier
                    (rich messages + /paper_* commands)
```

### New Files

| File                          | Purpose                                                                     |
| ----------------------------- | --------------------------------------------------------------------------- |
| `app/paper/exchange.py`       | `PaperExchange` — implements `IFuturesExchange`, simulates all order types  |
| `app/paper/state.py`          | `PaperTradeState`, `PaperOrder`, `PaperPosition`, `ClosedTrade` dataclasses |
| `app/paper/stream_manager.py` | `PaperTradeStreamManager` — aggTrade WebSocket, 500ms sampler               |
| `app/paper/funding.py`        | `PaperFundingScheduler` — fetches and applies real funding rates            |
| `app/paper/notifier.py`       | `PaperTelegramNotifier` — formats and sends all paper trade messages        |
| `app/paper/commands.py`       | Telegram command handlers: `/paper_*`                                       |

### Modified Files

| File                                         | Change                                                                                          |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `app/services/execution/exchange_factory.py` | Add `sim` case → return `PaperExchange(config)`                                                 |
| `app/core/runner.py`                         | On `sim` mode: start `PaperTradeStreamManager` and `PaperFundingScheduler` alongside main loop  |
| `config.yaml`                                | Add `paper_sim` section                                                                         |
| `.env.example`                               | No changes needed (no new API keys — uses existing public stream + REST for funding rates only) |

---

## `PaperTradeState` (Data Model)

```python
# app/paper/state.py

@dataclass
class PaperOrder:
    id: str                          # uuid4
    symbol: str
    order_type: str                  # market, limit, stop_market
    side: str                        # BUY, SELL
    amount: Decimal
    price: Optional[Decimal]         # limit price or None
    stop_price: Optional[Decimal]    # for stop_market
    reduce_only: bool
    status: str                      # pending_open | pending | filled | cancelled
    created_at: float                # epoch
    filled_at: Optional[float]
    fill_price: Optional[Decimal]

@dataclass
class PaperPosition:
    symbol: str
    side: str                        # long (bot is LONG-only)
    amount: Decimal                  # current open contracts
    entry_price: Decimal
    initial_amount: Decimal          # for R-multiple calc
    initial_risk: Decimal            # (entry_price - sl_price) × initial_amount
    sl_order_id: Optional[str]
    tp_order_ids: Dict[str, str]     # {"TP1": order_id, "TP2": ..., "TP3": ...}
    lock_profit_price: Optional[Decimal]
    lock_profit_activated: bool
    tp1_hit: bool
    tp2_hit: bool

@dataclass
class ClosedTrade:
    symbol: str
    entry_price: Decimal
    exit_price: Decimal
    amount: Decimal
    side: str
    pnl_gross: Decimal               # price movement only
    fees_paid: Decimal
    funding_paid: Decimal
    pnl_net: Decimal                 # gross - fees - funding
    r_multiple: Decimal              # pnl_net / initial_risk
    exit_reason: str                 # TP1 | TP2 | TP3 | HARD_SL | CANDLE_SL | TOGGLE_CLOSE | RESET
    opened_at: float
    closed_at: float

class PaperTradeState:
    balance: Decimal
    initial_balance: Decimal
    positions: Dict[str, PaperPosition]    # keyed by symbol
    pending_orders: Dict[str, PaperOrder]  # keyed by order id
    closed_trades: List[ClosedTrade]
    total_fees_paid: Decimal
    total_funding_paid: Decimal
    is_paused: bool                        # controlled by /paper_toggle
```

---

## `PaperExchange` (Order Simulation Engine)

### Interface

`PaperExchange` implements `IFuturesExchange` exactly. `PortfolioManager` calls it identically to `BinanceAdapter`.

### `create_order()` behavior

| order_type                            | behavior                                                                                                              |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `market` (entry, no `reduceOnly`)     | Status set to `pending_open`. Fills at **next candle open price** when `on_kline_open(symbol, open_price)` is called. |
| `market` (with `reduceOnly=True`)     | Closes position immediately at **current mid-price** (latest tick). Used for soft SL / forced close.                  |
| `limit` (TP, `reduceOnly=True`)       | Stored as `pending`. Filled by tick scanner when sampled price ≥ limit_price (SELL side).                             |
| `stop_market` (SL, `reduceOnly=True`) | Stored as `pending`. Filled by tick scanner when sampled price ≤ stop_price (SELL side).                              |

### `on_kline_open(symbol, open_price)`

Called by `MultiSymbolRunner` at the start of each new candle (extracted from kline stream).

```python
def on_kline_open(self, symbol: str, open_price: Decimal):
    """Fill pending_open market orders (entry) at candle open price."""
    for order_id, order in list(self.state.pending_orders.items()):
        if order.symbol == symbol and order.status == "pending_open":
            self._execute_fill(order, fill_price=open_price)
```

### `on_tick(symbol, price, timestamp)`

Called by `PaperTradeStreamManager` at 500ms intervals with the latest sampled aggTrade price.

```python
def on_tick(self, symbol: str, price: Decimal, timestamp: float):
    """Scan all pending orders for fills. Processes in insertion order (FIFO)."""
    for order_id, order in list(self.state.pending_orders.items()):
        if order.symbol != symbol or order.status != "pending":
            continue

        filled = False

        if order.order_type == "stop_market" and order.side == "SELL":
            # Hard SL: fill when price drops to or below stop_price
            if price <= order.stop_price:
                self._execute_fill(order, fill_price=order.stop_price)
                filled = True

        elif order.order_type == "limit" and order.side == "SELL":
            # TP: fill when price rises to or above limit_price
            if price >= order.price:
                self._execute_fill(order, fill_price=order.price)
                filled = True

        if filled:
            self._post_fill_hook(order)
```

### `_execute_fill()` internals

1. Mark order `status = "filled"`, record `fill_price` and `filled_at`
2. Calculate fee: taker (0.05%) for `market` and `stop_market`, maker (0.02%) for `limit`
3. Calculate P&L and update `PaperTradeState.balance`
4. Update or close `PaperPosition`
5. Emit fill event → `PaperTelegramNotifier.on_fill(order, position)`

### Lock-profit handling

Lock-profit is triggered by the **strategy** — it emits `MOVE_SL_LOCK_PROFIT` **immediately on the tick** that reaches or exceeds `lock_profit_price` (no candle close wait). `PortfolioManager` receives this signal and calls `exchange.cancel_order(old_sl_id)` + `exchange.create_order("stop_market", ...)` with the new SL price (breakeven). `PaperExchange` handles this like any other cancel + replace — the new `stop_market` order is then monitored by the tick scanner.

### `fetch_positions()`, `fetch_balance()`, `fetch_open_orders()`

Return data from `PaperTradeState` directly — no Binance API call needed.

```python
def fetch_positions(self, symbols=None):
    return [
        {"symbol": s, "contracts": float(p.amount), "side": "long",
         "entryPrice": float(p.entry_price), "unrealizedPnl": float(self._calc_upnl(p))}
        for s, p in self.state.positions.items()
        if symbols is None or s in symbols
    ]

def fetch_balance(self):
    return {"USDT": {"free": float(self.state.balance), "total": float(self.state.balance)}}
```

### `set_leverage()`, `cancel_order()`, `cancel_all_orders()`

`set_leverage()` — no-op (logs it, inherits leverage from config).
`cancel_order(id)` — remove from `pending_orders`.
`cancel_all_orders(symbol)` — remove all pending orders for symbol.

---

## `PaperTradeStreamManager` (Tick Sampler)

### Responsibility

- Subscribe to Binance `aggTrade` WebSocket stream for each configured symbol
- Sample one price per 500ms window (take the **last** trade price in each window)
- Call `PaperExchange.on_tick(symbol, price, timestamp)` on each sample

### Implementation

```python
class PaperTradeStreamManager:
    """
    Subscribes to Binance aggTrade streams.
    Samples 1 price per 500ms per symbol, forwards to PaperExchange.
    Runs in a dedicated thread, isolated from kline pipeline.
    """

    def __init__(self, symbols: List[str], paper_exchange: PaperExchange):
        self._symbols = symbols
        self._exchange = paper_exchange
        self._buffers: Dict[str, Decimal] = {}   # last price seen per symbol
        self._last_sample: Dict[str, float] = {} # last sample timestamp per symbol
        self._ws = None

    def start(self):
        """Connect to Binance aggTrade combined stream."""
        streams = "/".join(f"{s.lower().replace('/', '')}@aggTrade" for s in self._symbols)
        url = f"wss://fstream.binance.com/stream?streams={streams}"
        # ... websocket-client connection in background thread ...

    def _on_message(self, msg):
        symbol = msg["s"]  # e.g. "BTCUSDT"
        price = Decimal(msg["p"])
        now = time.time()

        self._buffers[symbol] = price  # always update latest price

        last = self._last_sample.get(symbol, 0)
        if now - last >= 0.5:  # 500ms elapsed
            self._last_sample[symbol] = now
            self._exchange.on_tick(symbol, price, now)
```

### Reconnect behavior

On disconnect: exponential backoff reconnect (1s, 2s, 4s, max 30s). Tick buffer is flushed (any pending prices in the 500ms window are discarded — safe because ticks are sampled, not accumulated).

---

## `PaperFundingScheduler`

### Responsibility

Apply Binance USDT-M funding payments to open paper positions at 00:00, 08:00, 16:00 UTC.

### Implementation

```python
class PaperFundingScheduler:
    """
    Schedules funding rate checks at 00:00, 08:00, 16:00 UTC.
    Fetches real rates from Binance REST API (public endpoint, no auth needed).
    """
    FUNDING_INTERVAL_HOURS = 8
    FUNDING_ENDPOINT = "https://fapi.binance.com/fapi/v1/premiumIndex"

    def apply_funding(self, state: PaperTradeState):
        for symbol, position in state.positions.items():
            try:
                rate = self._fetch_funding_rate(symbol)  # Decimal, e.g. Decimal("0.0001")
            except Exception as e:
                logger.warning(f"Funding rate fetch failed for {symbol}: {e}. Skipping.")
                continue

            notional = position.amount * self._get_last_price(symbol)
            payment = notional * rate  # positive = paid by longs (deducted)
            state.balance -= payment
            state.total_funding_paid += payment

            self._notifier.on_funding(symbol, rate, payment, state.balance)
```

**Failure behavior**: Log warning + skip. No retry, no cached rate fallback.

**API endpoint used**: `GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT` — public, no API key required.

---

## Fee Calculation

| Order Type                           | Fee Rate    | Applied To                   |
| ------------------------------------ | ----------- | ---------------------------- |
| `market` (entry BUY)                 | 0.05% taker | `entry_price × amount`       |
| `stop_market` (hard SL)              | 0.05% taker | `fill_price × amount`        |
| `market` with `reduceOnly` (soft SL) | 0.05% taker | `fill_price × amount`        |
| `limit` (TP1, TP2, TP3)              | 0.02% maker | `fill_price × filled_amount` |

Fees are deducted from `PaperTradeState.balance` at fill time. They are recorded separately in `ClosedTrade.fees_paid` and `state.total_fees_paid`.

---

## Fill Simulation Rules (Complete)

| Event                         | Trigger                                       | Fill Price        | Fee         |
| ----------------------------- | --------------------------------------------- | ----------------- | ----------- |
| Entry (LONG)                  | Next candle open                              | Candle open price | 0.05% taker |
| Hard SL                       | Tick ≤ stop_price                             | `stop_price`      | 0.05% taker |
| TP1 / TP2 / TP3               | Tick ≥ limit_price                            | `limit_price`     | 0.02% maker |
| Soft SL (candle close signal) | Candle close price ≤ soft_sl_price            | Latest tick price | 0.05% taker |
| Lock-profit SL move           | Strategy emits on tick ≥ lock_profit_price     | N/A (SL repriced) | No fee      |
| SL gap: tick skips SL and TP  | SL order hit first (chronological tick order) | `stop_price`      | 0.05% taker |

**Gap scenario**: If a candle's price movement causes both SL and TP to be within range, the **first tick sample to cross either level wins**. Since the tick scanner processes orders in chronological order and exits immediately on first fill, whichever level was crossed first in the 500ms sample sequence takes priority. This correctly handles the worst-case (SL then TP gap) without special logic.

---

## Telegram Integration

### Bot Configuration

```yaml
paper_sim:
  telegram_token: "" # blank = reuse bot.telegram_token from .env
```

If `telegram_token` is blank, `PaperTelegramNotifier` uses the same bot token as live mode. All paper messages are prefixed with `📄 PAPER` to distinguish them visually.

### Message Formats

All messages use **bold header + monospace table** (Telegram HTML parse mode).

#### Entry

```
📄 PAPER | 🟢 LONG ENTERED — BTCUSDT

Symbol:      BTCUSDT
Side:        LONG
Entry:       $95,420.00
Size:        0.013 BTC  ($1,240.46)
Leverage:    10x  (Notional: $12,404.60)

SL (Hard):   $94,100.00  (−1.39%)  Risk: −$140.00
TP1 (33%):   $97,200.00  (+1.87%)  Reward: +$182.80
TP2 (50%):   $99,500.00  (+4.28%)  Reward: +$314.50
TP3 (all):   $102,000.00 (+6.91%)  Reward: +$476.00
Lock Profit: $96,100.00  → SL moves to entry on tick hit

Balance:     $10,000.00  (margin used: $1,240.46)
```

#### TP1 Hit

```
📄 PAPER | ✅ TP1 HIT — BTCUSDT LONG

Fill:        $97,200.00
Closed:      0.0043 BTC ($417.96)  [33% of position]
Gross P&L:   +$60.90
Fee (maker): −$0.08  (0.02%)
Net P&L:     +$60.82

SL moved:    $94,100 → $95,420 (breakeven)
Remaining:   0.0087 BTC ($845.00)

Session P&L: +$60.82  |  Balance: $10,060.82
```

#### TP2 Hit

```
📄 PAPER | ✅ TP2 HIT — BTCUSDT LONG

Fill:        $99,500.00
Closed:      0.0044 BTC ($437.80)  [50% of remaining]
Gross P&L:   +$179.40
Fee (maker): −$0.09
Net P&L:     +$179.31

Remaining:   0.0043 BTC ($427.65)

Session P&L: +$240.13  |  Balance: $10,240.13
```

#### TP3 Hit (full close)

```
📄 PAPER | ✅ TP3 HIT — BTCUSDT LONG (CLOSED)

Fill:        $102,000.00
Closed:      0.0043 BTC ($438.60)  [all remaining]
Gross P&L:   +$227.30
Fee (maker): −$0.09
Net P&L:     +$227.21

─────────────────────────────────
Total Trade P&L:  +$467.34  (3.34R)
Fees Paid:        −$0.26
Duration:         4h 23m

Session P&L: +$467.34  |  Balance: $10,467.34
```

#### Hard SL Hit

```
📄 PAPER | 🛑 HARD SL HIT — BTCUSDT LONG

Fill:        $94,100.00
Closed:      0.013 BTC  ($1,223.30)
Gross P&L:   −$140.00
Fee (taker): −$0.61  (0.05%)
Net P&L:     −$140.61

─────────────────────────────────
Trade P&L:   −$140.61  (−1.00R)

Session P&L: −$140.61  |  Balance: $9,859.39
```

#### Candle SL Hit (soft SL)

```
📄 PAPER | 🟡 CANDLE SL HIT — BTCUSDT LONG

Exit:        $94,850.00  (close below soft SL level)
Closed:      0.013 BTC at market
Gross P&L:   −$73.20
Fee (taker): −$0.61
Net P&L:     −$73.81

Trade P&L:   −$73.81  (−0.53R)

Session P&L: −$73.81  |  Balance: $9,926.19
```

#### Funding Payment Applied

```
📄 PAPER | 💸 FUNDING — BTCUSDT

Rate:       +0.0100%  (longs pay)
Notional:   $12,404.60
Payment:    −$1.24

Balance:    $10,467.34 → $10,466.10
```

### Telegram Commands

| Command          | Description                     | Behavior                                                                                                                                                     |
| ---------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/paper_status`  | Current state snapshot          | Balance, unrealized P&L, open positions (entry, size, SL, TP), paused status                                                                                 |
| `/paper_reset`   | Reset to initial balance        | Requires confirmation reply within 30s. Closes all open paper positions at latest tick price (no fee). Clears trade history. Sends summary of session wiped. |
| `/paper_toggle`  | Pause / resume signal execution | Toggles `state.is_paused`. When paused, strategy signals are ignored. Open positions are still monitored for SL/TP fills.                                    |
| `/paper_history` | Trade log for this session      | List of all closed trades: symbol, entry→exit, exit reason, net P&L, R-multiple. Max 20 most recent.                                                         |
| `/paper_winrate` | Performance statistics          | See breakdown below                                                                                                                                          |

#### `/paper_winrate` Output

```
📄 PAPER | SESSION STATS

Trades:      12 closed  (3 open)
Win Rate:    75.0%  (9W / 3L)

Exit Breakdown:
  TP1:       4 trades  (33.3%)
  TP2:       3 trades  (25.0%)
  TP3:       2 trades  (16.7%)
  Hard SL:   2 trades  (16.7%)
  Candle SL: 1 trade   ( 8.3%)

Avg R-multiple:  +1.47R
Best trade:      +3.34R  (BTCUSDT TP3)
Worst trade:     −1.00R  (ETHUSDT Hard SL)

Session P&L:  +$523.40  (gross)
Fees paid:    −$14.20
Funding paid: −$3.40
Net P&L:      +$505.80  (+5.06%)

Balance:  $10,000.00 → $10,505.80
```

---

## `/paper_reset` Confirmation Flow

```
User: /paper_reset

Bot: ⚠️ PAPER RESET CONFIRMATION
     This will wipe all paper trades and reset balance to $10,000.00.
     Current session: 12 trades, Net P&L: +$505.80

     Reply /paper_reset confirm within 30 seconds to proceed.

User: /paper_reset confirm

Bot: ✅ Paper account reset.
     Session summary: 12 trades | Net P&L: +$505.80 | Win rate: 75%
     Balance reset to $10,000.00. Fresh session started.
```

If no confirmation within 30s, the reset is automatically cancelled (no notification needed).

---

## `/paper_toggle` Pause Behavior

When paused (`state.is_paused = True`):

- **Signals are ignored**: `PortfolioManager` checks `exchange.is_paused()` before executing. If paused, log signal but skip.
- **Active monitoring continues**: Tick scanner still calls `on_tick()`. Open positions are still monitored for SL/TP fills.
- **Funding still applied**: Scheduler is not affected.
- **All commands still respond**: `/paper_status`, etc., work normally.

Toggle message:

```
📄 PAPER | ⏸ PAUSED
Signal execution suspended. Open positions still monitored.
Use /paper_toggle to resume.
```

```
📄 PAPER | ▶️ RESUMED
Signal execution active.
```

---

## `MultiSymbolRunner` Changes (sim mode)

```python
def start(self):
    if self.config["bot"]["mode"] == "sim":
        # Start aggTrade stream manager
        self._paper_stream = PaperTradeStreamManager(
            symbols=self.symbols,
            paper_exchange=self.exchange  # PaperExchange instance
        )
        self._paper_stream.start()

        # Start funding scheduler
        self._funding_scheduler = PaperFundingScheduler(
            state=self.exchange.state,
            notifier=self.exchange.notifier
        )
        self._funding_scheduler.start()  # runs in background thread

    # ... existing kline stream startup ...
```

In the per-symbol loop, extract the candle open price and forward to `PaperExchange`:

```python
def _run_symbol_loop(self, symbol):
    prev_open_time = None

    while self.running.is_set():
        candle = self.data_store.get_latest_candle(symbol)

        # Detect new candle open (open_time changed)
        if candle.open_time != prev_open_time:
            self.exchange.on_kline_open(symbol, candle.open)
            prev_open_time = candle.open_time

        # ... existing strategy + PM logic ...
```

---

## `exchange_factory.py` Changes

```python
def create_exchange(config):
    mode = config.get("bot", {}).get("mode", "mock")

    if mode == "mock":
        return MockExchange(...)

    if mode == "sim":
        from app.paper.exchange import PaperExchange
        return PaperExchange(config)

    if mode in ("paper", "live"):
        return BinanceAdapter(config)

    raise ValueError(f"Unknown bot mode: {mode}")
```

---

## Files Changed

| File                                         | Action     | Description                                                                                |
| -------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------ |
| `app/paper/__init__.py`                      | **CREATE** | Package init                                                                               |
| `app/paper/exchange.py`                      | **CREATE** | `PaperExchange` — full `IFuturesExchange` implementation                                   |
| `app/paper/state.py`                         | **CREATE** | `PaperTradeState`, `PaperOrder`, `PaperPosition`, `ClosedTrade` dataclasses                |
| `app/paper/stream_manager.py`                | **CREATE** | `PaperTradeStreamManager` — aggTrade WebSocket + 500ms sampler                             |
| `app/paper/funding.py`                       | **CREATE** | `PaperFundingScheduler` — 8h funding rate application                                      |
| `app/paper/notifier.py`                      | **CREATE** | `PaperTelegramNotifier` — all message formats                                              |
| `app/paper/commands.py`                      | **CREATE** | `/paper_*` command handlers                                                                |
| `app/services/execution/exchange_factory.py` | **EDIT**   | Add `sim` case                                                                             |
| `app/core/runner.py`                         | **EDIT**   | Start paper stream + funding scheduler on `sim` mode; forward candle open to PaperExchange |
| `config.yaml`                                | **EDIT**   | Add `paper_sim` section                                                                    |
| `tests/test_paper_exchange.py`               | **CREATE** | Unit tests for fill simulation, fee calculation, R-multiple                                |
| `tests/test_paper_tick_scanner.py`           | **CREATE** | Unit tests for tick scanner ordering (gap scenarios, SL-before-TP)                         |

---

## Test Plan

| Test                                      | Validates                                                                                 |
| ----------------------------------------- | ----------------------------------------------------------------------------------------- |
| `test_market_entry_fills_at_next_open`    | Market entry order status `pending_open` → fills at `on_kline_open()` call                |
| `test_limit_tp_fills_on_tick`             | `on_tick(price=tp_price)` → TP1 fills at `tp_price`, fee is 0.02% maker                   |
| `test_stop_market_sl_fills_on_tick`       | `on_tick(price=sl_price)` → SL fills at `sl_price`, fee is 0.05% taker                    |
| `test_gap_sl_before_tp`                   | Tick sequence crosses SL price before TP price → SL fills, TP cancelled                   |
| `test_reduce_only_no_position`            | `reduceOnly` order when no position exists → order silently cancelled                     |
| `test_partial_tp1_reduces_position`       | TP1 fill → position.amount reduced by 33%, SL cancel+replace with new amount              |
| `test_lock_profit_sl_cancel_replace`      | Strategy emits MOVE_SL_LOCK_PROFIT on tick ≥ lock_profit_price → PM cancels old SL, creates new stop_market at entry (breakeven) |
| `test_funding_deducts_from_balance`       | `apply_funding()` with known rate → balance decremented, `ClosedTrade` not created        |
| `test_funding_api_failure_skips`          | API raises exception → balance unchanged, warning logged                                  |
| `test_paper_reset_wipes_state`            | After reset: balance = initial_balance, positions = {}, closed_trades = []                |
| `test_toggle_pauses_signal_execution`     | `is_paused=True` → PortfolioManager skips signal, no orders created                       |
| `test_toggle_does_not_stop_sl_monitoring` | While paused: `on_tick()` still fires, SL fills normally                                  |
| `test_r_multiple_calculation`             | Closed trade with known P&L and initial_risk → correct R-multiple                         |
| `test_fee_taker_on_hard_sl`               | Hard SL fill → fee = 0.05% of fill_price × amount                                         |
| `test_fee_maker_on_tp`                    | TP fill → fee = 0.02% of fill_price × amount                                              |

---

## Out of Scope

- Persistence across restarts (in-memory only by design)
- SHORT position simulation (strategy is LONG-only)
- Binance Testnet (`paper` mode) is unchanged — `sim` is a separate mode
- Web dashboard for paper trading state (Telegram is the sole monitoring interface)
- Partial fill simulation (all fills are complete fills at trigger price)
- Order book depth / market impact simulation
- Multiple simultaneous paper positions per symbol
