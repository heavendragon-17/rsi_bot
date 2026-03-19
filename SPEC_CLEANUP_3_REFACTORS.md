# SPEC Part 3: Internal Refactors

> **Related**: [Overview](SPEC_CLEANUP_1_OVERVIEW.md) · [Migration](SPEC_CLEANUP_2_MIGRATION.md) · [Tech Debt](SPEC_CLEANUP_4_TECH_DEBT.md) · [Agent Strategy](SPEC_CLEANUP_5_AGENTS.md)

These refactors happen **after** the directory restructure (Phases 1-8 in Part 2). Each refactor is self-contained and can be done independently.

---

## Refactor 1: PortfolioManager Decomposition

### Current State
`app/core/portfolio.py` — 769 lines, single class handling:
- Position tracking and lifecycle (open/close/partial close)
- Risk-based position sizing (`_calculate_position_size`)
- SL/TP order placement, trailing SL, SL moves (~200 lines)
- Telegram notifications interleaved with execution logic
- Exchange synchronization (sync TP fills, cancel orders)
- Position model (`Position` dataclass, ~50 lines)

### Target State
`app/trading/portfolio/` with 6 files:

#### `models.py` (~60 lines)
Extract the `Position` dataclass from portfolio.py:
```python
@dataclass
class Position:
    symbol: str
    side: str          # "BUY" or "SELL"
    entry_price: Decimal
    amount: Decimal    # signed: positive=LONG, negative=SHORT
    sl_price: Optional[Decimal]
    sl_order_id: Optional[str]
    tp_order_ids: Dict[str, str]
    tp_allocations: Dict[str, float]
    tp1_hit: bool
    tp2_hit: bool
    tp3_hit: bool
    # ... remaining fields
```

#### `position_sizer.py` (~80 lines)
Extract from `_calculate_position_size()` (currently lines ~180-250):
```python
class PositionSizer:
    def __init__(self, risk_config: RiskConfig, exchange: IExchange): ...

    def calculate(self, symbol: str, entry_price: Decimal,
                  sl_price: Decimal, side: str) -> Decimal:
        """Risk-based position sizing. Returns amount in base asset."""

    def _get_available_balance(self) -> Decimal: ...
    def _apply_max_position_limit(self, amount: Decimal, price: Decimal) -> Decimal: ...
```

#### `sl_tp_manager.py` (~200 lines)
Extract SL/TP placement, modification, and tracking:
```python
class SLTPManager:
    def __init__(self, exchange: IExchange, risk_config: RiskConfig): ...

    def place_initial_sl_tp(self, position: Position, sl_price: Decimal,
                            tp_prices: List[Decimal]) -> None: ...
    def move_sl(self, position: Position, new_price: Decimal) -> None: ...
    def move_sl_to_entry(self, position: Position) -> None: ...
    def handle_partial_close(self, position: Position, tp_level: str,
                             new_sl_price: Optional[Decimal]) -> Optional[dict]: ...
    def sync_tp_fills(self, position: Position) -> List[str]: ...
    def cancel_all_orders(self, position: Position) -> None: ...
```

#### `notification_dispatch.py` (~80 lines)
Extract notification calls currently interleaved with execution:
```python
class NotificationDispatcher:
    def __init__(self, notifier: Optional[TelegramNotifier]): ...

    def notify_entry(self, symbol: str, side: str, price: Decimal,
                     amount: Decimal, sl: Decimal, tp_prices: List[Decimal]) -> None: ...
    def notify_exit(self, symbol: str, reason: str, pnl: Decimal) -> None: ...
    def notify_sl_moved(self, symbol: str, old_sl: Decimal, new_sl: Decimal) -> None: ...
    def notify_partial_close(self, symbol: str, tp_level: str, amount: Decimal) -> None: ...
```

#### `trade_executor.py` (~150 lines)
Core orchestration — the "thin" version of what PortfolioManager currently does:
```python
class TradeExecutor:
    def __init__(self, exchange: IExchange, sizer: PositionSizer,
                 sl_tp: SLTPManager, notifier: NotificationDispatcher): ...

    def open_position(self, signal: SignalEvent) -> Optional[Position]: ...
    def close_position(self, symbol: str, reason: str) -> Optional[dict]: ...
    def handle_signal(self, signal: SignalEvent) -> None: ...
```

#### `manager.py` (~100 lines)
Slim orchestrator that preserves the current `PortfolioManager` API for backward compat:
```python
class PortfolioManager:
    """Facade over decomposed portfolio components."""
    def __init__(self, exchange, risk_config, notifier=None):
        self.sizer = PositionSizer(risk_config, exchange)
        self.sl_tp = SLTPManager(exchange, risk_config)
        self.dispatcher = NotificationDispatcher(notifier)
        self.executor = TradeExecutor(exchange, self.sizer, self.sl_tp, self.dispatcher)
        self.positions = {}  # symbol -> Position

    # Delegate existing methods to components
    def open_position(self, signal): return self.executor.open_position(signal)
    def close_position(self, symbol, reason): return self.executor.close_position(symbol, reason)
    # ... etc
```

### Migration Steps
1. Create `models.py` — extract `Position` dataclass
2. Create `position_sizer.py` — extract sizing logic
3. Create `sl_tp_manager.py` — extract SL/TP logic
4. Create `notification_dispatch.py` — extract notification calls
5. Create `trade_executor.py` — wire components together
6. Slim down `manager.py` to facade
7. Update all imports in tests and consumers
8. Verify: all portfolio tests pass

---

## Refactor 2: Pluggable FillSimulator

### Current State
- `MockExchange` (879 lines): wick-based fill simulation, position tracking, margin calc, liquidation, funding fees, SL/TP triggers
- `SimExchange` (498 lines): tick-based fill simulation, own position tracking, own order state
- Both implement `IExchange` independently with duplicated logic for: order creation, position tracking, balance management, PnL calculation

### Target State

#### `app/trading/exchange/fill_simulator.py` (~250 lines)
```python
class FillMode(ABC):
    """Abstract fill mode — determines when/how orders get filled."""
    @abstractmethod
    def check_fills(self, pending_orders: List[Order], market_data: Any) -> List[Fill]: ...

class WickFillMode(FillMode):
    """Backtest: check fills against candle OHLC wicks."""
    def check_fills(self, pending_orders, candle: dict) -> List[Fill]:
        # Current MockExchange._check_stop_loss / _check_take_profit logic
        ...

class TickFillMode(FillMode):
    """Paper trading: check fills against individual tick prices."""
    def check_fills(self, pending_orders, tick_price: Decimal) -> List[Fill]:
        # Current SimExchange._scan_pending_orders logic
        ...

class FillSimulator:
    """Shared order matching and position management."""
    def __init__(self, fill_mode: FillMode, initial_balance: float,
                 leverage: int, maker_fee: float, taker_fee: float): ...

    def create_order(self, symbol, order_type, side, amount, price, params) -> dict: ...
    def cancel_order(self, order_id, symbol) -> dict: ...
    def process_market_data(self, data: Any) -> List[Fill]: ...  # delegates to fill_mode
    def get_position(self, symbol) -> dict: ...
    def get_balance(self) -> dict: ...
    def calculate_pnl(self, position, current_price) -> Decimal: ...
```

#### Updated `MockExchange` (~300 lines, down from 879)
```python
class MockExchange(IExchange):
    def __init__(self, initial_balance, leverage, maker_fee, taker_fee):
        self._sim = FillSimulator(
            WickFillMode(), initial_balance, leverage, maker_fee, taker_fee
        )
    # Delegates to self._sim, adds candle-feed-specific logic
    def feed_candle(self, symbol, candle): ...
```

#### Updated `SimExchange` (~200 lines, down from 498)
```python
class SimExchange(IExchange):
    def __init__(self, ...):
        self._sim = FillSimulator(
            TickFillMode(), initial_balance, leverage, maker_fee, taker_fee
        )
    # Delegates to self._sim, adds tick-feed-specific logic
    def on_tick(self, symbol, price): ...
```

### Migration Steps
1. Identify shared logic between MockExchange and SimExchange (order creation, position tracking, balance, PnL)
2. Create `FillMode` ABC with `WickFillMode` and `TickFillMode`
3. Create `FillSimulator` with shared logic
4. Refactor `MockExchange` to delegate to `FillSimulator`
5. Refactor `SimExchange` to delegate to `FillSimulator`
6. Verify: `test_mock_exchange_short.py`, `test_sim_exchange.py`, `test_sim_tick_scanner.py`, `test_normalized_orders.py` all pass

---

## Refactor 3: Indicator Merge

### Current State
- `app/utils/indicators.py` (273 lines) — `Indicators` class with `compute_all()`, used by `rsi_no_retest` and `rsi_wma_retest` (long strategies)
- `app/utils/crossover_indicators.py` (225 lines) — `CrossoverIndicators` class with `compute()`, used by `rsi_momentum` (short strategy)
- **Overlap**: Both compute RSI, EMA of RSI, WMA of RSI. Subtle differences in column naming and parameter handling.

### Target State
`app/data/indicators.py` (~350 lines) — single `Indicators` class:
```python
class Indicators:
    """Unified indicator computation for all RSI strategies."""

    @staticmethod
    def compute_all(df: pd.DataFrame, rsi_period=14, ema_length=9,
                    wma_length=45, price_ema_fast=21, price_ema_slow=200,
                    include_crossover=False) -> pd.DataFrame:
        """Full indicator suite for long strategies (no_retest, wma_retest)."""
        ...

    @staticmethod
    def compute_crossover(df: pd.DataFrame, rsi_period=14, ema_period=9,
                          wma_period=45) -> pd.DataFrame:
        """Crossover-specific indicators for short strategy (momentum)."""
        ...

    @staticmethod
    def rsi(series: pd.Series, period: int) -> pd.Series: ...

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series: ...

    @staticmethod
    def wma(series: pd.Series, period: int) -> pd.Series: ...
```

### Migration Steps
1. Create `app/data/indicators.py` with merged class
2. Ensure column names match what strategies expect (map any differences)
3. Update `rsi_momentum.py`: `from app.data.indicators import Indicators`
4. Update `rsi_no_retest.py`, `rsi_wma_retest.py`: same
5. Delete old `app/utils/indicators.py` and `app/utils/crossover_indicators.py`
6. Verify: `test_rsi_momentum.py`, `test_stateless_strategy.py` pass

---

## Refactor 4: Backtest Service Extraction

### Current State
`app/api/routes/backtest.py` (491 lines) mixes:
- HTTP request validation
- Backtest parameter building
- Multi-symbol orchestration logic
- SSE streaming logic
- Result aggregation and formatting
- Database queries

### Target State

#### `app/backtest/service.py` (~200 lines)
```python
class BacktestService:
    """Business logic for backtest operations."""

    def start_run(self, request: BacktestRequest) -> str:
        """Validate params, create DB run, submit to executor. Returns run_id."""

    def get_run_detail(self, run_id: str) -> RunDetail:
        """Fetch run metrics + trades from DB."""

    def get_timeseries(self, run_id: str) -> TimeseriesResponse:
        """Fetch equity/drawdown curves."""

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running backtest."""

    async def stream_progress(self, run_id: str) -> AsyncIterator[dict]:
        """Yield progress events for SSE."""
```

#### `app/api/routes/backtest_run.py` (~60 lines)
```python
router = APIRouter(prefix="/api/backtest")

@router.post("/run")
async def start_backtest(req: BacktestRequest):
    run_id = service.start_run(req)
    return BacktestStartResponse(run_id=run_id)

@router.delete("/{run_id}")
async def cancel_backtest(run_id: str):
    service.cancel_run(run_id)
```

#### `app/api/routes/backtest_results.py` (~80 lines)
```python
@router.get("/{run_id}")
async def get_run(run_id: str): ...

@router.get("/{run_id}/timeseries")
async def get_timeseries(run_id: str): ...
```

#### `app/api/routes/backtest_stream.py` (~50 lines)
```python
@router.get("/{run_id}/progress")
async def progress_stream(run_id: str):
    return StreamingResponse(service.stream_progress(run_id), ...)
```

### Migration Steps
1. Create `BacktestService` with logic extracted from route handlers
2. Split `backtest.py` into 3 route files
3. Update `app/api/main.py` to register new routers
4. Verify: `test_api_backtest.py` passes

---

## Refactor 5: Config Cleanup

### Current State
- `config.yaml` contains both general config AND strategy parameters
- Strategy params are also defined in each strategy's frozen dataclass (with defaults)
- Magic numbers scattered: `WARMUP=220` in 3 places, `MAX_CANDLES_IN_RAM=6000` in 1 place, fee defaults in `app/core/actions.py`
- `AppConfig.to_legacy_dict()` exists for backward compat

### Target State

#### `app/core/constants.py` (NEW)
```python
"""Centralized constants — single source of truth for magic numbers."""

# Warm-up period (candles to skip before strategy analysis)
WARMUP_CANDLES: int = 220

# Maximum candles held in RAM per symbol
MAX_CANDLES_IN_RAM: int = 6000

# Default fee rates (Binance USDT-M futures)
DEFAULT_TAKER_FEE: float = 0.0004
DEFAULT_MAKER_FEE: float = 0.0002
```

#### Updated `config.yaml`
Remove strategy-specific keys. Keep only:
```yaml
exchange:
  name: binanceusdm
  mode: mock
  leverage: 10
  margin_type: ISOLATED

risk:
  risk_per_trade_pct: 0.02
  max_position_size_pct: 0.99
  # ... general risk params only

trading:
  symbols: ["BTC/USDT"]
  timeframe: "5m"
  strategy: "rsi_momentum"
  warmup_candles: 220

notifications:
  telegram_enabled: true
```

#### Updated strategy files
Each strategy already has its own config dataclass (e.g., `RsiMomentumConfig`). This is already the pattern — just ensure ALL strategy-specific params are in the dataclass, not in YAML:

```python
# At the top of each strategy file:
# ═══════════════════════════════════════════════════
# STRATEGY PARAMETERS — edit these to tune the strategy
# ═══════════════════════════════════════════════════
@dataclass(frozen=True)
class RsiMomentumConfig:
    rsi_period: int = 14
    ema_period: int = 9
    # ... all params with sensible defaults
```

### Migration Steps
1. Create `app/core/constants.py` with all centralized constants
2. Update `app/backtest/engine.py`: replace `WARMUP = 220` with import from constants
3. Update `app/backtest/run_paper_tick_replay.py`: same (before deprecation)
4. Update `app/data/store.py`: replace `MAX_CANDLES_IN_RAM = 6000` with import
5. Move fee defaults from `app/core/actions.py` to `constants.py`, update imports
6. Remove strategy params from `config.yaml`
7. Update `AppConfig` to not expect strategy params
8. Remove `to_legacy_dict()` if no longer needed
9. Update docs: `docs/03_setup_and_installation/`, `wiki/getting-started.md`
10. Verify: `test_config.py`, `test_config_validation.py` pass

---

## Refactor 6: Strategy Shared Utils

### Current State
The 3 RSI strategies duplicate:
- Config dataclass construction from `strategy_params` dict (merge defaults with overrides)
- `TradeState` serialization/deserialization for `ContextSnapshot.state`
- Crossover detection logic (RSI crossing EMA/WMA)
- SL/TP ladder building from R:R ratios

### Target State
`app/trading/strategy/utils/` with 4 modules:

#### `config_helpers.py`
```python
def merge_config(config_cls: type, overrides: dict) -> Any:
    """Construct a frozen config dataclass, merging defaults with overrides.
    Handles type coercion and unknown-key warnings."""
```

#### `trade_state.py`
```python
@dataclass
class TradeState:
    """Common trade state tracked across candles via ContextSnapshot.state."""
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    sl_moved_to_entry: bool = False
    lock_profit_triggered: bool = False
    last_signal_bar: Optional[int] = None
    # ... common fields

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, d: dict) -> "TradeState": ...
```

#### `signal_detection.py`
```python
def detect_ema_crossover(df: pd.DataFrame, fast_col: str, slow_col: str) -> pd.Series:
    """Detect crossover (fast crosses above slow). Returns boolean Series."""

def detect_rsi_spread(df: pd.DataFrame, ema_col: str, wma_col: str,
                      min_spread: float) -> pd.Series:
    """Check if RSI spread exceeds threshold. Returns boolean Series."""
```

#### `sl_tp_builders.py`
```python
def build_tp_ladder(entry_price: float, sl_distance: float, side: str,
                    rr_ratios: List[float]) -> List[float]:
    """Build TP price ladder from R:R ratios. Direction-aware."""

def build_sl_from_lookback(df: pd.DataFrame, lookback: int, side: str,
                           mode: str = "lowest_close") -> float:
    """Calculate SL price from recent candle data."""
```

### Migration Steps
1. Create utils module with `__init__.py`
2. Extract duplicated config merge logic into `config_helpers.py`
3. Extract TradeState into `trade_state.py`
4. Extract signal detection wrappers into `signal_detection.py`
5. Extract SL/TP builders into `sl_tp_builders.py`
6. Update all 3 strategies to import from utils
7. Delete duplicated code from strategies
8. Verify: `test_rsi_momentum.py`, `test_stateless_strategy.py` pass

---

## Refactor Execution Order

These refactors can be parallelized in two groups:

**Group A (independent)**:
- Refactor 3: Indicator Merge
- Refactor 5: Config Cleanup
- Refactor 6: Strategy Shared Utils

**Group B (depends on structure being stable)**:
- Refactor 1: PortfolioManager Decomposition
- Refactor 2: FillSimulator Extraction
- Refactor 4: Backtest Service Extraction

Group A can run in parallel with Group B since they touch different files.

---

*Next: [SPEC Part 4: Tech Debt Inventory →](SPEC_CLEANUP_4_TECH_DEBT.md)*
