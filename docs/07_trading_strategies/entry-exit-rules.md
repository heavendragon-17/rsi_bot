# Entry & Exit Rules

> Detailed entry state machine, SL/TP placement logic, and position management for `rsi_no_retest` and `rsi_momentum`.

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
- **Soft SL** = computed value (level at which the SL is "real")
- **Hard SL** depends on `sl_trigger_mode`:
  - `candle_close` (default): `entry - disaster_sl_multiplier × (entry - soft_sl)` — soft SL is monitored in-strategy on candle close, hard SL on the exchange acts as a safety net.
  - `touch`: `hard_sl = soft_sl` — exchange stop sits at the soft SL level and fires on touch. Strategy skips the candle-close detection.

---

## SL Trigger Mode (`sl_trigger_mode`)

| Mode | Behavior | Tradeoff |
|------|----------|----------|
| `candle_close` (default) | Strategy waits for the candle to *close* through `soft_sl`, then exits at the next candle's open (`CLOSE_BY_CANDLE_SL`). Exchange stop is at `disaster_sl` (wider). | Filters wick noise; pays slightly more on the exit since fill is at the next open, not the SL price. |
| `touch` | Exchange stop is placed at `soft_sl` and triggers as soon as price touches it. Strategy does not flag `pending_candle_sl`. | Tighter and faster fills; vulnerable to wick-through stop hunts. |

The lock-profit `MoveSL` step still applies in both modes (it just relocates the exchange stop).

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

### 6. Max Holding Period (force-close)
If `max_holding_enabled` is `True` and the position has been open for at least `max_holding_bars` candles:
- Emit `ClosePosition(reason="MAX_HOLDING_PERIOD", price=close)` (market exit at the current candle's close)
- Reset to SCANNING

`bars_held` increments once per `analyze()` call while a position is open. Defaults: `max_holding_enabled=True`, `max_holding_bars=96` (24 hours on 15m). Toggle `max_holding_enabled` off to disable the check entirely.

### 7. Soft SL (candle-close based)
**Active only when `sl_trigger_mode == "candle_close"`.** If `close <= soft_sl_price`:
- Set `pending_candle_sl=True` in context
- Emit `DoNothing` (exit happens next candle at open)

This 2-candle pattern prevents false exits from wick-only touches. The exit happens at the next candle's open price, simulating a realistic market exit.

When `sl_trigger_mode == "touch"`, this step is skipped — the exchange-level stop sits at `soft_sl_price` and fires on touch.

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
| `bars_held` | int | Candles since entry; force-close fires at `max_holding_bars` |
| `rsi_spread` | float | RSI spread at entry |
| `sl_mode` | str | SL mode used |
| `tp_allocations` | dict | TP allocation fractions |

TP hit flags (`tp1_hit`, `tp2_hit`, `tp3_hit`) come from `PositionSnapshot` (PortfolioManager is source of truth), not from context.

---

# rsi_momentum — Entry & Exit Rules (SHORT Only)

> SHORT-only strategy using RSI crossover indicators with bearish divergence confirmation.

## Entry Logic

All five conditions must hold simultaneously on the current candle:

```
S1 (Crossover/Persistence) ──┐
S2 (RSI < EMA9)              ├── ALL TRUE ──► Compute SL/TP ──► OpenPosition(side="SELL")
S3 (EMA9 < WMA45)            │
S4 (WMA45 − EMA9 > 2.5)     │
S5 (Bearish divergence)  ────┘
```

### S1: Crossover or Signal Persistence

**Crossover**: EMA9-of-RSI crosses below WMA45-of-RSI on the current candle:
- `EMA9[prev] >= WMA45[prev]` AND `EMA9[current] < WMA45[current]`

**Persistence**: If a crossover was detected on a prior candle (stored as `crossover_detected=True` in context), the signal persists on subsequent candles as long as S2+S3+S4 alignment holds. This prevents missing entries due to divergence appearing one candle late.

If alignment (S2+S3) breaks, `crossover_detected` resets to `False`.

### S2: RSI Below EMA9

`RSI_14 < EMA9-of-RSI` on the current candle. Confirms bearish RSI momentum.

### S3: EMA9 Below WMA45

`EMA9-of-RSI < WMA45-of-RSI` on the current candle. Confirms bearish trend alignment.

### S4: Spread Constraint

`(WMA45 - EMA9) > spread_threshold` (default 2.5 RSI units). Filters out noise when the two lines are too close together.

### S5: Bearish RSI Divergence

Price makes a Higher High while RSI makes a Lower High within the `divergence_lookback` window (default 30 candles).

Detection uses pivot swing highs (N=`pivot_strength`, default 5, meaning 11-bar pivots):
1. Find the two most recent swing highs in price within lookback
2. Find the two most recent swing highs in RSI within lookback
3. If `price_high[-1] > price_high[-2]` AND `rsi_high[-1] < rsi_high[-2]` → divergence confirmed

---

## SL Computation (Short)

For SHORT positions, SL is placed **above** entry:

| Component | Computation | Description |
|-----------|-------------|-------------|
| **Soft SL** | `max(high)` over last `sl_lookback` candles (default 30) | Highest high as resistance level |
| **Hard SL** | `entry + disaster_sl_multiplier × (soft_sl - entry)` | 3× the soft SL distance above entry |

The soft SL must be above entry price (`soft_sl > entry`), otherwise the trade is skipped (zero risk distance).

---

## TP Computation (Short)

TP levels are placed **below** entry at multiples of risk distance. Fee-aware calculation via `SLTPCalculator.compute_tp_price()`:

```
risk = soft_sl - entry          (positive, since soft_sl > entry for SHORT)
tp1 ≈ entry - tp1_rr × risk    (default: entry - 1.0 × risk)
tp2 ≈ entry - tp2_rr × risk    (default: entry - 2.0 × risk)
tp3 ≈ entry - tp3_rr × risk    (default: entry - 3.0 × risk)
```

The actual TP prices account for entry taker fee and exit maker fee to ensure the net profit matches the target R:R ratio.

### Dynamic Allocations

Same as `rsi_no_retest` — based on `tp_count`:

| tp_count | TP1 | TP2 | TP3 |
|----------|-----|-----|-----|
| 1 | 100% | — | — |
| 2 | `tp1_close_pct` (50%) | 100% remaining | — |
| 3 | `tp1_close_pct` (50%) | `tp2_close_pct` (50% of remaining) | 100% remaining |

---

## Position Management (Short Exit Logic)

Checked every candle in this priority order:

### 1. Pending Candle SL (highest priority)
If `pending_candle_sl=True` in context (set on previous candle):
- Exit at current candle's `open` price
- Emit `ClosePosition(reason="CLOSE_BY_CANDLE_SL")`
- Reset to SCANNING

### 2. Lock-Profit Trigger
If `low <= move_trigger` (price dropped 0.5R in our favor) and SL not yet moved:
- `move_trigger = entry - move_sl_rr × risk` (fee-adjusted)
- Emit `MoveSL(new_sl_price=lock_profit_price)`
- `lock_profit_price = entry - lock_profit_rr × risk` (below entry, locking profit)
- Set `moved_sl_to_entry=True`

Note: For SHORT positions, price going **down** is profitable. The lock-profit SL is placed **below** entry price (unlike LONG where it's above entry).

### 3. Max Holding Period (force-close)
If `max_holding_enabled` is `True` and the position has been open for at least `max_holding_bars` candles:
- Emit `ClosePosition(reason="MAX_HOLDING_PERIOD", price=close)` (market exit at the current candle's close)
- Reset to SCANNING

`bars_held` increments once per `analyze()` call while a position is open. Defaults: `max_holding_enabled=True`, `max_holding_bars=96` (24 hours on 15m). Toggle `max_holding_enabled` off to disable the check entirely.

### 4. Soft SL (candle-close based)
**Active only when `sl_trigger_mode == "candle_close"`.** If `close >= soft_sl_price` (price went against us — up):
- Set `pending_candle_sl=True` in context
- Emit `DoNothing` (exit happens next candle at open)

When `sl_trigger_mode == "touch"`, this step is skipped — the exchange stop at `soft_sl_price` fires on touch.

This 2-candle pattern prevents false exits from wick-only touches.

---

## rsi_momentum Context Meta Keys

The strategy stores these in `ContextSnapshot.meta` via the `TradeState` dataclass:

| Key | Type | Description |
|-----|------|-------------|
| `entry_price` | Decimal | Entry price |
| `sl_price` | Decimal | Current SL price (may move to lock-profit level) |
| `soft_sl_price` | Decimal | Current soft SL (candle-close monitored) |
| `original_soft_sl` | Decimal | Original soft SL before any moves |
| `disaster_sl_price` | Decimal | Hard SL on exchange (stop_market BUY order) |
| `lock_profit_price` | Decimal | SL moved here after lock-profit trigger |
| `move_trigger` | Decimal | Pre-computed price level to trigger lock-profit |
| `moved_sl_to_entry` | bool | Whether SL has been moved to lock-profit level |
| `pending_candle_sl` | bool | Candle SL flagged, exit next candle |
| `bars_held` | int | Candles since entry; force-close fires at `max_holding_bars` |
| `crossover_detected` | bool | Whether a bearish crossover has been detected (signal persistence) |
| `tp_allocations` | dict | TP allocation fractions, e.g. `{"TP1": 0.5, "TP2": 0.5, "TP3": 1.0}` |

TP hit flags (`tp1_hit`, `tp2_hit`, `tp3_hit`) come from `PositionSnapshot` (PortfolioManager is source of truth), not from context.
