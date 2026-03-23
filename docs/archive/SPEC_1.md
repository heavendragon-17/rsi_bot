# Trading Bot — Entry Conditions Specification

> **Purpose:** This document defines the necessary and sufficient conditions for the bot to generate a trade signal and execute an entry. It is intended as a precise, unambiguous reference for the developer implementing the system.
>
> **Last updated:** March 16, 2026

---

## 1. System Overview

| Property | Value |
|---|---|
| Market | Crypto — Centralized Exchange (CEX) |
| Execution model | Semi-automated: bot generates signals → sends Telegram notification → user confirms → bot executes |
| Strategy type | Momentum / custom indicator (RSI with applied moving averages) |
| Timeframe | 15-minute candles (single timeframe) |
| Trading pairs | 3–5 hardcoded major pairs against USDT *(to be specified by user)* |
| Direction | Long and Short |
| Leverage | Medium (5–10×) — exact multiplier to be configured per pair or globally |

---

## 2. Indicator Definitions

The strategy uses three derived indicators, all computed from the **14-period RSI** on 15m candles:

### 2.1 RSI Line
- **Type:** Relative Strength Index
- **Period:** 14 (standard)
- **Applied to:** Close price of each 15m candle

### 2.2 EMA 9 (of RSI)
- **Type:** Exponential Moving Average
- **Period:** 9
- **Applied to:** The RSI line (NOT price)

### 2.3 WMA 45 (of RSI)
- **Type:** Weighted Moving Average
- **Period:** 45
- **Applied to:** The RSI line (NOT price)

> **Critical implementation note:** EMA 9 and WMA 45 are moving averages *of the RSI values*, not of the price series. The developer must first compute the RSI, then feed that RSI series into the EMA and WMA calculations.

---

## 3. Entry Conditions

All conditions use strict **AND logic** — every condition must be true simultaneously on the **same 15m candle** for a valid signal.

### 3.1 Short Entry (Sell Signal)

A short signal fires when **all** of the following are true on candle close:

| # | Condition | Formal expression |
|---|---|---|
| S1 | **Bearish crossover:** EMA 9 crosses below WMA 45 | `EMA9[prev] >= WMA45[prev]` AND `EMA9[current] < WMA45[current]` |
| S2 | **RSI below EMA 9** | `RSI[current] < EMA9[current]` |
| S3 | **EMA 9 below WMA 45** | `EMA9[current] < WMA45[current]` |
| S4 | **Spread constraint:** Distance between WMA 45 and EMA 9 exceeds 2.5 | `(WMA45[current] - EMA9[current]) > 2.5` |
| S5 | **Bearish RSI divergence** within last 30 candles | See §3.3 below |

**Alignment summary:** `RSI < EMA9 < WMA45` **and** the crossover (S1) occurred on *this* candle, **and** the spread is wide enough (S4), **and** a recent bearish divergence confirms momentum exhaustion (S5).

> **Note:** Conditions S4 and S5 are **short-only** filters. Long entries do not require spread or divergence checks.

### 3.3 Bearish RSI Divergence (Short-Only — Condition S5)

A bearish divergence is detected when price makes a **Higher High** but RSI makes a **Lower High** within the last 30 candles. The detection logic is:

1. **Identify swing highs** in the 30-candle lookback window using pivot/fractal logic (implementation detail left to developer — e.g., a high surrounded by N lower highs on both sides).
2. **Find the two relevant peaks:**
   - **Peak A** (earlier): The previous swing high in the window.
   - **Peak B** (later): The highest price high in the window.
3. **Divergence condition:**
   - **Price:** `high[Peak B] > high[Peak A]` (Higher High — uses candle wicks, not close)
   - **RSI:** `RSI[Peak B] < RSI[Peak A]` (Lower High)
4. The divergence must have occurred **within the 30 candles preceding the current signal candle.** It does not need to occur on the signal candle itself — it is a lookback confirmation.

**Edge cases:**
- If fewer than two swing highs exist in the 30-candle window, condition S5 is **not met** (signal blocked).
- If multiple divergence pairs exist, any valid pair satisfies the condition.
- The 2.5-unit spread threshold (S4) is measured in RSI units (the same scale as the RSI, EMA 9, and WMA 45 values).

### 3.2 Long Entry (Buy Signal)

A long signal fires when **all** of the following are true on candle close (mirrored logic):

| # | Condition | Formal expression |
|---|---|---|
| L1 | **Bullish crossover:** EMA 9 crosses above WMA 45 | `EMA9[prev] <= WMA45[prev]` AND `EMA9[current] > WMA45[current]` |
| L2 | **RSI above EMA 9** | `RSI[current] > EMA9[current]` |
| L3 | **EMA 9 above WMA 45** | `EMA9[current] > WMA45[current]` |

**Alignment summary:** `RSI > EMA9 > WMA45` **and** the crossover (L1) occurred on *this* candle.

### 3.3 Crossover Timing Rule

- The entry signal is **only valid on the exact 15m candle where the EMA9/WMA45 crossover occurs.**
- If the user does not confirm the signal on that candle, the signal **remains valid** as long as the full alignment condition holds (i.e., all three conditions continue to be true on subsequent candles).
- The signal **expires** the moment any one of the three conditions breaks (e.g., RSI crosses back above EMA9).

---

## 4. Position Management Rules

### 4.1 One Position Per Pair
- Maximum **one open position per trading pair** at any time.
- If a signal fires in the opposite direction while a position is already open on that pair, the signal is **ignored**.
- Multiple pairs can have open positions simultaneously.

### 4.2 No Global Risk Cap
- There is no portfolio-level drawdown limit or maximum number of concurrent positions.
- Risk is managed on a per-trade basis only (see §5).

---

## 5. Risk Management & Position Sizing

### 5.1 Risk Per Trade
- **2% of total portfolio value** is the maximum loss per trade.
- "Loss" is defined as the distance from entry price to stop-loss price.

### 5.2 Position Size Calculation

```
risk_amount = portfolio_value × 0.02
stop_distance = |entry_price - stop_loss_price|
position_size = risk_amount / stop_distance
```

The bot must compute `stop_loss_price` **before** calculating position size (see §6.1).

### 5.3 Leverage
- Leverage range: **5–10×** (configurable).
- The position size formula above defines the *notional* size. Leverage determines how much margin is required: `margin = position_size × entry_price / leverage`.
- The bot must verify that the required margin does not exceed available balance before sending the signal.

---

## 6. Exit Conditions

### 6.1 Stop-Loss

| Direction | Stop-Loss Rule |
|---|---|
| **Short** | Highest high of the last **30** 15m candles (lookback from the entry candle, inclusive) |
| **Long** | Lowest low of the last **30** 15m candles (lookback from the entry candle, inclusive) |

- The 30-candle lookback equals **7.5 hours** of price data.
- Stop-loss is placed as a **static level** at entry time — it does not trail or update.
- If the stop-loss level equals the entry price (flat market), the signal should be **skipped** (zero risk distance makes position sizing undefined).

### 6.2 Take-Profit

- **Risk-to-reward ratio: 1:1**
- `take_profit_distance = |entry_price - stop_loss_price|`

| Direction | Take-Profit Price |
|---|---|
| **Short** | `entry_price - take_profit_distance` |
| **Long** | `entry_price + take_profit_distance` |

### 6.3 Exit Priority
- If both stop-loss and take-profit are hit on the same candle (gap/wick scenario), assume **stop-loss was hit first** (conservative).

---

## 7. Order Execution

### 7.1 Order Type
- **Market order** on user confirmation.
- No limit orders, no slippage protection beyond exchange defaults.

### 7.2 Execution Flow

```
1. Bot detects crossover + alignment on 15m candle close
2. Bot computes:
   a. Stop-loss level (30-candle swing high/low)
   b. Take-profit level (1:1 R:R)
   c. Position size (2% risk)
   d. Required margin (based on leverage)
3. Bot sends Telegram notification with:
   - Pair, direction (LONG/SHORT)
   - Entry price (current market)
   - Stop-loss price
   - Take-profit price
   - Position size
   - Required margin
4. User confirms via Telegram
5. Bot places market order + sets SL/TP on the exchange
```

### 7.3 Signal Validity After Notification
- Signal remains actionable as long as all three entry conditions hold on the most recent closed 15m candle.
- On each new 15m candle close, the bot re-evaluates conditions. If alignment breaks, the signal is **cancelled** and the user is notified.
- If the user confirms after a delay, the bot must **re-check conditions** and **recalculate SL/TP/size** at the current price before executing.

---

## 8. Pairs Configuration

Trading pairs are hardcoded and denominated in USDT. The user will provide 3–5 pairs from the following candidates:

> **⚠️ TO BE FILLED IN BY USER**
>
> Example: `BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT`

The bot should monitor all configured pairs simultaneously and independently.

---

## 9. Edge Cases & Developer Notes

### 9.1 Startup / Warm-up
- The bot needs at least **45 candles** of historical data to compute WMA 45 of RSI, plus 14 candles for the RSI itself. On startup, the bot must fetch at minimum **59 historical 15m candles** before generating signals.

### 9.2 Exchange Downtime / API Errors
- If a candle is missed due to API failure, the bot must **not** generate signals until it has a continuous series again. A crossover detected across a data gap is unreliable.

### 9.3 Identical EMA9 and WMA45 Values
- If `EMA9 == WMA45` exactly (floating-point edge case), this is **not** a crossover. Use strict inequality (`<` / `>`) for crossover detection.

### 9.4 Multiple Crossovers in Quick Succession
- If EMA9 whipsaws around WMA45 (crosses, then crosses back within a few candles), each crossover is a separate signal. However, since only one position per pair is allowed, subsequent signals on the same pair are ignored while a position is open.

### 9.5 Stop-Loss Equal to Entry
- If the 30-candle highest high (for shorts) or lowest low (for longs) equals the current price, the trade has zero risk distance. **Skip this signal** — notify the user that conditions were met but the trade was not viable.

### 9.6 Insufficient Balance
- If the required margin exceeds available balance, **do not send the signal.** Instead, notify the user that a valid signal was detected but margin is insufficient.

---

## 10. Configuration Summary

All configurable parameters in one place for the developer:

| Parameter | Default | Notes |
|---|---|---|
| `RSI_PERIOD` | 14 | Standard RSI |
| `EMA_PERIOD` | 9 | Applied to RSI |
| `WMA_PERIOD` | 45 | Applied to RSI |
| `CANDLE_TIMEFRAME` | 15m | Single timeframe |
| `LOOKBACK_CANDLES` | 30 | For swing high/low stop-loss |
| `SHORT_SPREAD_THRESHOLD` | 2.5 | Min WMA45–EMA9 distance for short entries (RSI units) |
| `DIVERGENCE_LOOKBACK` | 30 | Candles to search for bearish divergence (short only) |
| `RISK_PER_TRADE` | 0.02 | 2% of portfolio |
| `RISK_REWARD_RATIO` | 1.0 | 1:1 |
| `LEVERAGE` | 5–10 | Configurable |
| `PAIRS` | TBD | 3–5 USDT pairs |
| `MAX_POSITIONS_PER_PAIR` | 1 | Hard limit |
| `NOTIFICATION_CHANNEL` | Telegram | Bot → user |
