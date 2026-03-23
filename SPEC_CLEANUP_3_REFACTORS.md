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

## Refactor 3: Indicator Consolidation (Remove CrossoverIndicators)

### Current State
- `app/utils/indicators.py` (273 lines) — `Indicators` class with `compute()`, used by `rsi_no_retest` and `rsi_wma_retest` (long strategies)
- `app/utils/crossover_indicators.py` (225 lines) — `CrossoverIndicators` class with `compute()`, used by `rsi_momentum` (short strategy)
- **Overlap**: Both compute RSI, EMA9-of-RSI, WMA45-of-RSI with identical logic. The only real differences are:
  - Column naming (`rsi` vs `rsi_14`)
  - Default RSI period (`rsi_length=21` vs `rsi_period=14`)
  - `Indicators` adds price EMAs (EMA21, EMA200) and price-at-RSI calculation
  - `CrossoverIndicators` adds `detect_crossover()`, `check_alignment()`, `detect_bearish_divergence()`
- **Key insight**: Short entry = down cross (EMA9 crosses below WMA45), Long setup = up cross (EMA9 crosses above WMA45). Both sides use the same crossover detection — just with `direction="bearish"` vs `direction="bullish"`. There is no reason for two classes.

### Target State
`app/data/indicators.py` (~380 lines) — single `Indicators` class that serves ALL strategies:

```python
class Indicators(IIndicators):
    """Unified indicator computation for all RSI strategies.

    Computes RSI, EMA9-of-RSI, WMA45-of-RSI (shared by all strategies),
    plus optional price EMAs for long strategies.

    Crossover detection:
    - direction="bearish" (down cross) → SHORT entry signal
    - direction="bullish" (up cross)   → LONG setup signal
    """

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_ema_period: int = 9,
        rsi_wma_period: int = 45,
        price_ema_fast: int = 21,
        price_ema_slow: int = 200,
        include_price_emas: bool = False,
        enable_cache: bool = True,
    ):
        ...

    # --- IIndicators interface ---
    def compute(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Adds: rsi_14, rsi_ema9, rsi_wma45. Optionally: ema21, ema200."""
        ...

    def get_mode(self, df: pd.DataFrame) -> str: ...
    def check_wma_retest(self, df: pd.DataFrame, distance: float = 1.0) -> bool: ...
    def calculate_price_at_rsi(self, df: pd.DataFrame, target_rsi: float) -> Optional[Decimal]: ...

    # --- Crossover detection (shared by SHORT and LONG strategies) ---
    def detect_crossover(self, df: pd.DataFrame, direction: str = "bearish") -> bool:
        """Detect EMA9/WMA45 crossover on the most recent closed candle.
        direction='bearish' (down cross) → SHORT entry.
        direction='bullish' (up cross)   → LONG setup."""
        ...

    def check_alignment(self, df: pd.DataFrame, direction: str = "bearish") -> bool:
        """Check indicator alignment: bearish = RSI < EMA9 < WMA45, bullish = inverse."""
        ...

    def detect_bearish_divergence(self, df: pd.DataFrame, lookback: int = 30,
                                   pivot_strength: int = 5) -> bool:
        """Price HH + RSI LH in lookback window."""
        ...

    # --- Price ladder (long strategies only, requires include_price_emas=True) ---
    def calculate_price_at_rsi(self, df: pd.DataFrame, target_rsi: float) -> Optional[Decimal]: ...
    def check_r40_floor(self, df: pd.DataFrame, lookback: int = 5) -> bool: ...
```

**Column naming**: Standardize on `rsi_14`, `rsi_ema9`, `rsi_wma45` for all strategies. Update long strategy code to use these column names (currently uses `rsi`).

### Strategy Usage After Merge

```python
# rsi_momentum.py (SHORT) — down cross entry
self.indicators = Indicators(rsi_period=14, rsi_ema_period=9, rsi_wma_period=45)
crossover_now = self.indicators.detect_crossover(df, direction="bearish")  # down cross

# rsi_no_retest.py (LONG) — up cross setup
self.indicators = Indicators(rsi_period=21, rsi_ema_period=9, rsi_wma_period=45,
                              include_price_emas=True)
# Can now also use: self.indicators.detect_crossover(df, direction="bullish")

# rsi_wma_retest.py (LONG) — same as no_retest
self.indicators = Indicators(rsi_period=21, rsi_ema_period=9, rsi_wma_period=45,
                              include_price_emas=True)
```

### Migration Steps
1. Add crossover methods (`detect_crossover`, `check_alignment`, `detect_bearish_divergence`) from `CrossoverIndicators` into `Indicators`
2. Standardize column names to `rsi_14`, `rsi_ema9`, `rsi_wma45` everywhere
3. Add `include_price_emas` flag (default `False`) — only long strategies need EMA21/EMA200
4. Update `rsi_momentum.py`: `from app.data.indicators import Indicators` (was `CrossoverIndicators`)
5. Update `rsi_no_retest.py`, `rsi_wma_retest.py`: update column name references (`rsi` → `rsi_14`)
6. Delete `app/utils/crossover_indicators.py`
7. Update tests: `test_rsi_momentum.py` (remove `CrossoverIndicators` imports), `test_stateless_strategy.py`
8. Verify: all strategy tests pass, no references to `CrossoverIndicators` remain

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

**Missing API support**: The API only supports `single` and `portfolio` modes (auto-detected via `symbol` vs `symbols` fields). Two other backtest modes — `batch` (N independent backtests with separate balances, parallel execution) and `tick_replay` (tick-level simulation with SimExchange) — are CLI-only with no API routes. All 4 modes are core functionality and must be accessible from the UI.

#### Backtest Mode Differences

| | Single | Portfolio | Batch | Tick Replay |
|---|---|---|---|---|
| **Balance** | One symbol | Shared across symbols | Separate per symbol | One symbol |
| **Execution** | Sequential | Interleaved timeline | Parallel (ProcessPool) | Tick-by-tick replay |
| **Liquidation** | Per-symbol | Global (cross-symbol) | Per-symbol | Per-symbol |
| **Equity curve** | Per-symbol | Real-time portfolio-wide | Stitched post-hoc | Per-symbol |
| **Capital competition** | N/A | Yes — symbols compete for margin | None | N/A |
| **Use case** | Quick single test | Realistic multi-asset sim | Symbol/param screening | High-fidelity SL/TP fills |

### Target State

#### Updated `BacktestRequest` schema (`app/api/schemas.py`)
```python
from enum import Enum

class BacktestMode(str, Enum):
    SINGLE = "single"
    PORTFOLIO = "portfolio"
    BATCH = "batch"
    TICK_REPLAY = "tick_replay"

class BacktestRequest(BaseModel):
    """Unified backtest request with explicit mode selection."""
    mode: BacktestMode = BacktestMode.SINGLE   # Explicit mode (replaces auto-detection)
    symbol: str | None = None                   # single, tick_replay
    symbols: list[str] | None = None            # portfolio, batch
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: str = "10000.00"
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    fee_tier: str = "0.001"
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict[str, Any] = {}
    # Batch-specific
    max_workers: int | None = None              # batch only (default: CPU count)
    # Tick replay-specific
    tick_data_path: str | None = None           # tick_replay only (path to aggTrades CSV)

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "BacktestRequest":
        if self.mode in (BacktestMode.SINGLE, BacktestMode.TICK_REPLAY):
            if not self.symbol:
                raise ValueError(f"mode={self.mode.value} requires 'symbol'")
        elif self.mode in (BacktestMode.PORTFOLIO, BacktestMode.BATCH):
            if not self.symbols:
                raise ValueError(f"mode={self.mode.value} requires 'symbols'")
        # Backward compat: infer mode from symbol/symbols if mode not explicitly set
        return self
```

#### `app/backtest/service.py` (~250 lines)
```python
class BacktestService:
    """Business logic for backtest operations. Routes to the correct runner by mode."""

    def start_run(self, request: BacktestRequest) -> str:
        """Validate params, create DB run, route to correct runner, submit to executor. Returns run_id."""

    def _route_to_runner(self, request: BacktestRequest) -> callable:
        """Select runner based on mode: single → BacktestEngine, portfolio → PortfolioRunner,
        batch → BatchRunner, tick_replay → TickReplayRunner."""

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
1. Add `BacktestMode` enum and update `BacktestRequest` schema with explicit `mode` field
2. Create `BacktestService` with mode-routing logic extracted from route handlers
3. Split `backtest.py` into 3 route files
4. Wire `BatchRunner` and `TickReplayRunner` into `BacktestService._route_to_runner()`
5. Update `app/api/main.py` to register new routers
6. Verify: `test_api_backtest.py` passes (update tests to cover all 4 modes)

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

## Refactor 7: Backtest Runners Decomposition

### Context
These 3 files are **core backtest functions** used by the backtest UI — they are NOT dead code. The user plans to add probability/statistics analysis and AI-based strategy optimization in the near future, so the refactored structure must be extensible.

### Current State
- `app/backtest/run_batch_analysis.py` (962 lines) — multi-symbol parallel backtest + HTML report + CSV export. God file mixing CLI logic, data download, execution, reporting, and export.
- `app/backtest/run_paper_tick_replay.py` (553 lines) — tick-level simulation using SimExchange. Reasonably structured but has duplicated result computation.
- `app/backtest/run_portfolio_backtest.py` (317 lines) — unified multi-symbol portfolio backtest. Has duplicated `_enrich_round_trips()` and data download logic. Missing `_run_portfolio_backtest()` function that API routes expect.
- **Duplications**: `_enrich_round_trips()` (100% duplicate between batch + portfolio), data download/validation (~40 lines each, ~70% similar), `load_config()` (3 identical copies across backtest scripts).

### Target State

#### `app/backtest/runners/` — execution modes

##### `batch_runner.py` (~200 lines)
```python
class BatchRunner:
    """Multi-symbol parallel backtest orchestration."""

    def __init__(self, symbols: List[str], config: dict,
                 data_manager: DataManager): ...

    def run(self, max_workers: int = 4,
            progress_callback: Optional[Callable] = None) -> BatchResult: ...

    def _run_single_symbol(self, symbol: str) -> SymbolResult: ...
```

##### `portfolio_runner.py` (~200 lines)
```python
class PortfolioRunner:
    """Unified multi-symbol portfolio backtest."""

    def __init__(self, symbols: List[str], config: dict,
                 data_manager: DataManager): ...

    def run(self, progress_callback: Optional[Callable] = None) -> PortfolioResult: ...

    # API entry point (called from backtest routes)
    def run_portfolio_backtest(request: BacktestRequest) -> PortfolioResult: ...
```

##### `tick_replay.py` (~300 lines)
```python
class TickReplayRunner:
    """Tick-level simulation backtest using SimExchange."""

    def __init__(self, symbol: str, config: dict,
                 ohlc_path: str, tick_path: str): ...

    def run(self, progress_callback: Optional[Callable] = None) -> ReplayResult: ...

    def _compute_results(self) -> dict: ...
```

#### Shared utilities (extracted from runners)

##### `app/backtest/data_manager.py` (~100 lines)
```python
class DataManager:
    """Download, validate, and cache backtest data. Deduped from runners."""

    def ensure_data_available(self, symbol: str, timeframe: str,
                               limit: int = 5000) -> Path: ...
    def validate_csv(self, path: Path, min_rows: int = 100) -> bool: ...
    def get_csv_path(self, symbol: str, timeframe: str) -> Path: ...
```

##### `app/backtest/enrichment.py` (~60 lines)
```python
def enrich_round_trips(round_trips: List[dict], df: pd.DataFrame) -> List[dict]:
    """Add entry RSI/EMA/spread fields to round trip records. Shared by batch + portfolio."""
    ...
```

##### `app/backtest/export.py` (~120 lines)
```python
def export_signals_to_csv(trades: List[dict], path: Path, symbol: str) -> None:
    """Export per-symbol trade signals with timestamp handling."""
    ...

def export_combined_signals(symbol_csvs: List[Path], output_path: Path) -> None:
    """Combine individual signal CSVs into master CSV."""
    ...

def export_json_report(result: dict, path: Path) -> None:
    """Export JSON report for AI debugging."""
    ...
```

##### `app/backtest/batch_report.py` (~300 lines)
```python
class BatchHtmlGenerator:
    """Generate combined batch HTML report with portfolio overview.
    Extracted from run_batch_analysis.py."""
    ...
```

#### Future extensibility hooks (directories created but empty)
```
app/backtest/
├── optimization/          # Future: parameter sweeps, genetic algorithms, AI strategy finder
│   └── __init__.py
└── statistics/            # Future: Monte Carlo, probability analysis, confidence intervals
    └── __init__.py
```

### Migration Steps
1. Create `app/backtest/runners/` directory with `__init__.py`
2. Extract `DataManager` from download/validation logic duplicated across runners → `data_manager.py`
3. Extract `enrich_round_trips()` → `enrichment.py` (dedupe batch + portfolio)
4. Extract CSV/JSON export functions → `export.py`
5. Extract `BatchHtmlGenerator` → `batch_report.py`
6. Refactor `run_batch_analysis.py` → `runners/batch_runner.py` (BatchRunner class, ~200 lines)
7. Refactor `run_portfolio_backtest.py` → `runners/portfolio_runner.py` (PortfolioRunner class, ~200 lines). Add `run_portfolio_backtest()` API entry point.
8. Refactor `run_paper_tick_replay.py` → `runners/tick_replay.py` (TickReplayRunner class, ~300 lines)
9. Delete original 3 files after confirming all imports are updated
10. Wire ALL runners into `BacktestService._route_to_runner()` (from Refactor 4):
    - `mode=single` → `BacktestEngine` (existing)
    - `mode=portfolio` → `PortfolioRunner.run()`
    - `mode=batch` → `BatchRunner.run()` (**NEW** — was CLI-only)
    - `mode=tick_replay` → `TickReplayRunner.run()` (**NEW** — was CLI-only)
11. Update API routes to import from `runners/` instead of old paths
12. Create empty `optimization/` and `statistics/` directories with `__init__.py` for future work
13. Verify: all 4 backtest modes work via API, CLI entry points work, all tests pass

---

## Refactor Execution Order

These refactors can be parallelized in two groups:

**Group A (independent)**:
- Refactor 3: Indicator Consolidation
- Refactor 5: Config Cleanup
- Refactor 6: Strategy Shared Utils

**Group B (depends on structure being stable)**:
- Refactor 1: PortfolioManager Decomposition
- Refactor 2: FillSimulator Extraction
- Refactor 4: Backtest Service Extraction
- Refactor 7: Backtest Runners Decomposition

Group A can run in parallel with Group B since they touch different files.
Refactor 7 depends on Refactor 4 (BacktestService) being done first, since they share the API integration point.

---

*Next: [SPEC Part 4: Tech Debt Inventory →](SPEC_CLEANUP_4_TECH_DEBT.md)*
