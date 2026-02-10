# Strategy Development Guide

> **For AI Agents & Human Developers** | How to create new trading strategies for rsi_bot

---

## Architecture: What a Strategy IS and IS NOT

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STRATEGY BOUNDARY                           │
│                                                                     │
│  Strategy OWNS:                    Strategy DOES NOT OWN:           │
│  ✅ Entry conditions               ❌ Where OHLCV data comes from  │
│  ✅ Exit conditions                 ❌ Position sizing / allocation │
│  ✅ Indicator calculations          ❌ Order execution              │
│  ✅ SL / TP price calculation       ❌ Portfolio balance            │
│  ✅ Trade state machine             ❌ Exchange API calls           │
│  ✅ Signal generation               ❌ Data download / storage      │
│  ✅ DEFAULT_CONFIG definition       ❌ Risk management (leverage)   │
│                                     ❌ Logging infrastructure       │
│                                     ❌ Database operations          │
└─────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **A strategy is a pure signal generator.** It receives a DataFrame of OHLCV candles and returns either a `SignalEvent` (BUY/SELL) or `None`. It does not know, and must not care, where the prices came from (live WebSocket, CSV file, mock exchange) or how large the position will be.

---

## The Contract

### Input

```python
def analyze(self, symbol: str, df: pd.DataFrame) -> Optional[SignalEvent]:
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | `str` | Trading pair, e.g. `"BTC/USDT"` |
| `df` | `pd.DataFrame` | OHLCV data with columns: `open`, `high`, `low`, `close`, `volume`. Index is timestamp. May contain a `closed` column (bool). |

### Output

Return `SignalEvent` for entry/exit, or `None` for no action.

**BUY signal (entry):**
```python
return SignalEvent(
    symbol=symbol,
    signal_type="BUY",
    price=entry_price,            # Where to enter (Decimal)
    timestamp=ts,
    reason="Description of why",
    tp1_price=tp1,                # Take profit 1 (Optional[Decimal])
    tp2_price=tp2,                # Take profit 2 (Optional[Decimal])  
    tp3_price=tp3,                # Take profit 3 (Optional[Decimal])
    sl_price=disaster_sl,         # Hard SL for exchange order (Decimal)
    soft_sl_price=soft_sl,        # Candle-close SL for portfolio (Optional[Decimal])
    signal_class=2,               # Quality: 1=optimal, 2=acceptable
    tp_allocations={"TP1": 0.5, "TP2": 0.5, "TP3": 1.0},  # Optional close %
)
```

**SELL signal (exit):**
```python
return SignalEvent(
    symbol=symbol,
    signal_type="SELL",
    price=exit_price,
    timestamp=ts,
    reason="TP1 (>1R)" | "CLOSE_BY_CANDLE_SL" | "MOVE_SL_LOCK_PROFIT (...)",
    sl_price=new_sl,              # Optional: tells Portfolio to move SL
)
```

---

## File Structure & Registration

### 1. Create the file

```
app/strategies/your_strategy_name.py
```

Naming convention: `snake_case`, descriptive, no prefix/suffix needed.

### 2. Register in loader.py

Open [app/strategies/loader.py](file:///c:/Users/Windows/OneDrive/Documents/GitHub/rsi_bot/app/strategies/loader.py) and add:

```python
from .your_strategy_name import YourStrategyName

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "your_strategy_name": YourStrategyName,        # ← ADD HERE
}
```

> [!CAUTION]
> **Do NOT skip registration.** The UI, backtest engine, and live bot all use `loader.py` to find strategies. An unregistered strategy is invisible.

---

## Template: Minimal Strategy

```python
"""
Layer 2: Core Logic - [Strategy Name]
======================================
[Brief description of trading rules]
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.core.events import SignalEvent
from app.core.context import SCANNING, CONFIRMING


class YourStrategyName(BaseStrategy):
    """One-line description."""

    # -------------------------------------------------
    # DEFAULT_CONFIG: All tunable parameters go here
    # -------------------------------------------------
    DEFAULT_CONFIG = {
        # Indicator params
        "rsi_period": 14,
        "rsi_ema_length": 9,
        "rsi_wma_length": 45,
        "price_ema_fast": 21,
        "price_ema_slow": 200,

        # Entry conditions
        "min_rsi": 30,
        "max_rsi": 50,

        # SL / TP
        "sl_buffer_pct": 0.005,
        "tp_rr": 2.0,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        # Merge defaults with user overrides
        cfg = {**self.DEFAULT_CONFIG, **config.get("strategy_params", {})}

        # Init indicators
        self.indicators = Indicators(
            rsi_length=cfg["rsi_period"],
            rsi_ema_length=cfg["rsi_ema_length"],
            rsi_wma_length=cfg["rsi_wma_length"],
            price_ema_fast=cfg["price_ema_fast"],
            price_ema_slow=cfg["price_ema_slow"],
        )

        # Store params as instance vars
        self.min_rsi = float(cfg["min_rsi"])
        self.max_rsi = float(cfg["max_rsi"])
        self.sl_buffer_pct = float(cfg["sl_buffer_pct"])
        self.tp_rr = Decimal(str(cfg["tp_rr"]))

        self.timeframe = config.get("timeframe", "15m")

    # -------------------------------------------------
    # analyze(): The ONLY required method
    # -------------------------------------------------
    def analyze(self, symbol: str, df: pd.DataFrame) -> Optional[SignalEvent]:
        # Guard: Need enough data
        if df is None or len(df) < 220:
            return None

        # Guard: Skip unconfirmed candles
        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        # Compute indicators
        df_ind = self.indicators.compute(df, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return None

        # Extract values
        close = Decimal(str(last["close"]))
        ts = df_ind.index[-1]

        # ---- TRADE MANAGEMENT (if position open) ----
        if self.context.has_active_trade(symbol):
            return self._manage_trade(symbol, df_ind, last, close, ts)

        # ---- ENTRY LOGIC ----
        state = self.context.get_state(key)

        if state.phase == SCANNING:
            if self._check_entry_conditions(df_ind, last):
                self.context.transition(key, CONFIRMING, reason="Entry conditions met", now_ts=ts)
                state = self.context.get_state(key)

        if state.phase == CONFIRMING:
            return self._generate_entry_signal(symbol, key, df_ind, last, close, ts)

        return None

    # -------------------------------------------------
    # Private: Entry condition checks
    # -------------------------------------------------
    def _check_entry_conditions(self, df_ind, last) -> bool:
        """Return True if entry conditions are met."""
        # YOUR LOGIC HERE
        rsi = last.get("rsi")
        if rsi is None:
            return False
        return self.min_rsi <= float(rsi) <= self.max_rsi

    def _generate_entry_signal(self, symbol, key, df_ind, last, close, ts):
        """Generate BUY signal with SL/TP."""
        # Calculate SL
        sl_price = close * (Decimal("1") - Decimal(str(self.sl_buffer_pct)))

        # Calculate TP
        risk = close - sl_price
        if risk <= 0:
            self.context.transition(key, SCANNING, reason="Invalid risk", now_ts=ts)
            return None
        tp_price = close + (risk * self.tp_rr)

        # Register trade in context
        self.context.open_trade(
            symbol=symbol,
            timeframe=self.timeframe,
            side="LONG",
            entry_price=float(close),
            meta={
                "entry_price": close,
                "sl_price": sl_price,
                "tp_price": tp_price,
            },
            now_ts=ts,
        )
        self.context.transition(key, SCANNING, reason="BUY emitted", now_ts=ts)

        return SignalEvent(
            symbol=symbol,
            signal_type="BUY",
            price=close,
            timestamp=ts,
            reason="Your entry reason",
            sl_price=sl_price,
            tp1_price=tp_price,
        )

    # -------------------------------------------------
    # Private: Trade management (exits)
    # -------------------------------------------------
    def _manage_trade(self, symbol, df_ind, last, close, ts):
        """Manage open position: check TP/SL hits."""
        trade = self.context.get_trade(symbol)
        meta = trade.meta if trade else {}
        
        entry_price = Decimal(str(meta.get("entry_price", 0)))
        sl_price = Decimal(str(meta.get("sl_price", 0)))
        tp_price = Decimal(str(meta.get("tp_price", 0)))
        high = Decimal(str(last.get("high", 0)))

        # TP hit
        if tp_price and high >= tp_price:
            self.context.close_trade(symbol)
            key = f"{symbol}:{self.timeframe}"
            self.context.transition(key, SCANNING, reason="TP hit", now_ts=ts)
            return SignalEvent(
                symbol=symbol, signal_type="SELL",
                price=tp_price, timestamp=ts, reason="TP hit"
            )

        # SL hit (candle close below SL)
        if sl_price and close <= sl_price:
            self.context.close_trade(symbol)
            key = f"{symbol}:{self.timeframe}"
            self.context.transition(key, SCANNING, reason="SL hit", now_ts=ts)
            return SignalEvent(
                symbol=symbol, signal_type="SELL",
                price=close, timestamp=ts, reason="SL hit"
            )

        return None
```

---

## Rules (DO and DON'T)

### ✅ DO

| Rule | Why |
|------|-----|
| Define all tunable params in `DEFAULT_CONFIG` | Grid search, sensitivity, and UI need this dict |
| Use `Decimal` for all price values | Financial precision — `float(0.1 + 0.2) != 0.3` |
| Use `self.context` for state machine | Prevents duplicate entries, tracks active trades |
| Return `None` when no action | Engine calls `analyze()` on every candle |
| Guard with `len(df) < N` check | Indicators need history to compute |
| Skip unconfirmed candles (`closed` column) | Live data sends partial candles |
| Use `Indicators` class for RSI/EMA/WMA | Shared, tested, cached computation |
| Keep entry logic and trade management separate | Clean separation of concerns |
| Use the state machine (`SCANNING → CONFIRMING`) | Prevents re-entry on same signal |
| Put all `reason` strings in `SignalEvent` | Debugging and reporting need these |

### ❌ DON'T

| Rule | Why | What to Do Instead |
|------|-----|---------------------|
| ❌ Import exchange or fetch prices | Strategy doesn't know data source | Use the `df` parameter as-is |
| ❌ Calculate position size / quantity | Portfolio layer handles this | Just emit the signal |
| ❌ Call `exchange.create_order()` | Execution layer handles this | Return `SignalEvent` |
| ❌ Access `config.yaml` directly | Engine passes config to `__init__` | Use `self.config` |
| ❌ Write to DB or files | DB layer is separate | Log via `logger` if needed |
| ❌ Use `float` for prices | Precision loss | Use `Decimal(str(value))` |
| ❌ Use global/class-level mutable state | Breaks multi-symbol runs | Use `self.context` per symbol |
| ❌ Hardcode symbol-specific values | Breaks multi-asset backtest | Parameterize in `DEFAULT_CONFIG` |
| ❌ Import from `app.ui` or `app.db` | Clean architecture violation | Strategy is Layer 2, UI/DB is Layer 3+ |

---

## Available Tools

### Indicators (`app/utils/indicators.py`)

```python
from app.utils.indicators import Indicators

ind = Indicators(rsi_length=14, rsi_ema_length=9, rsi_wma_length=45,
                 price_ema_fast=21, price_ema_slow=200)

# Compute all indicators → adds columns to DataFrame
df_ind = ind.compute(df, symbol="BTC/USDT", timeframe="15m")
# Columns added: rsi, rsi_ema9, rsi_wma45, ema21, ema200

# Get last row as dict
last = Indicators.last(df_ind)  # {"close": 50000, "rsi": 45, "ema21": 49800, ...}

# Market mode
mode = ind.get_mode(df_ind)  # "BULLISH" or "NEUTRAL"

# Price at target RSI
price_at_r40 = ind.calculate_price_at_rsi(df_ind, 40.0)  # Decimal

# WMA retest check
is_retesting = ind.check_wma_retest(df_ind, distance=1.0)  # bool

# R40 floor check
floor_intact = ind.check_r40_floor(df_ind, lookback=5)  # bool
```

### Context (`app/core/context.py`)

```python
# State machine (per symbol:timeframe key)
state = self.context.get_state("BTC/USDT:15m")    # SymbolState
state.phase                                         # "SCANNING" | "CONFIRMING" | "RETESTING"
self.context.transition(key, CONFIRMING, reason="...", now_ts=ts)

# Active trade tracking
self.context.has_active_trade("BTC/USDT")           # bool
self.context.open_trade(symbol, timeframe, side, entry_price, meta={...}, now_ts=ts)
self.context.close_trade("BTC/USDT")
trade = self.context.get_trade("BTC/USDT")          # ActiveTrade or None
trade.meta                                           # dict — store SL/TP/flags here
```

### SignalEvent fields (`app/core/events.py`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | `str` | ✅ | Trading pair |
| `signal_type` | `str` | ✅ | `"BUY"` or `"SELL"` |
| `price` | `Decimal` | ✅ | Entry/exit price |
| `timestamp` | `datetime` | ✅ | Candle timestamp |
| `reason` | `str` | ✅ | Human-readable reason |
| `tp1_price` | `Decimal` | BUY only | Take profit level 1 |
| `tp2_price` | `Decimal` | Optional | Take profit level 2 |
| `tp3_price` | `Decimal` | Optional | Take profit level 3 |
| `sl_price` | `Decimal` | BUY only | Hard SL (exchange order) |
| `soft_sl_price` | `Decimal` | Optional | Candle-close SL |
| `signal_class` | `int` | Optional | Quality: 1=optimal, 2=acceptable |
| `tp_allocations` | `dict` | Optional | `{"TP1": 0.5, "TP2": 1.0}` |

---

## Testing a New Strategy

```bash
# Quick smoke test
conda run -n rsi python -c "
from app.strategies.your_strategy import YourStrategy
s = YourStrategy({'timeframe': '15m'})
print(f'Config keys: {list(s.DEFAULT_CONFIG.keys())}')
print('Init OK')
"

# Backtest
conda run -n rsi python app/backtest/backtest.py --strategy your_strategy_name --data app/backtest/data/BTCUSDT_15m.csv
```

---

## Existing Strategies (Reference)

| Strategy | File | Entry Logic |
|----------|------|-------------|
| `rsi_wma_retest` | [rsi_wma_retest.py](file:///c:/Users/Windows/OneDrive/Documents/GitHub/rsi_bot/app/strategies/rsi_wma_retest.py) | RSI touches WMA45 (retest) + bullish mode |
| `rsi_no_retest` | [rsi_no_retest.py](file:///c:/Users/Windows/OneDrive/Documents/GitHub/rsi_bot/app/strategies/rsi_no_retest.py) | EMA21 reclaim without WMA retest |

Both demonstrate: `DEFAULT_CONFIG`, dual SL system, multi-TP management, state machine, and trade context management.

---

## Clean Architecture Reminder

```
Layer 1: Data          → IDataProvider, IDataStore (where prices come from)
Layer 2: Core Logic    → IStrategy, IIndicators   (YOUR STRATEGY LIVES HERE)
Layer 3: Execution     → IExchange, IPortfolio     (how orders execute)
```

**Your strategy sits in Layer 2.** It must NEVER import from Layer 1 or Layer 3. The engine connects the layers.
