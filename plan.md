# Plan: RSI Momentum Short Strategy — Phase 1 (Backend)

**Date:** 2026-03-18
**Branch:** `claude/add-short-strategy-68UFC`
**Scope:** Phase 1 — Core refactor for SHORT support + `rsi_momentum` strategy (short-only) + modular SL/TP calculator + strategy unit tests

Phase 2 (deferred): UI visualization for short trades, portfolio short tests, MockExchange short tests, integration backtest tests.

---

## Decision Log (from interview)

| Decision | Choice |
|----------|--------|
| Short support approach | Full core refactor (actions, portfolio, mock_exchange, engine) |
| Execution mode | Auto-execute (like existing) — no Telegram confirmation flow |
| Strategy coexistence | New separate strategy (`rsi_momentum`) alongside `rsi_no_retest` |
| Exit system | Rich exits always (multi-TP, partials, lock-profit, dual SL) |
| Position model | Signed amounts (negative for short) |
| PnL formula | `amount * (exit - entry)` — naturally handles both sides |
| SL/TP ownership | Strategy computes prices, PortfolioManager places orders |
| Pivot strength (N) for divergence | N=5 (11-bar pivot) |
| Signal persistence | Flexible — enter while alignment holds (not just crossover candle) |
| Indicator approach | New `CrossoverIndicators` class (separate from existing `Indicators`) |
| Opposite signal handling | Ignore per spec (don't close/reverse) |
| Strategy config location | Config dataclass in strategy file (not config.yaml) |
| Spread threshold | Configurable param, default 2.5 |
| Dual SL | Modular component; 30-candle highest high as soft SL, disaster at 3x distance |
| Lock-profit for shorts | Mirror existing logic (inverted direction) |
| SL/TP calculator | Static utility module (`app/core/sl_tp_calculator.py`) |
| Fee-aware TP | Move to SL/TP module |
| Warm-up handling | DoNothing + log message |
| Strategy name | `rsi_momentum` |
| Long entries | SHORT only — longs are handled by `rsi_no_retest` |
| Test scope (Phase 1) | Strategy unit tests only |

---

## Implementation Steps

### Step 1: Update `OpenPosition` action to support SHORT side

**File:** `app/core/actions.py`

Current `OpenPosition.side` is typed as `str` with value `"BUY"`. Changes:
- Update docstring from "Open a new long position" to "Open a new position (long or short)"
- No field changes needed — `side` already accepts `"BUY"` or `"SELL"`
- The strategy will pass `side="SELL"` for short entries

This is a minimal change — the dataclass already supports it structurally.

---

### Step 2: Create modular SL/TP calculator

**New file:** `app/core/sl_tp_calculator.py`

Static utility module with these functions:

```python
def compute_soft_sl(
    df: pd.DataFrame,
    side: str,           # "BUY" or "SELL"
    lookback: int = 30,
    mode: str = "swing",  # "swing" (highest_high/lowest_low), "close", "wick"
) -> Optional[Decimal]:
    """
    LONG (BUY): lowest low of last `lookback` candles
    SHORT (SELL): highest high of last `lookback` candles
    """

def compute_disaster_sl(
    entry_price: Decimal,
    soft_sl_price: Decimal,
    side: str,
    multiplier: Decimal = Decimal("3.0"),
) -> Decimal:
    """
    LONG: entry - (entry - soft_sl) * multiplier
    SHORT: entry + (soft_sl - entry) * multiplier
    """

def compute_tp_price(
    entry_price: Decimal,
    sl_price: Decimal,
    side: str,
    rr_ratio: Decimal,
    taker_fee: Decimal = Decimal("0"),
    exit_fee: Decimal = Decimal("0"),
) -> Optional[Decimal]:
    """
    Fee-aware TP calculation.
    LONG: target above entry
    SHORT: target below entry
    Risk = |entry - sl|
    Net target accounts for entry taker fee + exit fee (maker or taker)
    """

def compute_lock_profit_price(
    entry_price: Decimal,
    soft_sl_price: Decimal,
    side: str,
    lock_profit_rr: Decimal,
    taker_fee: Decimal = Decimal("0"),
) -> Optional[Decimal]:
    """
    Price at which to move SL to lock profit after TP1 hit.
    LONG: above entry (locks in profit if price drops back)
    SHORT: below entry (locks in profit if price rises back)
    """

def compute_position_size(
    entry_price: Decimal,
    sl_price: Decimal,
    risk_capital: Decimal,
    risk_per_trade_pct: Decimal,
    leverage: Decimal,
) -> Decimal:
    """
    Standard risk-based sizing: risk_amount / sl_distance_pct
    Direction-agnostic — uses absolute distance.
    """
```

Extracts and generalizes the existing logic from `rsi_no_retest._compute_price_at_rr()` and `portfolio._calculate_position_size()`.

---

### Step 3: Create `CrossoverIndicators` class

**New file:** `app/utils/crossover_indicators.py`

```python
class CrossoverIndicators(IIndicators):
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_ema_period: int = 9,
        rsi_wma_period: int = 45,
    ):
        pass

    def compute(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Adds columns: rsi_14, rsi_ema9, rsi_wma45
        Uses same RSI calculation approach as existing Indicators class.
        EMA and WMA are applied to the RSI series (not price).
        """

    def get_mode(self, df: pd.DataFrame) -> str:
        """Returns alignment state: 'BEARISH' if RSI < EMA9 < WMA45, else 'NEUTRAL'"""

    def detect_bearish_divergence(
        self,
        df: pd.DataFrame,
        lookback: int = 30,
        pivot_strength: int = 5,
    ) -> bool:
        """
        Detects bearish RSI divergence:
        1. Find swing highs in price using N=5 pivot (high > N bars on each side)
        2. Find corresponding RSI values at those swing high candles
        3. Check: price Higher High + RSI Lower High
        Returns True if valid divergence found in lookback window.
        """

    def detect_crossover(
        self,
        df: pd.DataFrame,
        direction: str = "bearish",  # "bearish" or "bullish"
    ) -> bool:
        """
        Bearish: EMA9[prev] >= WMA45[prev] AND EMA9[current] < WMA45[current]
        Bullish: EMA9[prev] <= WMA45[prev] AND EMA9[current] > WMA45[current]
        """

    def check_alignment(
        self,
        df: pd.DataFrame,
        direction: str = "bearish",
    ) -> bool:
        """
        Bearish: RSI < EMA9 < WMA45
        Bullish: RSI > EMA9 > WMA45
        """

    # IIndicators interface stubs
    def check_wma_retest(self, df, distance) -> bool: ...
    def calculate_price_at_rsi(self, df, target_rsi) -> Decimal: ...
```

---

### Step 4: Create `rsi_momentum` strategy

**New file:** `app/strategies/rsi_momentum.py`

#### Config dataclass (in same file):

```python
@dataclass(frozen=True)
class RsiMomentumConfig:
    # Indicator params
    rsi_period: int = 14
    ema_period: int = 9
    wma_period: int = 45

    # Entry conditions
    spread_threshold: float = 2.5       # S4: min WMA45 - EMA9 distance
    divergence_lookback: int = 30       # S5: candles to search for divergence
    pivot_strength: int = 5             # S5: N for swing high detection
    min_candles: int = 75               # Warm-up: 14 RSI + 45 WMA + buffer

    # Exit: SL
    sl_lookback: int = 30              # Highest high of N candles
    disaster_sl_multiplier: float = 3.0 # Hard SL at 3x soft SL distance

    # Exit: TP (configurable R:R ratios)
    tp1_rr: float = 1.0
    tp2_rr: float = 2.0
    tp3_rr: float = 3.0
    tp_count: int = 3
    tp1_close_pct: float = 0.50
    tp2_close_pct: float = 0.50

    # Exit: Lock profit
    move_sl_rr: float = 0.5            # Trigger: move SL when price reaches 0.5R
    lock_profit_rr: float = 0.2        # Lock: SL moves to 0.2R profit

    # Fees
    taker_fee: float = 0.0005          # 0.05%
    maker_fee: float = 0.0002          # 0.02%

    # Active trade management
    use_active_trades: bool = True
    candle_close_slippage_pct: float = 0.0
```

#### Strategy class:

```python
class RsiMomentumStrategy(BaseStrategy):
    """
    RSI Momentum strategy — SHORT entries only.

    Entry conditions (all must be true):
    S1: EMA9 crosses below WMA45 (or alignment still holds)
    S2: RSI < EMA9
    S3: EMA9 < WMA45
    S4: (WMA45 - EMA9) > spread_threshold
    S5: Bearish RSI divergence in last 30 candles

    Exit: Dual SL (soft at 30-candle highest high, disaster at 3x) +
          Multi-TP (configurable R:R) + Lock-profit after TP1
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = RsiMomentumConfig()  # uses defaults from dataclass
        self.indicators = CrossoverIndicators(
            rsi_period=self.cfg.rsi_period,
            rsi_ema_period=self.cfg.ema_period,
            rsi_wma_period=self.cfg.wma_period,
        )
        self.taker_fee = Decimal(str(self.cfg.taker_fee))
        self.maker_fee = Decimal(str(self.cfg.maker_fee))

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        """
        State machine:
        - SCANNING: Check for short entry conditions (S1-S5)
        - If position open + use_active_trades: manage exit (SL movement, lock-profit)
        """
```

#### analyze() logic flow:

**Entry path (no position open):**

1. Warm-up check: `if len(df) < self.cfg.min_candles: return DoNothing` + log
2. Compute indicators: `df_ind = self.indicators.compute(df)`
3. Check alignment (S2 + S3): `RSI < EMA9 < WMA45`
4. Check crossover OR continued alignment (S1 — flexible mode):
   - First check if crossover happened this candle
   - If not, check if context has `crossover_detected=True` and alignment still holds
5. Check spread (S4): `(WMA45 - EMA9) > spread_threshold`
6. Check divergence (S5): `self.indicators.detect_bearish_divergence(df_ind)`
7. If all pass:
   - Compute SL using `sl_tp_calculator.compute_soft_sl(df_ind, "SELL", lookback=30)`
   - Compute disaster SL using `sl_tp_calculator.compute_disaster_sl()`
   - Compute TP levels using `sl_tp_calculator.compute_tp_price()` for each level
   - Compute lock-profit price using `sl_tp_calculator.compute_lock_profit_price()`
   - Verify SL != entry (skip if zero risk distance)
   - Return `OpenPosition(side="SELL", ...)`

**Exit path (position open, use_active_trades=True):**

Mirror the existing rsi_no_retest exit logic but inverted for shorts:
1. **Pending candle SL**: If flagged, close at next candle open
2. **Move SL (lock profit)**: When `low <= move_trigger` (0.5R below entry for shorts), move SL to lock-profit price
3. **Candle-close SL**: If `close >= soft_sl` (price moved AGAINST short), flag pending exit

Note: all comparisons are inverted vs long:
- Long: "price went up enough" = `high >= trigger` → Short: "price went down enough" = `low <= trigger`
- Long: "SL hit" = `close <= sl` → Short: "SL hit" = `close >= sl`

**Context tracking:**
- `crossover_detected`: bool — set True when S1 fires, reset when alignment breaks
- `pending_candle_sl`: bool — flag for next-candle exit
- `soft_sl_price`: Decimal — tracked for candle-close SL checks
- `move_trigger_price`: Decimal — price level that triggers SL movement
- `sl_moved`: bool — whether lock-profit SL has been placed

---

### Step 5: Update PortfolioManager for SHORT support

**File:** `app/core/portfolio.py`

Changes needed:

1. **`on_signal()`**: Route `SELL` signals to a new `_handle_sell_signal()` (or refactor `_handle_buy_signal` to be side-aware)
   - Better approach: Rename to `_handle_entry_signal()` and make it side-aware
   - Entry order side: `signal.side` ("BUY" for long, "SELL" for short)
   - Exit orders (SL/TP) use opposite side: "SELL" for long exits, "BUY" for short exits

2. **`_handle_entry_signal()`** (refactored from `_handle_buy_signal`):
   - Market order with `side=signal.side`
   - SL `stop_market` with `side=opposite_side`
   - TP `limit` orders with `side=opposite_side`
   - Position amount: positive for long, **negative for short** (signed convention)

3. **`_handle_full_sell()`** → rename to `_handle_full_exit()`:
   - Exit side = opposite of position side
   - Use `abs(amount)` for order amount

4. **`_move_sl_to_entry()`**: Update SL order side based on position side

5. **`_place_tp_orders()`**: TP order side = opposite of position side

6. **`sync_tp_fills()`**: When a TP fills on a short position, the remaining amount moves toward zero (less negative)

7. **Position dataclass**: Already has `side` field. Amount will be negative for shorts.

8. **`_calculate_position_size()`**: Use absolute SL distance, then negate amount for shorts.

Key principle: **opposite_side = "BUY" if position.side == "SELL" else "SELL"**

---

### Step 6: Update MockExchange for SHORT support

**File:** `app/backtest/mock_exchange.py`

Changes needed:

1. **`create_order()` — market SELL entry (opening short):**
   - Store position as negative: `positions[symbol] -= amount`
   - Deduct margin: `margin = notional / leverage`
   - Track entry_price

2. **`_execute_order()` — BUY exit (closing short):**
   - PnL formula: `amount * (exit_price - entry_price)` where amount is negative
   - This naturally gives positive PnL when exit < entry (price dropped, short wins)
   - Return margin + PnL to balance

3. **`update_candle()` — order trigger logic for SHORT exits:**
   - BUY limit (TP for short): triggers when `low <= price` — already correct
   - BUY stop_market (SL for short): triggers when `high >= stopPrice` — already correct
   - The existing trigger logic already handles BUY-side orders correctly

4. **`check_liquidation()`:**
   - For shorts: unrealized PnL = `abs(amount) * (entry_price - current_price)`
   - When price goes UP, short loses → negative uPnL
   - Liquidation when total equity <= 0

5. **`fetch_positions()`**: Return signed amount (negative for shorts)

---

### Step 7: Register strategy in loader

**File:** `app/strategies/loader.py`

Add to `STRATEGY_MAP`:
```python
"rsi_momentum": RsiMomentumStrategy,
```

---

### Step 8: Write strategy unit tests

**New file:** `tests/test_rsi_momentum.py`

Test cases:

**Entry condition tests:**
- `test_short_entry_all_conditions_met` — S1-S5 all true → OpenPosition(side="SELL")
- `test_short_entry_no_crossover` — alignment holds but no crossover ever → DoNothing
- `test_short_entry_alignment_broken` — RSI > EMA9 → DoNothing
- `test_short_entry_spread_too_narrow` — (WMA45 - EMA9) < 2.5 → DoNothing
- `test_short_entry_no_divergence` — no swing highs in window → DoNothing
- `test_short_entry_flexible_signal` — crossover on candle N, alignment still holds on N+1 → OpenPosition
- `test_short_entry_signal_expires` — crossover on N, alignment breaks on N+1 → DoNothing

**Divergence detection tests:**
- `test_bearish_divergence_detected` — price HH + RSI LH → True
- `test_no_divergence_insufficient_pivots` — fewer than 2 swing highs → False
- `test_divergence_outside_lookback` — divergence exists but > 30 candles ago → False

**SL/TP tests:**
- `test_sl_is_highest_high_30_candles` — verify correct SL level for short
- `test_disaster_sl_at_3x` — disaster SL = entry + 3 * (highest_high - entry)
- `test_sl_equals_entry_skipped` — zero risk distance → DoNothing
- `test_tp_prices_below_entry` — all TP levels below entry for short

**Exit management tests (if use_active_trades):**
- `test_lock_profit_triggered` — price drops to 0.5R → MoveSL action
- `test_candle_close_sl_flags_exit` — close >= soft SL → pending flag
- `test_pending_sl_exits_next_candle` — ClosePosition on next candle

**Edge cases:**
- `test_warmup_insufficient_candles` — DoNothing + log
- `test_ignore_long_signal_when_short_open` — position exists, opposite signal → DoNothing
- `test_ignore_short_signal_when_position_open` — already in position → DoNothing

**Test approach:** Build synthetic DataFrames with controlled RSI/EMA9/WMA45 values. Use `PositionSnapshot` and `ContextSnapshot` mocks for exit management tests.

---

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `app/core/actions.py` | Modify | Update OpenPosition docstring for SHORT support |
| `app/core/sl_tp_calculator.py` | **New** | Modular SL/TP/sizing utility with static methods |
| `app/utils/crossover_indicators.py` | **New** | CrossoverIndicators class (RSI14 + EMA9/WMA45 of RSI + divergence) |
| `app/strategies/rsi_momentum.py` | **New** | RsiMomentumStrategy (short-only, rich exits) |
| `app/strategies/loader.py` | Modify | Register `rsi_momentum` in STRATEGY_MAP |
| `app/core/portfolio.py` | Modify | Refactor for side-aware entry/exit (SHORT support) |
| `app/backtest/mock_exchange.py` | Modify | Handle negative amounts, short PnL, short liquidation |
| `tests/test_rsi_momentum.py` | **New** | Strategy unit tests (~15-20 test cases) |

**New files:** 4
**Modified files:** 4

---

## Out of Scope (Phase 2)

- Backtest UI visualization for short trades (chart markers, trade table side column, color coding)
- Portfolio short tests (PortfolioManager with SHORT positions)
- MockExchange short tests (negative amounts, order matching)
- Integration backtest test (end-to-end short trade flow)
- SimExchange / BinanceAdapter SHORT support (live trading)
- Removing legacy strategy config from config.yaml
- Semi-automated execution flow (Telegram confirmation)
- Long entry conditions (L1-L3) for this strategy

---

## Risk & Mitigations

| Risk | Mitigation |
|------|------------|
| PortfolioManager refactor breaks existing long trades | Run existing test suite after changes; refactor is additive (new code path for SELL side) |
| MockExchange PnL formula breaks for longs | Signed amount formula `amount * (exit - entry)` works identically for positive amounts (longs) |
| Divergence detection too strict with N=5 | Configurable via `pivot_strength` param; can adjust without code changes |
| CrossoverIndicators diverges from existing Indicators | Separate class by design — no risk of breaking rsi_no_retest |
