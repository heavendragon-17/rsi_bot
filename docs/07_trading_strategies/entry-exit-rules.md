# Entry & Exit Rules

> Detailed entry state machine, SL/TP placement logic, and position management for `rsi_no_retest`.

---

## Entry State Machine

```
SCANNING ──[reclaim + pullback detected]──► CONFIRMING ──[RSI spread met]──► OpenPosition
    ▲                                           │
    └───────────[RSI spread fails]──────────────┘
```

### SCANNING → CONFIRMING

Two conditions checked simultaneously (within the same candle):

**1. Reclaim Detection** (`_detect_reclaim()`):
- Candle at `[-3]` had `close <= EMA21` (was below)
- Candle at `[-2]` had `close > EMA21` (crossed above)
- Both candles must be closed (not the live candle at `[-1]`)

**2. Pullback Filter** (`_pullback_filter()`):
- In the lookback window `[-(lookback+1):-1]` (default 30 candles before current)
- Count candles where `close > EMA21`
- Must be `<= nr_max_above_ema21` (default 3)
- This ensures the reclaim happens after a genuine pullback, not random noise

If both pass, immediately proceed to CONFIRMING (no wait for next candle).

### CONFIRMING → OpenPosition

**RSI Spread Check**:
- `(RSI_EMA9 - RSI_WMA45) >= nr_rsi_spread_min` (default 2.5)
- If fails → reset to SCANNING
- If passes → compute SL/TP and emit `OpenPosition`

---

## SL Computation

Three modes controlled by `nr_sl_mode`:

| Mode | Computation | Best For |
|------|-------------|----------|
| `lowest_close` | `min(close)` over lookback window | Conservative, avoids wick noise |
| `lowest_wick` | `min(low)` over lookback window | Tighter, uses wicks |
| `rsi_ema9` | `indicators.calculate_price_at_rsi(df, rsi_ema9_value)` | RSI-based, dynamic |

After computation:
- Optional buffer: `sl = sl × (1 - sl_buffer_pct)`
- **Soft SL** = computed value (strategy-monitored, candle-close based)
- **Hard SL** = `entry - disaster_sl_multiplier × (entry - soft_sl)` (exchange stop_market)

---

## TP Computation

TP levels are placed at multiples of risk distance from entry:

```
risk = entry - soft_sl
tp1 = entry + nr_tp1_rr × risk    (default: entry + 1.0 × risk)
tp2 = entry + nr_tp2_rr × risk    (default: entry + 2.0 × risk)
tp3 = entry + nr_tp3_rr × risk    (default: entry + 3.0 × risk)
```

### Dynamic Allocations

Based on `nr_tp_count`:

| tp_count | TP1 | TP2 | TP3 |
|----------|-----|-----|-----|
| 1 | 100% | — | — |
| 2 | `tp1_close_pct` (50%) | 100% remaining | — |
| 3 | `tp1_close_pct` (50%) | `tp2_close_pct` (50% of remaining) | 100% remaining |

---

## Position Management (Exit Logic)

Checked every candle in this priority order:

### 1. Pending Candle SL (highest priority)
If `pending_candle_sl=True` in context (set on previous candle):
- Exit at current candle's `open` price
- Emit `ClosePosition(reason="CLOSE_BY_CANDLE_SL")`
- Reset to SCANNING

### 2. TP3 Check
If `high >= tp3_price` and TP3 not yet hit:
- Emit `PartialClose(tp_level="TP3")`
- Full exit (100% remaining)
- Reset to SCANNING

### 3. TP2 Check
If `high >= tp2_price` and TP2 not yet hit:
- Emit `PartialClose(tp_level="TP2")`
- Close `tp2_close_pct` of remaining
- Keep current SL

### 4. TP1 Check
If `high >= tp1_price` and TP1 not yet hit:
- Emit `PartialClose(tp_level="TP1", new_sl_price=lock_profit_price)`
- Close `tp1_close_pct` of position
- Move SL to `lock_profit_price` (entry + 0.2R by default)

### 5. Breakeven / Lock Profit Trigger
If `high >= entry + nr_move_sl_rr × risk` and SL not yet moved:
- Emit `MoveSL(new_sl_price=lock_profit_price)`
- SL moves to `entry + nr_lock_profit_rr × risk`

### 6. Soft SL (candle-close based)
If `close <= soft_sl_price`:
- Set `pending_candle_sl=True` in context
- Emit `DoNothing` (exit happens next candle at open)

This 2-candle pattern prevents false exits from wick-only touches. The exit happens at the next candle's open price, simulating a realistic market exit.

---

## Context Meta Keys

The strategy stores these in `ContextSnapshot.meta`:

| Key | Type | Description |
|-----|------|-------------|
| `entry_price` | Decimal | Entry price |
| `sl_price` | Decimal | Hard/disaster SL price |
| `soft_sl_price` | Decimal | Soft SL (candle-close monitored) |
| `original_soft_sl` | Decimal | Original soft SL before any moves |
| `disaster_sl_price` | Decimal | Hard SL on exchange |
| `tp1_price` | Decimal | TP1 target |
| `tp2_price` | Decimal | TP2 target |
| `tp3_price` | Decimal | TP3 target |
| `lock_profit_price` | Decimal | SL moved here after trigger |
| `moved_sl_to_entry` | bool | Whether SL has been moved |
| `pending_candle_sl` | bool | Candle SL flagged, exit next candle |
| `rsi_spread` | float | RSI spread at entry |
| `sl_mode` | str | SL mode used |
| `tp_allocations` | dict | TP allocation fractions |

TP hit flags (`tp1_hit`, `tp2_hit`, `tp3_hit`) come from `PositionSnapshot` (PortfolioManager is source of truth), not from context.
