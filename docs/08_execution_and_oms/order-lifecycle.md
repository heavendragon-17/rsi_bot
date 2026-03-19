# Order Lifecycle

> Order types, vocabulary, and the flow from strategy action to exchange execution.

---

## Normalized Order Vocabulary

All internal code uses these 5 order types. Exchange adapters translate to native formats.

| Order Type | Usage | CCXT Mapping | Key Params |
|------------|-------|-------------|------------|
| `market` | Entry orders, emergency exits | `MARKET` | — |
| `limit` | TP orders | `LIMIT` | `price`, `reduceOnly=True`, `timeInForce=GTC` |
| `stop_market` | Hard SL (disaster SL) | `STOP_MARKET` | `stopPrice`, `reduceOnly=True` |
| `stop_limit` | Reserved (not currently used) | `STOP` | `stopPrice`, `price` |
| `trailing_stop` | Reserved (not currently used) | `TRAILING_STOP_MARKET` | `callbackRate` |

**Critical rule**: All exit orders (TP, SL) use `reduceOnly=True` in params. This prevents accidental position opening if the position was already closed.

---

## `create_order()` Signature

```python
IExchange.create_order(
    symbol: str,          # e.g. "BTC/USDT"
    order_type: str,      # "market", "limit", "stop_market"
    side: str,            # "BUY" or "SELL"
    amount: Decimal,      # Position size in base currency
    price: Decimal = None,  # Required for limit orders
    params: dict = None   # {"reduceOnly": True, "stopPrice": ...}
)
```

---

## Order Flow

All flows use `entry_side` for entry and `exit_side = opposite_side(entry_side)` for exits. LONG: entry=BUY, exit=SELL. SHORT: entry=SELL, exit=BUY.

### Entry (LONG)

```
Strategy: OpenPosition(side="BUY")
    → Engine: _action_to_signal() → SignalEvent(signal_type="BUY")
    → PortfolioManager: on_signal()
        → _calculate_position_size()
        → exchange.set_leverage(leverage, symbol)
        → exchange.create_order(symbol, "market", "BUY", amount)     ← Entry
        → exchange.create_order(symbol, "stop_market", "SELL", amount, params={"stopPrice": sl, "reduceOnly": True})  ← Hard SL
        → exchange.create_order(symbol, "limit", "SELL", tp1_amount, tp1_price, params={"reduceOnly": True})  ← TP1
        → exchange.create_order(symbol, "limit", "SELL", tp2_amount, tp2_price, params={"reduceOnly": True})  ← TP2
        → exchange.create_order(symbol, "limit", "SELL", tp3_amount, tp3_price, params={"reduceOnly": True})  ← TP3
```

### Entry (SHORT)

```
Strategy: OpenPosition(side="SELL")
    → Engine: _action_to_signal() → SignalEvent(signal_type="SELL")
    → PortfolioManager: on_signal()
        → _calculate_position_size()
        → exchange.set_leverage(leverage, symbol)
        → exchange.create_order(symbol, "market", "SELL", amount)     ← Entry
        → exchange.create_order(symbol, "stop_market", "BUY", amount, params={"stopPrice": sl, "reduceOnly": True})  ← Hard SL
        → exchange.create_order(symbol, "limit", "BUY", tp1_amount, tp1_price, params={"reduceOnly": True})  ← TP1
        → exchange.create_order(symbol, "limit", "BUY", tp2_amount, tp2_price, params={"reduceOnly": True})  ← TP2
        → exchange.create_order(symbol, "limit", "BUY", tp3_amount, tp3_price, params={"reduceOnly": True})  ← TP3
```

### SL Movement

```
Strategy: MoveSL action
    → PortfolioManager: move_stop_loss()
        → exchange.cancel_order(old_sl_order_id)
        → exchange.create_order(symbol, "stop_market", exit_side, amount, params={"stopPrice": new_sl, "reduceOnly": True})
```

### Partial Close (TP Hit)

```
Strategy: PartialClose action
    → PortfolioManager: execute_partial_close()
        → exchange.cancel_order(tp_order_id)
        → exchange.create_order(symbol, "market", exit_side, partial_amount, params={"reduceOnly": True})
        → move_stop_loss() if new_sl_price provided
```

### Full Exit

```
Strategy: ClosePosition action
    → PortfolioManager: close_position()
        → exchange.cancel_all_orders(symbol)
        → exchange.create_order(symbol, "market", exit_side, full_amount, params={"reduceOnly": True})
```

---

## Order Status Checking

- `fetch_order(order_id, symbol)` — check individual order status
- `fetch_open_orders(symbol)` — list all open orders
- `sync_tp_fills(symbol)` — PortfolioManager polls TP order statuses to detect fills
