# Stateless Strategy Pattern

> The core contract every strategy must implement. Strategies are pure functions of market data and state snapshots.

---

## The `analyze()` Contract

```python
def analyze(
    self,
    symbol: str,
    df: pd.DataFrame,
    position: PositionSnapshot = None,
    context: ContextSnapshot = None
) -> AnalysisResult:
```

### Why Stateless

Strategies store **no mutable state** on `self`. All state lives in `ContextSnapshot`, which flows in and out:

1. Engine owns `self.contexts: Dict[str, ContextSnapshot]` per symbol
2. Engine passes `context` to `analyze()`
3. Strategy returns `AnalysisResult.new_context` with updated state
4. Engine stores the new context for next call

This enables: testing without mocking, parallel execution, serialization, and reasoning about state transitions.

---

## Action Types

`AnalysisResult.actions` contains a list of one or more actions:

### OpenPosition

```python
OpenPosition(
    side: str,             # "BUY" or "SELL"
    sl_price: Decimal,     # Hard SL (disaster SL placed on exchange as stop_market)
    tp1_price: Decimal,    # TP1 price
    tp2_price: Optional[Decimal],
    tp3_price: Optional[Decimal],
    soft_sl_price: Optional[Decimal],  # Tight SL checked by strategy on candle close
    lock_profit_price: Optional[Decimal],  # SL moved here after TP1 or breakeven trigger
    tp_allocations: Dict[str, float],  # e.g. {"TP1": 0.5, "TP2": 0.5, "TP3": 0.0}
)
```

### ClosePosition

```python
ClosePosition(
    reason: str,   # e.g. "CLOSE_BY_CANDLE_SL", "MANUAL", "EOD"
    price: Decimal # Current price for exit
)
```

### MoveSL

```python
MoveSL(
    new_sl_price: Decimal  # New stop loss price
)
```

### PartialClose

```python
PartialClose(
    tp_level: str,         # "TP1", "TP2", "TP3"
    price: Decimal,        # Current price
    new_sl_price: Optional[Decimal]  # Move SL after partial close (e.g., to lock_profit)
)
```

### DoNothing

No fields. Returns when no action is required.

---

## Action Dispatch (Engine → PortfolioManager)

The `Engine._apply_action()` method dispatches each action:

| Action | PortfolioManager Call |
|--------|---------------------|
| `OpenPosition` | `portfolio.on_signal(_action_to_signal(action))` |
| `ClosePosition` | `portfolio.close_position(symbol, reason=action.reason, price=action.price)` |
| `MoveSL` | `portfolio.move_stop_loss(symbol, action.new_sl_price)` |
| `PartialClose` | `portfolio.execute_partial_close(symbol, action.tp_level, action.new_sl_price)` |
| `DoNothing` | (nothing) |

`_action_to_signal()` converts an `OpenPosition` into a `SignalEvent` with all TP/SL prices, allocations, and signal metadata.

---

## Context Flow

```
Engine stores:  contexts["BTC/USDT"] = ContextSnapshot(state="SCANNING")
                    │
                    ▼
Strategy:       analyze(symbol, df, position, context)
                    │
                    ▼
Returns:        AnalysisResult(actions=[...], new_context=ContextSnapshot(state="CONFIRMING", meta={...}))
                    │
                    ▼
Engine stores:  contexts["BTC/USDT"] = result.new_context
```

The `meta` dict in `ContextSnapshot` carries strategy-specific data (entry prices, flags, SL levels) that persists between calls.

---

## Reusable Utilities

### SLTPCalculator (`app/trading/sl_tp_calculator.py`)

Static utility for direction-aware SL/TP/sizing calculations. All methods accept a `side` parameter (`"BUY"` or `"SELL"`):

- `compute_soft_sl(df, side, lookback)` — Soft SL from swing high/low
- `compute_disaster_sl(entry_price, soft_sl_price, side, multiplier)` — Hard SL at N× distance
- `compute_tp_price(entry_price, sl_price, side, rr_ratio, taker_fee, exit_fee)` — Fee-aware TP
- `compute_lock_profit_price(entry_price, soft_sl_price, side, lock_profit_rr, taker_fee)` — Lock-profit SL level
- `compute_position_size(...)` — Risk-based sizing (direction-agnostic)

### CrossoverIndicators (`app/data/indicators.py`)

Alternative `IIndicators` implementation for crossover-based strategies. Adds `rsi_14`, `rsi_ema9`, `rsi_wma45` columns:

- `compute(df)` — Add indicator columns
- `check_alignment(df, direction)` — Check RSI < EMA9 < WMA45 (bearish) or inverse (bullish)
- `detect_crossover(df, direction)` — Detect EMA9/WMA45 crossover on current candle
- `detect_bearish_divergence(df, lookback, pivot_strength)` — Price HH + RSI LH

---

## Implementing a New Strategy

See `docs/workflows/add-strategy.md` for the complete step-by-step guide. Key requirements:

1. Inherit from `BaseStrategy`
2. Define a config dataclass (e.g., `RsiMomentumConfig`) with all tunable parameters
3. Implement `analyze()` returning `AnalysisResult` with `new_context`
4. Never mutate `self` — all state goes through `ContextSnapshot`
5. Handle both "no position" and "has position" cases
6. For SHORT strategies: use `side="SELL"` in `OpenPosition`, place SL above entry, TP below entry
