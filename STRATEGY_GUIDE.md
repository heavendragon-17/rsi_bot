# RSI No Retest Strategy - Configuration Guide

This document explains the configuration parameters available in the `RsiNoRetestStrategy`.
You can edit these values in:

1.  **`app/strategies/rsi_no_retest.py`** (inside the `DEFAULT_CONFIG` dictionary).
2.  **`config.yaml`** (under `strategy_params`, which overrides the python defaults).

## Parameter Reference

### 1. Indicator Settings

These parameters control the technical indicators used for signal generation.

| Parameter        | Default | Description                                            |
| :--------------- | :------ | :----------------------------------------------------- |
| `rsi_period`     | 21      | Length for calculating the main RSI line.              |
| `rsi_ema_length` | 9       | Length of the EMA applied to the RSI (Signal line).    |
| `rsi_wma_length` | 45      | Length of the WMA applied to the RSI (Trend baseline). |
| `price_ema_fast` | 21      | Fast EMA on price (used for Entry triggers).           |
| `price_ema_slow` | 200     | Slow EMA on price (used for Trend determination).      |

### 2. Entry Conditions

Conditions that must be met to enter a trade.

| Parameter            | Default | Description                                                                                                  |
| :------------------- | :------ | :----------------------------------------------------------------------------------------------------------- |
| `nr_lookback`        | 30      | Number of past candles to analyze for validity (the "Pullback" phase).                                       |
| `nr_max_above_ema21` | 1       | Maximum number of candles allowed to close _above_ the EMA21 during the pullback. Lower = stricter pullback. |
| `nr_rsi_spread_min`  | 1.5     | Minimum required distance between `rsi_ema9` and `rsi_wma45` to confirm momentum.                            |

### 3. Stop Loss (SL) Settings

How the initial Stop Loss is calculated.

| Parameter                | Default        | Description                                                                                                                                                                                                         |
| :----------------------- | :------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `nr_sl_mode`             | "lowest_close" | **lowest_close**: SL is placed at the lowest _close_ price in the lookback.<br>**lowest_wick**: SL is placed at the lowest _low_ (wick) in the lookback.<br>**rsi_ema9**: SL is calculated based on RSI volatility. |
| `sl_buffer_pct`          | 0.0            | Optional percentage to widen the SL (e.g., 0.01 = 1% below the calculate level).                                                                                                                                    |
| `disaster_sl_multiplier` | 3.0            | Defines the "Hard SL" sent to the exchange relative to the "Soft SL". <br>Example: If Soft SL is 1% away, Disaster SL is 3% away.                                                                                   |

### 4. Take Profit (TP) Settings

Configuration for profit targets. You can choose to use 1, 2, or 3 TP levels.

| Parameter         | Default | Description                                                    |
| :---------------- | :------ | :------------------------------------------------------------- |
| **`nr_tp_count`** | **3**   | **Number of TP levels to use (1, 2, or 3).**                   |
| `nr_tp1_rr`       | 1.0     | Distance to TP1 in Risk Units (R). 1.0 = 1x Risk.              |
| `nr_tp2_rr`       | 2.0     | Distance to TP2 (2x Risk). Ignored if count < 2.               |
| `nr_tp3_rr`       | 3.0     | Distance to TP3 (3x Risk). Ignored if count < 3.               |
| `tp1_close_pct`   | 0.50    | Percentage of position to close at TP1 (0.5 = 50%).            |
| `tp2_close_pct`   | 1.0     | Percentage of _remaining_ position to close at TP2.            |
| `tp3_close_pct`   | 0.0     | Percentage at TP3 (usually 0.0 implies "close all remaining"). |

### 5. Trade Management

Rules for managing the trade after entry.

| Parameter           | Default | Description                                                                                                                      |
| :------------------ | :------ | :------------------------------------------------------------------------------------------------------------------------------- |
| `nr_move_sl_rr`     | 0.5     | **Breakeven Trigger**: When price reaches 0.5R profit, check the Lock Profit condition.                                          |
| `nr_lock_profit_rr` | 0.2     | **Lock Profit Level**: When the trigger is hit, move SL to `Entry Price + 0.2R`. (Ensures you cover fees and lock small profit). |
| `use_active_trades` | True    | If True, the strategy actively monitors open trades to manage exits.                                                             |

## How to Edit

### Option A: Edit Defaults (Permanent)

1. Open `app/strategies/rsi_no_retest.py`
2. Locate `DEFAULT_CONFIG = { ... }`
3. Change the values.
4. Push changes to GitHub.

### Option B: Edit Config (Flexible)

1. Open `config.yaml`.
2. Add/Edit keys under `strategy_params`.
3. **Restart the bot** to apply.

```yaml
# config.yaml example
strategy_params:
  nr_tp_count: 2
  nr_tp1_rr: 1.5
  tp1_close_pct: 0.5
```
