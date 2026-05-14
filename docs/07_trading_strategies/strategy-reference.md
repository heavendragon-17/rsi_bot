# Strategy Reference

> Parameter reference for all strategies. Covers entry rules, SL/TP logic, and config defaults.

---

## Available Strategies

| Name | Module | Status | Description |
|------|--------|--------|-------------|
| `rsi_no_retest` | `app/trading/strategy/rsi_no_retest.py` | Primary | Entry on EMA21 reclaim + RSI momentum spread |
| `rsi_wma_retest` | `app/trading/strategy/rsi_wma_retest.py` | Legacy | Requires RSI retest of WMA45 (old stateful API) |
| `rsi_momentum` | `app/trading/strategy/rsi_momentum.py` | Active | SHORT-only entries via RSI momentum + bearish divergence |
| `rsi_alert` | `app/trading/strategy/rsi_alert/` | Alert-only | Telegram alert when RSI14 (live, intra-candle) hits 8.5 / 8 — no trading |

Loaded dynamically by `app/trading/strategy/loader.py` via `STRATEGY_MAP`.

---

## rsi_no_retest — Complete Parameter Reference

### Indicator Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rsi_period` | 21 | RSI calculation length |
| `rsi_ema_length` | 9 | EMA smoothing of RSI (signal line) |
| `rsi_wma_length` | 45 | WMA smoothing of RSI (trend baseline) |
| `price_ema_fast` | 21 | Fast EMA on price (entry trigger) |
| `price_ema_slow` | 200 | Slow EMA on price (trend filter) |

### Entry Conditions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nr_lookback` | 30 | Candles to analyze for pullback phase |
| `nr_max_above_ema21` | 3 | Max candles allowed above EMA21 during pullback (lower = stricter) |
| `nr_rsi_spread_min` | 2.5 | Minimum RSI_EMA9 − RSI_WMA45 spread for confirmation |

### Stop Loss Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nr_sl_mode` | `"lowest_close"` | SL mode: `lowest_close`, `lowest_wick`, or `rsi_ema9` |
| `sl_buffer_pct` | 0.0 | Percentage to widen SL below computed level |
| `disaster_sl_multiplier` | 3.0 | Hard SL = soft SL distance × multiplier |

### Take Profit Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nr_tp_count` | 3 | TP levels to use (1, 2, or 3) |
| `nr_tp1_rr` | 1.0 | TP1 at 1.0× risk distance |
| `nr_tp2_rr` | 2.0 | TP2 at 2.0× risk distance |
| `nr_tp3_rr` | 3.0 | TP3 at 3.0× risk distance |
| `tp1_close_pct` | 0.50 | Position fraction closed at TP1 |
| `tp2_close_pct` | 0.50 | Remaining fraction closed at TP2 |
| `tp3_close_pct` | 0.0 | TP3 closes all remaining (100%) |

### Trade Management

| Parameter | Default | Description |
|-----------|---------|-------------|
| `nr_move_sl_rr` | 0.5 | Breakeven trigger: price reaches +0.5R |
| `nr_lock_profit_rr` | 0.2 | Lock profit level: SL moved to entry + 0.2R |
| `use_active_trades` | True | Whether strategy manages open positions |
| `candle_close_slippage_pct` | 0.0 | Slippage on candle-close exits |

---

## Dual SL System

Every trade uses two SL levels:

| SL Type | Price | Mechanism | Purpose |
|---------|-------|-----------|---------|
| **Soft SL** | Computed from `nr_sl_mode` | Strategy checks on candle close. Uses 2-candle pattern: close < SL → set flag → next candle open → market exit | Tight SL for risk management |
| **Hard SL** | `entry - disaster_sl_multiplier × (entry - soft_sl)` | `stop_market` order placed on exchange immediately | Disaster protection for flash crashes |

Position sizing uses soft SL distance, not hard SL.

---

## Management Flow

In priority order (checked each candle):

1. **Pending candle SL**: If flagged on previous candle → exit at current open
2. **TP3 check**: If `high >= tp3_price` → full exit, reset to SCANNING
3. **TP2 check**: If `high >= tp2_price` → partial close (50% remaining)
4. **TP1 check**: If `high >= tp1_price` → partial close (50%), move SL to `lock_profit_price`
5. **Breakeven trigger**: If `high >= entry + move_sl_rr × risk` → move SL to `lock_profit_price`
6. **Soft SL check**: If `close <= soft_sl_price` → flag `pending_candle_sl`, wait for next candle

---

## rsi_momentum — Complete Parameter Reference

SHORT-only strategy using RSI momentum crossover with bearish divergence confirmation. Uses `Indicators` (RSI14 + EMA9-of-RSI + WMA45-of-RSI) and the reusable `SLTPCalculator` utility.

**Files**: `app/trading/strategy/rsi_momentum.py`, `app/data/indicators.py`, `app/trading/sl_tp_calculator.py`

### Indicator Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rsi_period` | 14 | RSI calculation length |
| `ema_period` | 9 | EMA smoothing of RSI (signal line) |
| `wma_period` | 45 | WMA smoothing of RSI (trend baseline) |

### Entry Conditions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `spread_threshold` | 2.5 | S4: Minimum (WMA45 − EMA9) RSI-unit spread |
| `divergence_lookback` | 30 | S5: Candles to search for bearish divergence |
| `pivot_strength` | 5 | S5: N for swing high detection (11-bar pivot, N bars each side) |
| `min_candles` | 75 | Warm-up requirement (14 RSI + 45 WMA + 16 buffer) |

### Stop Loss Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sl_lookback` | 30 | Highest high lookback for soft SL |
| `disaster_sl_multiplier` | 3.0 | Hard SL = entry + multiplier × (soft_sl − entry) |

### Take Profit Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tp_count` | 3 | TP levels to use (1, 2, or 3) |
| `tp1_rr` | 1.0 | TP1 at 1.0× risk distance below entry |
| `tp2_rr` | 2.0 | TP2 at 2.0× risk distance below entry |
| `tp3_rr` | 3.0 | TP3 at 3.0× risk distance below entry |
| `tp1_close_pct` | 0.50 | Position fraction closed at TP1 |
| `tp2_close_pct` | 0.50 | Remaining fraction closed at TP2 |

### Trade Management

| Parameter | Default | Description |
|-----------|---------|-------------|
| `move_sl_rr` | 0.5 | Lock-profit trigger: price drops 0.5R (in our favor for SHORT) |
| `lock_profit_rr` | 0.2 | Lock-profit SL level: 0.2R above entry (locking profit for SHORT) |
| `use_active_trades` | True | Whether strategy manages open positions |
| `candle_close_slippage_pct` | 0.0 | Slippage on candle-close exits |
| `taker_fee` | 0.0005 | Taker fee rate (market/stop orders) |
| `maker_fee` | 0.0002 | Maker fee rate (limit orders) |

---

## rsi_momentum — Dual SL System (Short)

Every SHORT trade uses two SL levels:

| SL Type | Price | Mechanism | Purpose |
|---------|-------|-----------|---------|
| **Soft SL** | Highest high of last `sl_lookback` candles | Strategy checks on candle close. If `close >= soft_sl` → set `pending_candle_sl` flag → next candle open → market exit | Tight SL for risk management |
| **Hard SL** | `entry + disaster_sl_multiplier × (soft_sl - entry)` | `stop_market` BUY order placed on exchange immediately | Disaster protection for flash pumps |

Position sizing uses soft SL distance, not hard SL.

---

## rsi_momentum — Management Flow (Short)

In priority order (checked each candle):

1. **Pending candle SL**: If flagged on previous candle → exit at current open
2. **Lock-profit trigger**: If `low <= entry - move_sl_rr × risk` and SL not yet moved → move SL to `lock_profit_price` (entry − lock_profit_rr × risk)
3. **Soft SL check**: If `close >= soft_sl_price` → flag `pending_candle_sl`, wait for next candle

TP fills are handled by `PortfolioManager` via exchange limit orders (not strategy-managed). The hard (disaster) SL is a `stop_market` BUY order on the exchange.

---

## rsi_wma_retest (Legacy)

Uses the old stateful API (mutable `self.context`, returns `SignalEvent`). Not fully migrated to stateless pattern.

**Entry state machine**: SCANNING → RETESTING → CONFIRMING
- **SCANNING**: RSI > RSI_EMA9 and RSI > RSI_WMA45 → RETESTING
- **RETESTING**: RSI retests WMA45 (distance ≤ 0.3) → CONFIRMING
- **CONFIRMING**: EMA21 cross-up + RSI bounce → entry signal

**TP levels**: RSI-based (60/70/80), not R:R-based.

---

## rsi_alert — Alert-Only Strategy

Continuously watches `rsi_14` on the configured timeframe (default M15) using
the **in-progress candle** (not just closed candles). When RSI drops into an
oversold tier, dispatches a Telegram message via `notification_service` and
suppresses further alerts on that tier for `cooldown_minutes`.

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rsi_period` | 14 | RSI calculation length |
| `warning_threshold` | 8.5 | Alert fires when live RSI ≤ this (and > strong) |
| `strong_threshold` | 8.0 | Alert fires when live RSI ≤ this |
| `cooldown_minutes` | 120 | Per-symbol, per-tier mute window after firing |
| `min_candles` | 30 | Warm-up before RSI is trusted |

### Behavior

- Emits only `SendAlert` actions — never opens positions, never touches the
  portfolio.
- Sets `tick_mode = True` so `run_symbol_loop` evaluates it every ~1s using
  the full DataFrame (including the forming candle), instead of waiting for
  candle close.
- Two cooldown timestamps are stored in the strategy's `ContextSnapshot.meta`
  (`rsi_alert_last_warning_ts`, `rsi_alert_last_strong_ts`) and reset
  independently when their cooldown expires.

### Config

```yaml
strategy: rsi_alert
timeframe: 15m
symbols: [BTC/USDT, ETH/USDT, ...]
```

To tune thresholds or cooldown, edit the `RsiAlertConfig` defaults in
`app/trading/strategy/rsi_alert/strategy.py`, or pass overrides through the
top-level config dict (keys are filtered by `merge_config`).

---

## How to Override Parameters

**Option A — Frozen config dataclass (recommended)**:
Edit the strategy's frozen config dataclass defaults (e.g., `RsiNoRetestConfig` in `app/trading/strategy/rsi_no_retest.py`). Strategy parameters are no longer stored in `config.yaml`.

**Option B — Backtest UI sidebar (per-run)**:
Override parameters in the UI for individual backtest runs.

Override hierarchy: frozen dataclass defaults < `DEFAULT_CONFIG` < UI sidebar
