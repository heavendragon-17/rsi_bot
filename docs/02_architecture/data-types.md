# Data Types Reference

> Deep-dive into every key data type used across the RSI bot system. Covers snapshots, events, actions, configuration, and DataFrame schemas. Consult this when you need to know exact field names, types, defaults, or validation rules.

---

## Table of Contents

- [Snapshots (Strategy Input)](#snapshots-strategy-input)
  - [PositionSnapshot](#positionsnapshot)
  - [ContextSnapshot](#contextsnapshot)
- [AnalysisResult (Strategy Output)](#analysisresult-strategy-output)
- [Action Types](#action-types)
  - [OpenPosition](#openposition)
  - [ClosePosition](#closeposition)
  - [MoveSL](#movesl)
  - [PartialClose](#partialclose)
  - [SendAlert](#sendalert)
  - [DoNothing](#donothing)
  - [Action Union Type](#action-union-type)
- [Events](#events)
  - [Candle](#candle)
  - [MarketEvent](#marketevent)
  - [SignalEvent](#signalevent)
  - [OrderEvent](#orderevent)
  - [TPSLEvent](#tpslevent)
  - [Engine Events](#engine-events)
- [Configuration Types](#configuration-types)
  - [AppConfig](#appconfig)
  - [ExchangeConfig](#exchangeconfig)
  - [RiskConfig](#riskconfig)
  - [NotificationConfig](#notificationconfig)
  - [BacktestConfig](#backtestconfig)
  - [PaperSimConfig](#papersimconfig)
- [DataFrame Schema](#dataframe-schema)

---

## Snapshots (Strategy Input)

Snapshots are **frozen (immutable) dataclasses** passed to `Strategy.analyze()`. They provide read-only views of system state so the strategy remains stateless and side-effect-free.

**File**: `app/core/snapshots.py`

### PositionSnapshot

Read-only view of the current position state, provided by `PortfolioManager.get_position_snapshot()`.

```python
@dataclass(frozen=True)
class PositionSnapshot:
    has_position: bool
    symbol: str
    side: str = "BUY"
    entry_price: Decimal = Decimal("0")
    current_sl: Decimal = Decimal("0")
    soft_sl: Optional[Decimal] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    lock_profit_triggered: bool = False
    unrealized_pnl: Optional[Decimal] = None
```

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `has_position` | `bool` | (required) | Whether there is an active position for this symbol | `True` |
| `symbol` | `str` | (required) | Trading pair identifier | `"BTC/USDT"` |
| `side` | `str` | `"BUY"` | Position side: `"BUY"` (long) or `"SELL"` (short) | `"BUY"` or `"SELL"` |
| `entry_price` | `Decimal` | `Decimal("0")` | Average entry price of the position | `Decimal("97500.50")` |
| `current_sl` | `Decimal` | `Decimal("0")` | Current hard stop-loss price (on exchange as `stop_market` order) | `Decimal("96000.00")` |
| `soft_sl` | `Optional[Decimal]` | `None` | Soft stop-loss price (candle-close based exit, not an exchange order) | `Decimal("96500.00")` |
| `tp1_hit` | `bool` | `False` | Whether TP1 (R60 level) has been triggered and partially closed | `True` |
| `tp2_hit` | `bool` | `False` | Whether TP2 (R70 level) has been triggered and partially closed | `False` |
| `tp3_hit` | `bool` | `False` | Whether TP3 (R80 level) has been triggered (full exit) | `False` |
| `lock_profit_triggered` | `bool` | `False` | Whether the lock-profit mechanism has moved SL to breakeven (0.2R level) | `False` |
| `unrealized_pnl` | `Optional[Decimal]` | `None` | Current unrealized PnL from the exchange. `None` if not available. | `Decimal("125.30")` |

**When passed to analyze()**:
- If no position exists: `PositionSnapshot(has_position=False, symbol="BTC/USDT")`
- If a position exists: All fields populated from `PortfolioManager` internal state

### ContextSnapshot

Read-only view of the strategy state machine. The runner stores one `ContextSnapshot` per symbol and passes it on each `analyze()` call. The strategy returns a new `ContextSnapshot` in `AnalysisResult.new_context`.

```python
@dataclass(frozen=True)
class ContextSnapshot:
    state: str = "SCANNING"
    soft_sl_price: Optional[Decimal] = None
    meta: Optional[Dict[str, Any]] = None  # defaults to {} via __post_init__
```

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `state` | `str` | `"SCANNING"` | Current state machine phase | `"CONFIRMING"` |
| `soft_sl_price` | `Optional[Decimal]` | `None` | Current soft SL price (updated when SL is moved) | `Decimal("96500.00")` |
| `meta` | `Optional[Dict[str, Any]]` | `{}` (via `__post_init__`) | Arbitrary strategy-owned metadata dict | See below |

#### State Machine

The strategy operates as a two-state machine:

```
                 signal detected
    ┌──────────┐ ──────────────> ┌────────────┐
    │ SCANNING │                 │ CONFIRMING │
    │          │ <────────────── │            │
    └──────────┘  confirmation   └────────────┘
                  failed / position
                  opened
```

- **SCANNING**: Looking for potential entry signals. No active candidate.
- **CONFIRMING**: A potential signal was detected. Waiting for confirmation candle(s) before opening a position.

#### Meta Dict Keys (strategy-owned)

The `meta` dict is owned by the strategy. Common keys used by `RsiNoRetestStrategy`:

| Key | Type | Description |
|-----|------|-------------|
| `entry_price` | `float` | Candidate entry price during CONFIRMING |
| `sl_price` | `float` | Candidate SL price during CONFIRMING |
| `original_soft_sl` | `float` | Original soft SL price at position open |
| `disaster_sl_price` | `float` | Hard disaster SL (3x distance from entry) |
| `tp1_price` | `float` | TP1 target price (R60 level) |
| `tp2_price` | `float` | TP2 target price (R70 level) |
| `tp3_price` | `float` | TP3 target price (R80 level) |
| `moved_sl_to_entry` | `bool` | Whether SL has been moved to breakeven |
| `pending_candle_sl` | `bool` | Whether a soft-SL candle-close exit is pending (2-candle pattern) |
| `lock_profit_price` | `float` | Price level at which to lock profit (move SL to entry) |
| `tp_allocations` | `dict` | Dynamic TP allocation percentages, e.g. `{"TP1": 0.5, "TP2": 1.0}` |
| `signal_class` | `int` | Quality classification of the signal (1=optimal, 2=acceptable) |

**Additional keys used by `RsiMomentumStrategy`** (stored via `TradeState` dataclass):

| Key | Type | Description |
|-----|------|-------------|
| `original_soft_sl` | `Decimal` | Original soft SL before any moves |
| `disaster_sl_price` | `Decimal` | Hard SL on exchange (stop_market BUY order for shorts) |
| `move_trigger` | `Decimal` | Pre-computed price level to trigger lock-profit |
| `crossover_detected` | `bool` | Whether a bearish crossover has been detected (signal persistence) |

---

## AnalysisResult (Strategy Output)

**File**: `app/core/analysis_result.py`

Returned by `Strategy.analyze()`. The strategy never mutates state directly -- it returns actions and the new context, and the runner applies them.

```python
@dataclass(frozen=True)
class AnalysisResult:
    actions: List[Action]
    new_context: ContextSnapshot
```

| Field | Type | Description |
|-------|------|-------------|
| `actions` | `List[Action]` | Ordered list of actions to execute. Usually contains 1 action, but can contain multiple (e.g., `MoveSL` + `PartialClose`). |
| `new_context` | `ContextSnapshot` | Updated context to store for the next `analyze()` call. |

**Runner dispatch logic** (from `MultiSymbolRunner._run_symbol_loop`):

```python
for action in result.actions:
    if isinstance(action, OpenPosition):
        signal = self._action_to_signal(action)
        portfolio.on_signal(signal)
    elif isinstance(action, ClosePosition):
        portfolio.close_position(action.symbol, reason=action.reason, price=action.price)
    elif isinstance(action, MoveSL):
        portfolio.move_stop_loss(action.symbol, action.new_sl_price)
    elif isinstance(action, PartialClose):
        portfolio.execute_partial_close(action.symbol, action.tp_level, new_sl_price=action.new_sl_price)
    # DoNothing: no-op
```

---

## Action Types

**File**: `app/core/actions.py`

All action types are frozen dataclasses. Each is self-describing and carries all data needed for execution.

### OpenPosition

Open a new position (long or short). Converted to `SignalEvent` by the runner before passing to `PortfolioManager.on_signal()`.

```python
@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    side: str
    entry_price: Decimal
    sl_price: Decimal
    soft_sl_price: Optional[Decimal]
    tp_prices: List[Decimal]
    tp_allocations: Optional[dict]
    lock_profit_price: Optional[Decimal]
    signal_class: int
    reason: str
```

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `symbol` | `str` | Trading pair | `"BTC/USDT"` |
| `side` | `str` | Position side: `"BUY"` for long, `"SELL"` for short | `"BUY"` or `"SELL"` |
| `entry_price` | `Decimal` | Current market price at signal time | `Decimal("97500.00")` |
| `sl_price` | `Decimal` | Hard/disaster SL price (placed as `stop_market` on exchange) | `Decimal("94500.00")` |
| `soft_sl_price` | `Optional[Decimal]` | Soft SL price (candle-close exit level, R40 - buffer) | `Decimal("96500.00")` |
| `tp_prices` | `List[Decimal]` | TP target prices `[tp1, tp2, tp3]` -- only non-None entries | `[Decimal("99000"), Decimal("101000"), Decimal("104000")]` |
| `tp_allocations` | `Optional[dict]` | Custom TP allocation percentages. `None` = use config defaults. | `{"TP1": 0.5, "TP2": 1.0}` |
| `lock_profit_price` | `Optional[Decimal]` | Price at which to move SL to breakeven (0.2R level) | `Decimal("98000.00")` |
| `signal_class` | `int` | Signal quality: 1=optimal (WMA45 in 40-46), 2=acceptable (WMA45 in 30-50) | `2` |
| `reason` | `str` | Human-readable reason for the signal | `"RSI bounced off WMA45 at 42.5"` |

### ClosePosition

Close the current position entirely (full exit).

```python
@dataclass(frozen=True)
class ClosePosition:
    symbol: str
    reason: str
    price: Optional[Decimal] = None
```

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `symbol` | `str` | (required) | Trading pair | `"BTC/USDT"` |
| `reason` | `str` | (required) | Exit reason | `"Soft SL triggered (candle close below 96500)"` |
| `price` | `Optional[Decimal]` | `None` | Exit price. `None` = market order. Set for candle-close exits. | `Decimal("96400.00")` |

### MoveSL

Move the stop loss to a new price level.

```python
@dataclass(frozen=True)
class MoveSL:
    symbol: str
    new_sl_price: Decimal
    reason: str
```

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `symbol` | `str` | Trading pair | `"BTC/USDT"` |
| `new_sl_price` | `Decimal` | New SL price to set | `Decimal("97500.00")` |
| `reason` | `str` | Reason for moving SL | `"TP1 hit, moving SL to entry"` |

### PartialClose

Partially close position at a take-profit level. Optionally moves SL after the partial close.

```python
@dataclass(frozen=True)
class PartialClose:
    symbol: str
    tp_level: str
    price: Decimal
    reason: str
    new_sl_price: Optional[Decimal] = None
```

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `symbol` | `str` | (required) | Trading pair | `"BTC/USDT"` |
| `tp_level` | `str` | (required) | Which TP level was hit | `"TP1"`, `"TP2"`, `"TP3"` |
| `price` | `Decimal` | (required) | Price at which TP was hit | `Decimal("99000.00")` |
| `reason` | `str` | (required) | Reason for partial close | `"TP1 hit at R60 level"` |
| `new_sl_price` | `Optional[Decimal]` | `None` | Move SL to this price after partial close. Common: move to entry after TP1. | `Decimal("97500.00")` |

### SendAlert

Dispatch a notification message (e.g. Telegram) without touching the portfolio. Used by alert-only strategies that surface market conditions without placing orders.

```python
@dataclass(frozen=True)
class SendAlert:
    symbol: str
    message: str
    tier: str = ""  # free-form label (e.g. "warning", "strong")
```

The runner forwards `message` to `notification_service.send_message()`. `tier` is for log context only and does not gate dispatch.

### DoNothing

Explicit no-op. Makes the return type non-optional -- every `analyze()` call returns at least `[DoNothing()]`.

```python
@dataclass(frozen=True)
class DoNothing:
    pass
```

No fields. The runner ignores this action type entirely.

### Side Constants and Utilities

```python
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

def opposite_side(side: str) -> str:
    """Return the opposite side. BUY→SELL, SELL→BUY."""
```

Exit reason constants: `EXIT_CLOSE_BY_CANDLE_SL = "CLOSE_BY_CANDLE_SL"` (used by `rsi_momentum` for candle-close SL exits).

### Action Union Type

```python
Action = Union[OpenPosition, ClosePosition, MoveSL, PartialClose, SendAlert, DoNothing]
```

Use `isinstance()` checks to dispatch actions. The runner processes actions in order.

---

## Events

**File**: `app/core/events.py`

### Candle

OHLCV candle data with `Decimal` precision for all price fields.

```python
@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    closed: bool
```

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `symbol` | `str` | Trading pair | `"BTC/USDT"` |
| `timestamp` | `datetime` | Candle open time | `datetime(2026, 2, 25, 10, 30)` |
| `open` | `Decimal` | Open price | `Decimal("97500.50")` |
| `high` | `Decimal` | High price | `Decimal("97800.00")` |
| `low` | `Decimal` | Low price | `Decimal("97400.00")` |
| `close` | `Decimal` | Close price | `Decimal("97750.25")` |
| `volume` | `Decimal` | Volume | `Decimal("1234.567")` |
| `closed` | `bool` | Whether this candle is finalized (closed) or still forming | `True` |

### EventType (Enum)

```python
class EventType(Enum):
    TICK_UPDATE = "TICK_UPDATE"    # Candle still forming (real-time update)
    KLINE_CLOSE = "KLINE_CLOSE"   # Candle just closed (confirmed)
```

### MarketEvent

Wrapper event emitted when market data arrives from the stream.

```python
@dataclass
class MarketEvent:
    type: EventType
    exchange: str
    payload: Candle
    received_at: datetime = field(default_factory=datetime.now)
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `EventType` | `TICK_UPDATE` or `KLINE_CLOSE` |
| `exchange` | `str` | Exchange name (e.g., `"binance"`) |
| `payload` | `Candle` | The candle data |
| `received_at` | `datetime` | When the event was received locally |

### SignalEvent

Signal emitted by the strategy layer. Bridges the gap between `OpenPosition` action and `PortfolioManager`. The runner converts `OpenPosition` to `SignalEvent` via `_action_to_signal()`.

```python
@dataclass
class SignalEvent:
    symbol: str
    signal_type: str
    price: Decimal
    timestamp: datetime
    reason: str = ""
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    soft_sl_price: Optional[Decimal] = None
    signal_class: int = 2
    lock_profit_price: Optional[Decimal] = None
    tp_allocations: Optional[dict] = field(default=None)
```

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `symbol` | `str` | (required) | Trading pair | `"BTC/USDT"` |
| `signal_type` | `str` | (required) | `"BUY"` for long entry, `"SELL"` for short entry | `"BUY"` or `"SELL"` |
| `price` | `Decimal` | (required) | Signal price (entry price) | `Decimal("97500.00")` |
| `timestamp` | `datetime` | (required) | When the signal was generated | `datetime.now()` |
| `reason` | `str` | `""` | Human-readable reason | `"RSI bounced off WMA45"` |
| `tp1_price` | `Optional[Decimal]` | `None` | TP1 target (R60 level) | `Decimal("99000.00")` |
| `tp2_price` | `Optional[Decimal]` | `None` | TP2 target (R70 level) | `Decimal("101000.00")` |
| `tp3_price` | `Optional[Decimal]` | `None` | TP3 target (R80 level) | `Decimal("104000.00")` |
| `sl_price` | `Optional[Decimal]` | `None` | Hard/disaster SL (3x distance) | `Decimal("94500.00")` |
| `soft_sl_price` | `Optional[Decimal]` | `None` | Soft SL (candle-close exit) | `Decimal("96500.00")` |
| `signal_class` | `int` | `2` | Signal quality: 1=optimal, 2=acceptable | `1` |
| `lock_profit_price` | `Optional[Decimal]` | `None` | Lock-profit trigger price (0.2R) | `Decimal("98000.00")` |
| `tp_allocations` | `Optional[dict]` | `None` | Custom TP allocations. `None` = use config defaults. | `{"TP1": 0.5, "TP2": 1.0}` |

### OrderEvent

Order event to be executed by the exchange. Used internally.

```python
@dataclass
class OrderEvent:
    symbol: str
    order_type: str    # MARKET, LIMIT
    side: str          # BUY, SELL
    amount: Decimal
    price: Optional[Decimal] = None
```

### TPSLEvent

Take-profit or stop-loss trigger event. Used internally for TP/SL management.

```python
@dataclass
class TPSLEvent:
    symbol: str
    event_type: str         # TP1, TP2, TP3, SL
    trigger_price: Decimal
    close_percentage: Decimal  # 0.0 - 1.0
    timestamp: datetime
```

### Engine Events

Used by the unified `BacktestEngine` / `LiveEngine` event loop (PR7).

#### TickEvent

```python
@dataclass
class TickEvent:
    symbol: str
    price: Decimal
    timestamp: datetime
    volume: Optional[Decimal] = None
```

Real-time price tick from WebSocket or historical replay.

#### CandleCloseEvent

```python
@dataclass
class CandleCloseEvent:
    candle: Candle
    df: Optional[pd.DataFrame] = None
```

A candle has closed. The optional `df` field carries a pre-built DataFrame with indicators already computed (used by `BacktestEventSource`). When `df` is `None`, the engine fetches the DataFrame from its data store.

#### EngineStopEvent

```python
@dataclass
class EngineStopEvent:
    reason: str = "normal"
```

Signals the engine to stop processing.

#### EngineEvent (Union)

```python
EngineEvent = Union[TickEvent, CandleCloseEvent, EngineStopEvent]
```

---

## Configuration Types

**File**: `app/core/config.py`

All configuration types are **frozen dataclasses** (`@dataclass(frozen=True)`) -- immutable after construction. Each sub-config validates its fields in `__post_init__`.

### AppConfig

Top-level application config. Loaded once at startup from `config.yaml`. Passed to constructors (not a global singleton).

```python
@dataclass(frozen=True)
class AppConfig:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    paper_sim: PaperSimConfig = field(default_factory=PaperSimConfig)
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy_name: str = "rsi_no_retest"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    timeframe: str = "5m"
    warmup_candles: int = 200
    debug: bool = False
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exchange` | `ExchangeConfig` | `ExchangeConfig()` | Exchange connection settings |
| `risk` | `RiskConfig` | `RiskConfig()` | Risk management parameters |
| `notification` | `NotificationConfig` | `NotificationConfig()` | Notification service flags |
| `backtest` | `BacktestConfig` | `BacktestConfig()` | Backtest-specific settings |
| `paper_sim` | `PaperSimConfig` | `PaperSimConfig()` | Local simulation settings |
| `symbols` | `List[str]` | `["BTC/USDT"]` | Trading pairs to monitor |
| `strategy_name` | `str` | `"rsi_no_retest"` | Strategy to instantiate |
| `strategy_params` | `Dict[str, Any]` | `{}` | Extra params passed to strategy constructor |
| `timeframe` | `str` | `"5m"` | Candle timeframe |
| `warmup_candles` | `int` | `200` | Number of historical candles to fetch on startup |
| `debug` | `bool` | `False` | Enable debug mode (verbose logging) |

**Key methods**:
- `AppConfig.from_yaml(path: str) -> AppConfig` -- Load and validate from YAML file
- `AppConfig.to_legacy_dict() -> dict` -- Convert to raw dict for backward-compatible constructors

### ExchangeConfig

```python
@dataclass(frozen=True)
class ExchangeConfig:
    name: str = "binanceusdm"
    mode: str = "mock"
    leverage: int = 10
    margin_type: str = "ISOLATED"
```

| Field | Type | Default | Valid Values | Validation |
|-------|------|---------|--------------|------------|
| `name` | `str` | `"binanceusdm"` | `binanceusdm`, `binance`, `hyperliquid`, `lighter` | `ValueError` if invalid |
| `mode` | `str` | `"mock"` | `mock`, `sim`, `paper`, `testnet`, `live` | `ValueError` if invalid |
| `leverage` | `int` | `10` | 1-125 | Validated in `RiskConfig` |
| `margin_type` | `str` | `"ISOLATED"` | `ISOLATED`, `CROSSED` | Not validated (passed to exchange) |

### RiskConfig

```python
@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: Decimal = Decimal("0.02")
    max_position_size_pct: Decimal = Decimal("0.99")
    leverage: int = 10
    use_initial_capital_for_risk: bool = False
    use_risk_based_sizing: bool = True
    tp1_close_pct: Decimal = Decimal("0.33")
    tp2_close_pct: Decimal = Decimal("0.50")
    min_sl_distance_pct: Decimal = Decimal("0.003")
```

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `risk_per_trade_pct` | `Decimal` | `0.02` | `0 < x <= 0.1` | Risk per trade as fraction of balance (2% = 0.02) |
| `max_position_size_pct` | `Decimal` | `0.99` | -- | Maximum position size as fraction of balance |
| `leverage` | `int` | `10` | `1 <= x <= 125` | Leverage multiplier |
| `use_initial_capital_for_risk` | `bool` | `False` | -- | If `True`, always use initial capital for risk sizing (not current balance) |
| `use_risk_based_sizing` | `bool` | `True` | -- | If `True`, use risk-based position sizing. If `False`, use max_position_size_pct. |
| `tp1_close_pct` | `Decimal` | `0.33` | -- | Fraction of position to close at TP1 (33%) |
| `tp2_close_pct` | `Decimal` | `0.50` | -- | Fraction of remaining position to close at TP2 (50%) |
| `min_sl_distance_pct` | `Decimal` | `0.003` | -- | Minimum SL distance as percentage of price (0.3%) |

### NotificationConfig

```python
@dataclass(frozen=True)
class NotificationConfig:
    telegram_enabled: bool = True
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `telegram_enabled` | `bool` | `True` | Enable Telegram bot notifications. Falls back to `NullNotifier` if init fails. |

### BacktestConfig

```python
@dataclass(frozen=True)
class BacktestConfig:
    initial_balance: Decimal = Decimal("10000")
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `initial_balance` | `Decimal` | `10000` | Starting balance for backtest simulation |

### PaperSimConfig

```python
@dataclass(frozen=True)
class PaperSimConfig:
    initial_balance: Decimal = Decimal("10000")
    tick_sample_interval_ms: int = 500
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `initial_balance` | `Decimal` | `10000` | Starting balance for paper simulation |
| `tick_sample_interval_ms` | `int` | `500` | How often to sample aggTrade ticks for order matching (milliseconds) |

---

## DataFrame Schema

The `MarketDataStore.get_dataframe(symbol)` returns a pandas DataFrame with the following columns. The index is `timestamp` (datetime).

### Base Columns (from MarketDataStore)

| Column | dtype | Source | Description |
|--------|-------|--------|-------------|
| `open` | `float64` | Candle | Open price (float for pandas vectorized operations) |
| `high` | `float64` | Candle | High price |
| `low` | `float64` | Candle | Low price |
| `close` | `float64` | Candle | Close price |
| `volume` | `float64` | Candle | Trading volume |
| `closed` | `bool` | Candle | Whether candle is finalized |
| `open_dec` | `Decimal` | Candle | Open price (Decimal precision) |
| `high_dec` | `Decimal` | Candle | High price (Decimal precision) |
| `low_dec` | `Decimal` | Candle | Low price (Decimal precision) |
| `close_dec` | `Decimal` | Candle | Close price (Decimal precision) |

**Index**: `timestamp` (datetime) -- the candle open time.

### Computed Indicator Columns (after IIndicators.compute())

These columns are added by the `IIndicators.compute()` call before the DataFrame is passed to `Strategy.analyze()`. All indicators are now computed by the unified `Indicators` class (`app/data/indicators.py`).

**Indicators** (used by all strategies):

| Column | dtype | Description |
|--------|-------|-------------|
| `rsi_14` | `float64` | Relative Strength Index (14-period) |
| `rsi_ema9` | `float64` | EMA(9) of RSI (signal line) |
| `rsi_wma45` | `float64` | WMA(45) of RSI (trend baseline) |
| `ema200` | `float64` | Exponential Moving Average of price (200-period, trend filter) |

### Memory Constraints

- **Maximum candles in RAM**: 6,000 per symbol (`MAX_CANDLES_IN_RAM` in `app/core/constants.py`)
- When the limit is exceeded, oldest candles are dropped via `df.tail(MAX_CANDLES_IN_RAM)`
- The `get_dataframe()` method returns a **copy** of the internal DataFrame (thread safety)

### Candle Update Behavior

When `update_candle()` is called:
1. If the candle timestamp matches the last row's timestamp: **update in place** (real-time tick update of forming candle)
2. If the candle timestamp is new: **append** a new row (new candle)

This means the last row in the DataFrame may represent a still-forming candle (`closed=False`) during live trading. The strategy loop in `MultiSymbolRunner` checks `last_row.get('closed', False)` and only processes closed candles.

---

## Key Source Files

| File | Types Defined |
|------|---------------|
| `app/core/snapshots.py` | `PositionSnapshot`, `ContextSnapshot` |
| `app/core/analysis_result.py` | `AnalysisResult` |
| `app/core/actions.py` | `OpenPosition`, `ClosePosition`, `MoveSL`, `PartialClose`, `DoNothing`, `Action`, `SIDE_BUY`, `SIDE_SELL`, `opposite_side()` |
| `app/core/events.py` | `Candle`, `EventType`, `MarketEvent`, `SignalEvent`, `OrderEvent`, `TPSLEvent`, `TickEvent`, `CandleCloseEvent`, `EngineStopEvent`, `EngineEvent` |
| `app/core/config.py` | `AppConfig`, `ExchangeConfig`, `RiskConfig`, `NotificationConfig`, `BacktestConfig`, `PaperSimConfig` |
| `app/data/store.py` | `MarketDataStore` (DataFrame schema) |
