# PortfolioManager

> The sole execution path for all order operations. No component should call exchange methods directly.

---

## Role

`PortfolioManager` is a slim facade/orchestrator between strategy decisions and exchange execution. It delegates to specialized components for each responsibility.

**Location**: `app/trading/portfolio/manager.py`

### Decomposed Structure

| File | Class | Responsibility |
|------|-------|---------------|
| `app/trading/portfolio/manager.py` | `PortfolioManager` | Slim facade — routes signals to delegates, holds positions dict |
| `app/trading/portfolio/trade_executor.py` | `TradeExecutor` | Entry/exit orchestration (market orders, order groups) |
| `app/trading/portfolio/position_sizer.py` | `PositionSizer` | Risk-based position sizing and max position caps |
| `app/trading/portfolio/sl_tp_manager.py` | `SLTPManager` | SL/TP placement, trailing SL, SL moves, TP fill sync |
| `app/trading/portfolio/notification_dispatch.py` | `NotificationDispatcher` | Telegram notification dispatch for trade events |

The facade pattern keeps each component under 600 lines and with a single responsibility. `PortfolioManager` creates the delegates on init and routes calls to them.

---

## Position Sizing

### Risk-Based Sizing (default, `use_risk_based_sizing=True`)

```
risk_capital = initial_capital if use_initial_capital_for_risk else current_balance
risk_amount = risk_capital × risk_per_trade_pct
sl_distance_pct = |entry_price - sl_price| / entry_price
position_notional = risk_amount / sl_distance_pct
position_size = position_notional / entry_price
```

### Max Position Cap

```
max_amount = (balance × max_position_size_pct × leverage) / entry_price
final_size = min(position_size, max_amount)
```

### Edge Cases
- SL distance = 0 → returns 0 (skip trade)
- SL distance < `min_sl_distance_pct` → still uses risk-based sizing, logs warning

---

## Entry Flow (`on_signal()` → `_handle_entry_signal()`)

The entry flow is **side-aware** — it handles both LONG (BUY) and SHORT (SELL) entries using `opposite_side()` for exit orders.

1. Fetch current balance from exchange
2. Calculate position size (risk-based or max-position). Uses `abs(entry_price - sl_price)` for risk distance (direction-agnostic).
3. Set leverage: `exchange.set_leverage(leverage, symbol)`
4. Place market entry: `create_order(symbol, "market", entry_side, amount)`
5. Store `Position` in `self.positions[symbol]` with **signed amount** (positive for LONG, negative for SHORT)
6. Place hard SL: `create_order(symbol, "stop_market", opposite_side(entry_side), amount, params={"stopPrice": sl, "reduceOnly": True})`
7. Place TP orders: `_place_tp_orders()` — limit orders with `side=opposite_side(entry_side)` and `reduceOnly=True`

### LONG Entry Example
- Entry: `market BUY` → SL: `stop_market SELL` → TP: `limit SELL`

### SHORT Entry Example
- Entry: `market SELL` → SL: `stop_market BUY` → TP: `limit BUY`

---

## TP Fill Sync (`sync_tp_fills()`)

Called periodically by the runner to detect filled TP orders:

1. For each TP order ID in `position.tp_order_ids`:
   - `fetch_order(order_id, symbol)`
   - If status = `"closed"` (filled):
     - Adjust `position.amount`: LONG: `amount -= filled`, SHORT: `amount += filled` (reducing negative amount toward zero)
     - Set `position.tp{n}_hit = True`
     - Remove from `tp_order_ids`
2. After TP1 fill: move SL to breakeven via `_move_sl_to_entry()`

---

## SL Movement (`move_stop_loss()`)

1. Cancel existing SL order: `cancel_order(sl_order_id)`
2. Place new SL: `create_order(symbol, "stop_market", position.exit_side, current_amount, params={"stopPrice": new_price, "reduceOnly": True})`
   - LONG: `exit_side = "SELL"`, SHORT: `exit_side = "BUY"`
3. Update `position.sl_order_id` and `position.sl_price`

---

## Partial Close (`execute_partial_close()`)

1. Cancel the specific TP limit order
2. Place market exit for the partial amount: `create_order(symbol, "market", position.exit_side, partial_amount, params={"reduceOnly": True})`
3. Adjust `position.amount` (decrement for LONG, increment toward zero for SHORT)
4. If `new_sl_price` provided: call `move_stop_loss()`

---

## Full Exit (`close_position()`)

1. Cancel all open orders for the symbol: `cancel_all_orders(symbol)`
2. Place market exit: `create_order(symbol, "market", position.exit_side, full_amount, params={"reduceOnly": True})`
3. Remove position from `self.positions`

### Soft SL Exit (`_handle_soft_sl_exit()`)

Special pre-check before soft SL exit:
- Query exchange for actual position existence
- If hard SL already fired (no position on exchange): just clean up local state
- If position exists: proceed with market exit

**SL exit reason logic** (direction-aware):
- LONG: `LOCK_PROFIT` if sl > entry, `BREAKEVEN` if sl == entry, `STOP_LOSS` if sl < entry
- SHORT: `LOCK_PROFIT` if sl < entry, `BREAKEVEN` if sl == entry, `STOP_LOSS` if sl > entry

---

## Position Snapshot (`get_position_snapshot()`)

Returns a read-only `PositionSnapshot` for strategy consumption:

```python
# LONG position example
PositionSnapshot(
    has_position=True,
    symbol="BTC/USDT",
    side="BUY",
    entry_price=Decimal("42150.00"),
    current_sl=Decimal("41500.00"),
    tp1_hit=False, tp2_hit=False, tp3_hit=False,
    lock_profit_triggered=False,
    unrealized_pnl=Decimal("25.50")
)

# SHORT position example
PositionSnapshot(
    has_position=True,
    symbol="BTC/USDT",
    side="SELL",
    entry_price=Decimal("42150.00"),
    current_sl=Decimal("43500.00"),  # SL above entry for SHORT
    tp1_hit=False, tp2_hit=False, tp3_hit=False,
    lock_profit_triggered=False,
    unrealized_pnl=Decimal("30.00")
)
```

---

## Exchange Sync (`sync_from_exchange()`)

On startup or periodically:
- Fetches positions from exchange via `exchange.fetch_positions()`
- Removes local positions that no longer exist on exchange (orphan cleanup)
- Does NOT create new local positions for exchange positions not tracked locally
