# Position Tracking

> How positions are tracked in-memory and synchronized with the exchange.

---

## In-Memory Position State

`PortfolioManager` maintains `self.positions: Dict[str, Position]` keyed by symbol.

### Position Dataclass Fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | str | Trading pair |
| `amount` | Decimal | Current position size — **signed**: positive for LONG, negative for SHORT. Magnitude decreases with partial closes. |
| `entry_price` | Decimal | Entry fill price |
| `side` | str | `"BUY"` (long) or `"SELL"` (short) |
| `timestamp` | datetime | Entry timestamp |
| `tp1_price` | Optional[Decimal] | TP1 target price |
| `tp2_price` | Optional[Decimal] | TP2 target price |
| `tp3_price` | Optional[Decimal] | TP3 target price |
| `sl_price` | Optional[Decimal] | Hard SL price (disaster SL) |
| `lock_profit_price` | Optional[Decimal] | SL moved here after trigger |
| `tp_allocations` | Optional[dict] | TP allocation fractions |
| `sl_order_id` | Optional[str] | Active SL order ID on exchange |
| `tp_order_ids` | Dict[str, str] | Active TP order IDs: `{"TP1": "order_123", ...}` |
| `tp1_hit` | bool | TP1 filled |
| `tp2_hit` | bool | TP2 filled |
| `tp3_hit` | bool | TP3 filled |

---

## Position Lifecycle

```
1. Entry signal    → Position created, stored in self.positions[symbol]
2. Management      → amount decremented on partial closes, SL order_id updated on moves
3. TP fill sync    → tp{n}_hit flags set, amount decremented, tp_order_ids pruned
4. Full exit       → Position removed from self.positions
```

---

## Exchange as Source of Truth

The exchange is the authoritative source for position existence. PortfolioManager syncs in two ways:

### Reconciliation Sync (`sync_from_exchange()`)
- Calls `exchange.fetch_positions(symbols=list(self.positions.keys()))`
- Treats any tracked symbol that the exchange omits — or reports with
  `contracts == 0` — as closed, and pops it from `self.positions`
- Does NOT recreate local tracking for exchange positions not in `self.positions`
- Errors from `fetch_positions()` are swallowed (logged) so a transient API
  blip never wipes valid local state
- Triggered on every signal (`TradeExecutor.on_signal`) **and** at the end of
  every runner-loop iteration when a new candle closes, so a hard SL fill (or
  any out-of-band close) is reconciled within one candle in live mode

### Sim Mode Fast-Path (`register_position_closed_callback`)
- `SimExchange` exposes a callback hook fired the instant
  `sim_fill_handler.close_position_locked()` zeroes a position
- `PortfolioManager.__init__` registers itself if the exchange supports the hook
- This makes sim cleanup synchronous with the SL/TP fill — no polling lag —
  so `StatusWriter` never reports phantom positions to the deploy pipeline

### TP Fill Polling (`sync_tp_fills()`)
- Iterates each TP order ID
- Checks order status via `fetch_order()`
- On fill: updates local position state (amount, hit flags)

### Orphan Detection
On startup, `MultiSymbolRunner` checks for positions on the exchange that aren't tracked locally. These "orphan" positions are logged as warnings. The bot does not auto-close orphans — manual intervention is needed.

---

## PositionSnapshot (Read-Only View)

Strategy receives a read-only snapshot via `get_position_snapshot(symbol)`:

```python
PositionSnapshot(
    has_position: bool,
    symbol: str,
    side: str,
    entry_price: Decimal,
    current_sl: Decimal,
    tp1_hit: bool,
    tp2_hit: bool,
    tp3_hit: bool,
    lock_profit_triggered: bool,  # True if SL moved to lock profit (direction-aware)
    unrealized_pnl: Optional[Decimal]
)
```

The `Position` dataclass also exposes an `exit_side` property that returns `opposite_side(side)` — `"SELL"` for LONG positions, `"BUY"` for SHORT positions. This is used for all exit orders (SL, TP, market close).

The strategy uses the snapshot to decide on management actions (TP checks, SL moves) without accessing mutable state.
