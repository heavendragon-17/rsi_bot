# Strategy Reference

> Parameter reference for all strategies. Covers entry rules, SL/TP logic, and config defaults.

---

## Available Strategies

| Name | Module | Description |
|------|--------|-------------|
| `rsi_no_retest` | `app/strategies/rsi_no_retest.py` | Primary. Entry on EMA21 reclaim + RSI momentum spread. |
| `rsi_wma_retest` | `app/strategies/rsi_wma_retest.py` | Legacy. Requires RSI retest of WMA45. |

Loaded dynamically by `app/strategies/loader.py`.

Configuration sources (override order):
1. `DEFAULT_CONFIG` in strategy file (base defaults)
2. `config.yaml` under `strategy_params` (overrides defaults)
3. Backtest UI sidebar (overrides for individual runs)

---

## rsi_no_retest

### 1. Indicator Settings

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `rsi_period` | 21 | Length for calculating the main RSI line |
| `rsi_ema_length` | 9 | Length of the EMA applied to the RSI (signal line) |
| `rsi_wma_length` | 45 | Length of the WMA applied to the RSI (trend baseline) |
| `price_ema_fast` | 21 | Fast EMA on price (entry triggers) |
| `price_ema_slow` | 200 | Slow EMA on price (trend determination) |

### 2. Entry Conditions

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `nr_lookback` | 30 | Number of past candles to analyze for the pullback phase |
| `nr_max_above_ema21` | 3 | Max candles allowed to close above EMA21 during pullback. Lower = stricter |
| `nr_rsi_spread_min` | 2.5 | Minimum required distance between RSI_EMA9 and RSI_WMA45 to confirm momentum |

**Entry logic**:
1. **Reclaim detection**: Candle at index -2 closes > EMA21, candle at -3 closed <= EMA21
2. **Pullback filter**: In the last `nr_lookback` candles, max `nr_max_above_ema21` closed above EMA21
3. **RSI confirmation**: `RSI_EMA9 - RSI_WMA45 >= nr_rsi_spread_min`

State machine: SCANNING → [reclaim + pullback] → CONFIRMING → [RSI spread met] → OpenPosition → SCANNING

### 3. Stop Loss (SL) Settings

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `nr_sl_mode` | `"lowest_close"` | SL calculation mode: `lowest_close`, `lowest_wick`, or `rsi_ema9` |
| `sl_buffer_pct` | 0.0 | Optional percentage to widen SL (e.g., 0.01 = 1% below) |
| `disaster_sl_multiplier` | 3.0 | Hard SL distance as multiple of soft SL distance |

**Dual SL system**:
- **Soft SL** (`soft_sl_price`): Tight SL at computed level. Checked on candle close. Uses 2-candle pattern (candle N close < SL → flag → candle N+1 open → market close).
- **Hard SL** (`sl_price`): Disaster SL at `entry - disaster_sl_multiplier × SL_distance`. Placed as `stop_market` on exchange. Safety net only.

### 4. Take Profit (TP) Settings

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `nr_tp_count` | 3 | Number of TP levels to use (1, 2, or 3) |
| `nr_tp1_rr` | 1.0 | Distance to TP1 in Risk units (1.0 = 1x Risk) |
| `nr_tp2_rr` | 2.0 | Distance to TP2 (2x Risk). Ignored if count < 2 |
| `nr_tp3_rr` | 3.0 | Distance to TP3 (3x Risk). Ignored if count < 3 |
| `tp1_close_pct` | 0.50 | Percentage of position to close at TP1 |
| `tp2_close_pct` | 0.50 | Percentage of remaining position to close at TP2 |
| `tp3_close_pct` | 0.0 | TP3 closes all remaining |

**TP logic** (checked TP3 → TP2 → TP1):
- TP3 hit: Full exit, state → SCANNING
- TP2 hit: Partial close (50% remaining), keep SL
- TP1 hit: Partial close (50%), move SL to lock_profit_price

### 5. Trade Management

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `nr_move_sl_rr` | 0.5 | Breakeven trigger: when price reaches +0.5R, check lock profit |
| `nr_lock_profit_rr` | 0.2 | Lock profit level: move SL to entry + 0.2R |
| `use_active_trades` | True | Whether strategy actively monitors open trades for exits |

**Management flow**:
1. Price reaches +0.5R → move SL to entry + 0.2R (lock small profit)
2. TP1 hit → partial close + move SL to lock_profit_price
3. TP2 hit → partial close
4. TP3 hit → full exit
5. Soft SL triggered → 2-candle exit pattern

### How to Edit

**Option A: Edit defaults (permanent)**
- Open `app/strategies/rsi_no_retest.py` → modify `DEFAULT_CONFIG`

**Option B: Edit config.yaml (flexible, restart required)**
```yaml
strategy_params:
  nr_tp_count: 2
  nr_tp1_rr: 1.5
  tp1_close_pct: 0.5
```

---

## rsi_wma_retest (Legacy)

Uses RSI retest of WMA45 as entry confirmation instead of RSI momentum spread. Shares the same SL/TP management system as `rsi_no_retest`.

Key difference: Requires RSI line to cross back below WMA45 and then retest from above, confirming trend strength.

See `app/strategies/rsi_wma_retest.py` for full implementation.
