# IMPROVE.md — Architecture & Standards Improvement Spec

> Full implementation spec for upgrading the RSI bot's architecture, coding standards,
> and common workflows. Covers the Python trading bot core, FastAPI backend, and React UI.
>
> **Migration strategy**: Incremental PRs in dependency order (PR1 → PR8).

---

## Table of Contents

1. [PR1: Custom Exception Hierarchy](#pr1-custom-exception-hierarchy)
2. [PR2: Dead Code Removal](#pr2-dead-code-removal)
3. [PR3: Typed Config with Dataclasses](#pr3-typed-config-with-dataclasses)
4. [PR4: Structured Logging (structlog)](#pr4-structured-logging-structlog)
5. [PR5: Thread-Safe Exchange Wrapper + Shared Utils](#pr5-thread-safe-exchange-wrapper--shared-utils)
6. [PR6: Stateless Strategy + Typed Actions + PositionSnapshot](#pr6-stateless-strategy--typed-actions--positionsnapshot)
7. [PR7: Unified Engine with Event Source Pattern](#pr7-unified-engine-with-event-source-pattern)
8. [PR8: Test Suite Overhaul](#pr8-test-suite-overhaul)
9. [Cross-Cutting: Optional Services (Null Object + Flags)](#cross-cutting-optional-services)
10. [Cross-Cutting: Notification Thread](#cross-cutting-notification-thread)
11. [Cross-Cutting: Paper Mode Naming](#cross-cutting-paper-mode-naming)
12. [Cross-Cutting: Single IExchange Interface](#cross-cutting-single-iexchange-interface)
13. [Cross-Cutting: Position Reconciliation via WebSocket](#cross-cutting-position-reconciliation)
14. [UI & API Improvements](#ui--api-improvements)

---

## PR1: Custom Exception Hierarchy

**Problem**: `PortfolioManager` imports `ccxt` directly to catch exchange exceptions. This is a layer violation — `MockExchange` and `PaperExchange` don't raise `ccxt` errors, so their failures slip through uncaught.

**Decision**: Custom exception hierarchy in `app/core/exceptions.py`.

### File: `app/core/exceptions.py` (NEW)

```python
"""
Application-level exceptions.
Each exchange adapter catches its own library errors and re-raises as these.
"""

class ExchangeError(Exception):
    """Base exception for all exchange operations."""
    def __init__(self, message: str, original: Exception = None):
        super().__init__(message)
        self.original = original


class InsufficientFundsError(ExchangeError):
    """Not enough balance/margin to execute the order."""
    pass


class OrderRejectedError(ExchangeError):
    """Exchange rejected the order (invalid params, symbol not found, etc.)."""
    pass


class OrderNotFoundError(ExchangeError):
    """Order ID does not exist on the exchange."""
    pass


class ConnectionError(ExchangeError):
    """Network/connection failure to exchange."""
    pass


class RateLimitError(ExchangeError):
    """Exchange rate limit exceeded."""
    pass


class PositionError(ExchangeError):
    """Error related to position operations (leverage, margin mode, etc.)."""
    pass
```

### Changes to `app/services/execution/cex/binance_adapter.py`

Every method that currently lets `ccxt` exceptions propagate must catch and re-raise:

```python
from app.core.exceptions import (
    ExchangeError, InsufficientFundsError, OrderRejectedError,
    ConnectionError, RateLimitError
)
import ccxt

# In create_order():
try:
    result = self.exchange.create_order(...)
except ccxt.InsufficientFunds as e:
    raise InsufficientFundsError(str(e), original=e)
except ccxt.InvalidOrder as e:
    raise OrderRejectedError(str(e), original=e)
except ccxt.RateLimitExceeded as e:
    raise RateLimitError(str(e), original=e)
except ccxt.NetworkError as e:
    raise ConnectionError(str(e), original=e)
except ccxt.BaseError as e:
    raise ExchangeError(str(e), original=e)
```

Apply same pattern to: `cancel_order()`, `fetch_order()`, `fetch_positions()`, `fetch_balance()`, `fetch_open_orders()`, `cancel_all_orders()`, `set_leverage()`.

### Changes to `app/backtest/mock_exchange.py`

Add raises where appropriate:

```python
from app.core.exceptions import InsufficientFundsError, OrderNotFoundError

# In create_order(), where balance check fails:
raise InsufficientFundsError(f"Insufficient balance: need {required}, have {available}")

# In cancel_order(), where order not found:
raise OrderNotFoundError(f"Order {order_id} not found")
```

### Changes to `app/paper/exchange.py`

Same pattern as MockExchange — raise app exceptions instead of silently returning None/False.

### Changes to `app/core/portfolio.py`

**Remove `import ccxt`**. Replace all `ccxt.*` exception catches:

```python
# Before:
import ccxt
try:
    ...
except ccxt.InsufficientFunds:
    ...
except ccxt.BaseError:
    ...

# After:
from app.core.exceptions import ExchangeError, InsufficientFundsError
try:
    ...
except InsufficientFundsError:
    ...
except ExchangeError:
    ...
```

### Changes to DEX adapters

`hyperliquid_adapter.py` and `lighter_adapter.py` — wrap their native exceptions too. Each adapter is responsible for catching its own lib errors and re-raising as app exceptions.

### PR1 Checklist

- [ ] `app/core/exceptions.py` exists with 6 exception classes
- [ ] `grep -r "import ccxt" app/core/` returns 0 results (no ccxt in core layer)
- [ ] `BinanceAdapter` catches ccxt errors and re-raises as app exceptions
- [ ] `MockExchange` raises `InsufficientFundsError` / `OrderNotFoundError`
- [ ] `PaperExchange` raises app exceptions
- [ ] `PortfolioManager` catches only `app.core.exceptions` types
- [ ] `python -m pytest tests/ -v` — all previously passing tests still pass

---

## PR2: Dead Code Removal

**Decision**: Delete all confirmed dead code now. Git history preserves it.

### Files to DELETE entirely

| File | Reason |
|------|--------|
| `app/core/engine.py` | 14-line stub with only `print("Engine started")` |
| `app/core/risk_types.py` | `RiskParams` and `ExitTrigger` defined but never imported anywhere |

### Dead code to REMOVE from existing files

| File | What to remove | Why |
|------|---------------|-----|
| `app/strategies/rsi_no_retest.py` | `_compute_tp_1to1()` method | References `self.tp_rr` which doesn't exist; method is never called |
| `app/strategies/rsi_no_retest.py` | `ctx` alias guard block | `BaseStrategy.__init__` already sets `self.context`; `ctx` alias doesn't exist |
| `app/strategies/rsi_wma_retest.py` | `ctx` alias guard block | Same as above |
| `app/core/interfaces.py` | Mutable default `params: Dict = {}` | Change to `params: Optional[Dict] = None` in `fetch_balance()` |

```python
# In both strategies, remove this block:
if hasattr(self, "ctx") and not hasattr(self, "context"):
    self.context = self.ctx
if not hasattr(self, "context"):
    self.context = StrategyContext()
```

### Debug scripts to MOVE out of `tests/`

Move these to `scripts/debug/` (or delete if no longer useful):

| File | Action |
|------|--------|
| `tests/debug_test.py` | Move to `scripts/debug/` |
| `tests/quick_test.py` | Move to `scripts/debug/` |
| `tests/quick_test_lock_profit.py` | Move to `scripts/debug/` |
| `tests/repro_ghost_tp.py` | Move to `scripts/debug/` |
| `tests/repro_pnl.py` | Move to `scripts/debug/` |
| `tests/debug_tp_stress.py` | Move to `scripts/debug/` |

### PR2 Checklist

- [ ] `app/core/engine.py` deleted
- [ ] `app/core/risk_types.py` deleted
- [ ] `grep -r "_compute_tp_1to1" app/` returns 0 results
- [ ] `grep -r "hasattr.*ctx" app/strategies/` returns 0 results
- [ ] `ls tests/debug_test.py` → file not found (moved to scripts/)
- [ ] `python -m pytest tests/ -v` — all previously passing tests still pass (no debug scripts collected)

---

## PR3: Typed Config with Dataclasses

**Problem**: Config is a raw `dict` passed everywhere. Defaults are scattered across 5+ classes. `validate_config()` is never called from `main.py` and rejects valid modes/exchanges.

**Decision**: Dataclasses for both config types (no new dependency). Two distinct config concerns:
1. **AppConfig** — global bot settings (mode, exchange, risk, symbols, services)
2. **StrategyConfig** — per-strategy, owned by the strategy class

### File: `app/core/config.py` (NEW)

```python
"""
Typed configuration with dataclasses.
Single source of truth for defaults and validation.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Any
import yaml


@dataclass(frozen=True)
class ExchangeConfig:
    """Exchange connection settings."""
    name: str = "binanceusdm"
    mode: str = "mock"  # mock | sim | paper | testnet | live
    leverage: int = 10
    margin_type: str = "ISOLATED"

    def __post_init__(self):
        valid_modes = {"mock", "sim", "paper", "testnet", "live"}
        if self.mode not in valid_modes:
            raise ValueError(f"Invalid mode '{self.mode}'. Must be one of {valid_modes}")
        valid_exchanges = {"binanceusdm", "binance", "hyperliquid", "lighter"}
        if self.name not in valid_exchanges:
            raise ValueError(f"Invalid exchange '{self.name}'. Must be one of {valid_exchanges}")


@dataclass(frozen=True)
class RiskConfig:
    """Risk management parameters."""
    risk_per_trade_pct: Decimal = Decimal("0.02")
    max_position_pct: Decimal = Decimal("0.5")
    max_leverage: int = 20
    use_initial_capital_for_risk: bool = False

    def __post_init__(self):
        if not (Decimal("0") < self.risk_per_trade_pct <= Decimal("0.1")):
            raise ValueError(f"risk_per_trade_pct must be 0-10%, got {self.risk_per_trade_pct}")
        if self.max_leverage < 1 or self.max_leverage > 125:
            raise ValueError(f"max_leverage must be 1-125, got {self.max_leverage}")


@dataclass(frozen=True)
class NotificationConfig:
    """Optional service flags + settings."""
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    db_enabled: bool = False


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest-specific settings."""
    initial_balance: Decimal = Decimal("10000")
    fee_rate: Decimal = Decimal("0.001")


@dataclass(frozen=True)
class AppConfig:
    """
    Top-level application config.
    Loaded once at startup from config.yaml + .env.
    Passed to constructors (not a global singleton).
    """
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy_name: str = "rsi_no_retest"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    timeframe: str = "5m"
    warmup_candles: int = 200

    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "AppConfig":
        """Load config from YAML file. Validates on construction."""
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        return cls(
            exchange=ExchangeConfig(
                name=raw.get("exchange", {}).get("name", "binanceusdm"),
                mode=raw.get("mode", "mock"),
                leverage=raw.get("exchange", {}).get("leverage", 10),
                margin_type=raw.get("exchange", {}).get("margin_type", "ISOLATED"),
            ),
            risk=RiskConfig(
                risk_per_trade_pct=Decimal(str(raw.get("risk", {}).get("risk_per_trade_pct", "0.02"))),
                max_position_pct=Decimal(str(raw.get("risk", {}).get("max_position_pct", "0.5"))),
                max_leverage=raw.get("risk", {}).get("max_leverage", 20),
                use_initial_capital_for_risk=raw.get("risk", {}).get("use_initial_capital_for_risk", False),
            ),
            notification=NotificationConfig(
                telegram_enabled=raw.get("notification", {}).get("telegram_enabled", True),
            ),
            backtest=BacktestConfig(
                initial_balance=Decimal(str(raw.get("backtest", {}).get("initial_balance", "10000"))),
            ),
            symbols=raw.get("symbols", ["BTC/USDT"]),
            strategy_name=raw.get("strategy", "rsi_no_retest"),
            strategy_params=raw.get("strategy_params", {}),
            timeframe=raw.get("timeframe", "5m"),
            warmup_candles=raw.get("warmup_candles", 200),
        )

    def to_legacy_dict(self) -> dict:
        """
        Convert to the raw dict format used by current constructors.
        Allows incremental migration — new code reads AppConfig,
        old code receives the dict until it's updated.
        """
        return {
            "mode": self.exchange.mode,
            "exchange": {
                "name": self.exchange.name,
                "leverage": self.exchange.leverage,
                "margin_type": self.exchange.margin_type,
            },
            "risk": {
                "risk_per_trade_pct": float(self.risk.risk_per_trade_pct),
                "max_position_pct": float(self.risk.max_position_pct),
                "max_leverage": self.risk.max_leverage,
                "use_initial_capital_for_risk": self.risk.use_initial_capital_for_risk,
            },
            "symbols": self.symbols,
            "strategy": self.strategy_name,
            "strategy_params": self.strategy_params,
            "timeframe": self.timeframe,
            "warmup_candles": self.warmup_candles,
            "backtest": {
                "initial_balance": float(self.backtest.initial_balance),
            },
        }
```

### Per-Strategy Config (owned by the strategy class)

Each strategy defines its own config dataclass:

```python
# app/strategies/rsi_no_retest.py

@dataclass(frozen=True)
class RsiNoRetestConfig:
    """Config for RSI No-Retest strategy."""
    rsi_period: int = 14
    ema_period: int = 21
    wma_period: int = 45
    min_rsi_spread: float = 5.0
    entry_rsi_min: float = 40.0
    entry_rsi_max: float = 50.0
    tp_count: int = 3
    tp1_rsi: float = 60.0
    tp2_rsi: float = 70.0
    tp3_rsi: float = 80.0
    soft_sl_buffer: float = 2.0
    hard_sl_multiplier: float = 3.0
    lock_profit_rr: float = 0.2

    @classmethod
    def from_dict(cls, params: dict) -> "RsiNoRetestConfig":
        """Construct from strategy_params dict, ignoring unknown keys."""
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in params.items() if k in valid_keys}
        return cls(**filtered)
```

Strategy `__init__` uses it:

```python
class RsiNoRetestStrategy(BaseStrategy):
    def __init__(self, config: AppConfig):  # or legacy dict
        super().__init__(config)
        if isinstance(config, AppConfig):
            self.cfg = RsiNoRetestConfig.from_dict(config.strategy_params)
        else:
            self.cfg = RsiNoRetestConfig.from_dict(config.get("strategy_params", {}))
```

### Migration script: `scripts/migrate_config.py` (NEW)

```python
"""
One-time migration: convert old config.yaml to new format.
Usage: python scripts/migrate_config.py config.yaml
"""
import sys
import yaml

def migrate(path: str):
    with open(path) as f:
        old = yaml.safe_load(f)

    # ... rearrange keys to new structure ...
    # ... write back with comments explaining new structure ...

if __name__ == "__main__":
    migrate(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
```

### Changes to `main.py`

```python
# Before:
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# After:
from app.core.config import AppConfig
config = AppConfig.from_yaml("config.yaml")
# Constructors that aren't yet updated can use:
legacy_config = config.to_legacy_dict()
```

### Delete: `app/utils/validators.py`

The current `validate_config()` is broken (rejects valid modes/exchanges) and never called. Delete it entirely. Validation is now in `__post_init__` of each dataclass.

### PR3 Checklist

- [ ] `app/core/config.py` exists with `AppConfig`, `ExchangeConfig`, `RiskConfig`, `NotificationConfig`, `BacktestConfig`
- [ ] `AppConfig.from_yaml("config.yaml")` loads without error
- [ ] Invalid config raises `ValueError` with descriptive message at startup
- [ ] `main.py` uses `AppConfig.from_yaml()`
- [ ] Each strategy has its own config dataclass
- [ ] `app/utils/validators.py` deleted (or `validate_config` removed)
- [ ] `scripts/migrate_config.py` exists and converts old format
- [ ] `python -m pytest tests/ -v` — all tests pass

---

## PR4: Structured Logging (structlog)

**Problem**: Logging is inconsistent — `portfolio.py` uses root logger, `stream_manager.py` uses `print()`, strategies use named loggers. Different patterns means messages get lost.

**Decision**: structlog with thread-local context variables.

### New dependency

```
# requirements.txt
structlog>=24.0.0
```

### File: `app/core/logging.py` (NEW — replaces `app/utils/logger.py`)

```python
"""
Structured logging setup.
All modules use: logger = structlog.get_logger()
Bound context: symbol=, trade_id=, thread_name=
"""
import logging
import structlog
import threading


def setup_logging(level: str = "INFO", json_output: bool = False):
    """
    Call once in main.py at startup.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_output: True for production (JSON lines), False for dev (colored console)
    """
    structlog.reset_defaults()

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_thread_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Also add file handler
    file_handler = logging.FileHandler("rsi_bot.log")
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(file_handler)
    root.setLevel(getattr(logging, level.upper()))


def _add_thread_name(logger, method_name, event_dict):
    event_dict["thread"] = threading.current_thread().name
    return event_dict


def bind_trade_context(symbol: str, trade_id: str = None):
    """Bind trade context for structured logging. Call at position open."""
    structlog.contextvars.bind_contextvars(symbol=symbol)
    if trade_id:
        structlog.contextvars.bind_contextvars(trade_id=trade_id)


def clear_trade_context():
    """Clear trade context. Call at position close."""
    structlog.contextvars.unbind_contextvars("symbol", "trade_id")
```

### Usage in every module

```python
# Before (various patterns):
import logging
logger = logging.getLogger(__name__)
logger.info("Position opened for %s", symbol)

# Or:
logging.info("Position opened")

# Or:
print(f"Position opened for {symbol}")

# After (one pattern everywhere):
import structlog
logger = structlog.get_logger()
logger.info("position_opened", symbol=symbol, entry_price=str(price))
```

### Files to update

| File | Current | Change to |
|------|---------|-----------|
| `app/core/portfolio.py` | `logging.info(...)` (root logger) | `structlog.get_logger()` |
| `app/core/runner.py` | `logging.getLogger(__name__)` | `structlog.get_logger()` |
| `app/strategies/rsi_no_retest.py` | `logging.getLogger("rsi_bot")` | `structlog.get_logger()` |
| `app/strategies/rsi_wma_retest.py` | `logging.getLogger("rsi_bot")` | `structlog.get_logger()` |
| `app/services/market_data/stream_manager.py` | `print()` everywhere | `structlog.get_logger()` |
| `app/backtest/engine.py` | `print()` everywhere | `structlog.get_logger()` |
| `app/backtest/reporting.py` | `print()` everywhere | `structlog.get_logger()` |
| `app/paper/exchange.py` | `logging.getLogger(__name__)` | `structlog.get_logger()` |
| `app/services/execution/cex/binance_adapter.py` | `logging.getLogger(...)` | `structlog.get_logger()` |
| `main.py` | `setup_logger("rsi_bot", ...)` | `setup_logging(level="INFO")` |

### Trade lifecycle logging

```python
# In PortfolioManager._handle_buy_signal():
from app.core.logging import bind_trade_context
trade_id = f"{symbol}_{int(time.time())}"
bind_trade_context(symbol=symbol, trade_id=trade_id)
logger.info("position_opened", entry=str(entry_price), sl=str(sl_price))

# In PortfolioManager._cleanup_position():
from app.core.logging import clear_trade_context
logger.info("position_closed", pnl=str(pnl), reason=reason)
clear_trade_context()
```

Output example (dev mode):
```
2026-02-19T10:30:45Z [info] position_opened  symbol=BTC/USDT trade_id=BTCUSDT_1708345845 entry=42150.50 sl=41800.00 thread=symbol-BTCUSDT
2026-02-19T10:31:12Z [info] tp1_hit          symbol=BTC/USDT trade_id=BTCUSDT_1708345845 price=42500.00 thread=symbol-BTCUSDT
```

### Delete: `app/utils/logger.py`

The old `setup_logger()` function is replaced by `app/core/logging.py`.

### PR4 Checklist

- [ ] `structlog` added to `requirements.txt`
- [ ] `app/core/logging.py` exists with `setup_logging()`, `bind_trade_context()`, `clear_trade_context()`
- [ ] `grep -rn "print(" app/backtest/engine.py app/backtest/reporting.py app/services/market_data/stream_manager.py` returns 0 results
- [ ] `grep -rn "import logging" app/core/portfolio.py` returns 0 results (uses structlog)
- [ ] `app/utils/logger.py` deleted
- [ ] `python -m pytest tests/ -v` — all tests pass
- [ ] Running the bot produces structured log output with symbol/trade_id context

---

## PR5: Thread-Safe Exchange Wrapper + Shared Utils

### Problem 1: CCXT is not thread-safe

`BinanceAdapter` shares one CCXT instance across N symbol threads. CCXT instances are not thread-safe for concurrent calls.

**Decision**: Thread-safe wrapper with locks around all CCXT calls.

### Changes to `app/services/execution/cex/binance_adapter.py`

```python
import threading

class BinanceAdapter(IExchange):
    def __init__(self, config):
        self._lock = threading.Lock()
        # ... existing init ...

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        with self._lock:
            # ... existing CCXT call ...
            # ... catch ccxt errors, re-raise as app exceptions (from PR1) ...

    def cancel_order(self, order_id, symbol):
        with self._lock:
            # ...

    def fetch_order(self, order_id, symbol):
        with self._lock:
            # ...

    def fetch_positions(self, symbols=None):
        with self._lock:
            # ...

    def fetch_balance(self, params=None):
        with self._lock:
            # ...

    def fetch_open_orders(self, symbol=None):
        with self._lock:
            # ...

    def cancel_all_orders(self, symbol):
        with self._lock:
            # ...

    def set_leverage(self, leverage, symbol):
        with self._lock:
            # ...

    def fetch_ohlcv(self, symbol, timeframe, limit):
        with self._lock:
            # ...
```

All public methods acquire `self._lock` before calling CCXT. This serializes exchange API calls but is safe with the current thread-per-symbol architecture.

### Problem 2: `to_decimal()` duplicated in 3 files

**Decision**: Shared utils layer at `app/core/utils.py` (already exists). Remove duplicates.

### Changes

| File | Change |
|------|--------|
| `app/backtest/mock_exchange.py` | Remove local `to_decimal()`, add `from app.core.utils import to_decimal` |
| `app/services/execution/cex/binance_adapter.py` | Remove local `to_decimal()`, add `from app.core.utils import to_decimal` |
| `app/core/utils.py` | Keep as canonical location (already exists) |

### Import policy (enforced going forward)

```
app/core/       → imports NOTHING from app/services/, app/backtest/, app/paper/
app/core/utils.py → shared utilities importable by any layer
app/services/   → imports from app/core/ freely
app/backtest/   → imports from app/core/ freely
app/paper/      → imports from app/core/ freely
app/strategies/ → imports from app/core/ freely

NEVER: app/core/ importing from app/services/ (layer violation)
NEVER: circular imports between any modules
```

### PR5 Checklist

- [ ] `BinanceAdapter` has `self._lock = threading.Lock()` in `__init__`
- [ ] All public methods in `BinanceAdapter` acquire `self._lock`
- [ ] `grep -n "def to_decimal" app/` returns exactly 1 result (in `app/core/utils.py`)
- [ ] `MockExchange` and `BinanceAdapter` import `to_decimal` from `app.core.utils`
- [ ] `python -m pytest tests/test_concurrency.py -v` — still passes
- [ ] `python -m pytest tests/ -v` — all tests pass

---

## PR6: Stateless Strategy + Typed Actions + PositionSnapshot

**Problem**: Strategies mutate `self.context` state across calls, making them impossible to test without careful setup sequences. Runner directly reaches into `strategy.context.active_trades[symbol].meta` to sync TP state — coupling 3 layers.

**Decision**:
- Stateless `analyze()` — receives context snapshot, returns typed actions + new state
- Runner passes `PositionSnapshot` from Portfolio
- Typed action objects (not enums)

### File: `app/core/actions.py` (NEW)

```python
"""
Typed action objects returned by Strategy.analyze().
Each action is self-describing and carries all data needed for execution.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List


@dataclass(frozen=True)
class OpenPosition:
    """Open a new position."""
    symbol: str
    side: str  # "BUY" for long
    entry_price: Decimal
    sl_price: Decimal
    soft_sl_price: Optional[Decimal]
    tp_prices: List[Decimal]  # [tp1, tp2, tp3]
    tp_allocations: Optional[dict]  # {"TP1": 0.33, "TP2": 0.5, ...}
    lock_profit_price: Optional[Decimal]
    signal_class: int
    reason: str


@dataclass(frozen=True)
class ClosePosition:
    """Close the current position."""
    symbol: str
    reason: str  # "CANDLE_CLOSE_BELOW_SL", "TP3_HIT", "MANUAL", etc.


@dataclass(frozen=True)
class MoveSL:
    """Move stop loss to a new price."""
    symbol: str
    new_sl_price: Decimal
    reason: str  # "LOCK_PROFIT", "TRAILING", etc.


@dataclass(frozen=True)
class DoNothing:
    """Explicit no-op. Makes the return type non-optional."""
    pass


# Union type for type checking
Action = OpenPosition | ClosePosition | MoveSL | DoNothing
```

### File: `app/core/snapshots.py` (NEW)

```python
"""
Read-only snapshots passed to stateless analyze().
Portfolio provides these; strategy reads them.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict


@dataclass(frozen=True)
class PositionSnapshot:
    """Read-only view of current position state."""
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


@dataclass(frozen=True)
class ContextSnapshot:
    """Read-only view of strategy state machine."""
    state: str  # "SCANNING", "RETESTING", "CONFIRMING"
    entry_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    soft_sl_price: Optional[Decimal] = None
    retesting_since: Optional[int] = None  # candle count
    confirming_since: Optional[int] = None
    meta: Dict = None  # any extra state the strategy needs

    def __post_init__(self):
        if self.meta is None:
            object.__setattr__(self, "meta", {})
```

### File: `app/core/analysis_result.py` (NEW)

```python
"""
Return type from Strategy.analyze().
Contains typed actions and the new context state.
"""
from dataclasses import dataclass
from typing import List
from app.core.actions import Action
from app.core.snapshots import ContextSnapshot


@dataclass(frozen=True)
class AnalysisResult:
    """
    Returned by analyze(). Strategy never mutates state directly.
    Runner reads .actions and applies them. Runner reads .new_context
    and stores it for the next analyze() call.
    """
    actions: List[Action]
    new_context: ContextSnapshot
```

### Updated `IStrategy` interface

```python
# app/core/interfaces.py

class IStrategy(ABC):
    @abstractmethod
    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        """
        Pure analysis function.

        Args:
            symbol: Trading pair
            df: OHLCV DataFrame with indicators
            position: Current position state (None = no position)
            context: Strategy state machine snapshot (None = initial state)

        Returns:
            AnalysisResult with typed actions and new context state.
            Runner applies actions and stores new_context for next call.
        """
        pass
```

### Candle-close SL logic (preserved elegantly)

```python
# In RsiNoRetestStrategy.analyze():

def analyze(self, symbol, df, position=None, context=None):
    context = context or ContextSnapshot(state="SCANNING")
    candle = self._last_candle(df)

    # --- Candle-close SL check ---
    # This checks candle.close, NOT candle.low.
    # A wick below SL does NOT trigger close. Only a CLOSE below SL does.
    if position and position.has_position and context.soft_sl_price:
        if candle.close < context.soft_sl_price:
            return AnalysisResult(
                actions=[ClosePosition(symbol=symbol, reason="CANDLE_CLOSE_BELOW_SL")],
                new_context=ContextSnapshot(state="SCANNING"),
            )

    # --- Lock profit check ---
    if position and position.has_position and not position.lock_profit_triggered:
        if candle.close >= context.meta.get("lock_profit_price", Decimal("inf")):
            return AnalysisResult(
                actions=[MoveSL(
                    symbol=symbol,
                    new_sl_price=position.entry_price,
                    reason="LOCK_PROFIT",
                )],
                new_context=context,  # state unchanged
            )

    # --- Entry signal detection (state machine) ---
    if context.state == "SCANNING":
        # ... detect EMA21 reclaim + RSI momentum spread ...
        if entry_conditions_met:
            return AnalysisResult(
                actions=[OpenPosition(...)],
                new_context=ContextSnapshot(state="SCANNING"),  # reset after entry
            )

    return AnalysisResult(
        actions=[DoNothing()],
        new_context=context,  # state unchanged
    )
```

### Updated Runner loop

```python
# app/core/runner.py — _run_symbol_loop()

# State stored per symbol in Runner:
contexts: Dict[str, ContextSnapshot] = {}

while not self.stop_event.is_set():
    # ... get candle, compute indicators ...

    # Get position snapshot from Portfolio
    position = self.portfolio.get_position_snapshot(symbol)

    # Get or create context
    ctx = contexts.get(symbol, ContextSnapshot(state="SCANNING"))

    # Pure analysis call
    result = self.strategy.analyze(symbol, df, position=position, context=ctx)

    # Store new context
    contexts[symbol] = result.new_context

    # Apply actions
    for action in result.actions:
        match action:
            case OpenPosition():
                signal = self._action_to_signal(action)
                self.portfolio.on_signal(signal)
            case ClosePosition():
                self.portfolio.close_position(action.symbol, Decimal("1.0"))
            case MoveSL():
                self.portfolio.move_stop_loss(action.symbol, action.new_sl_price)
            case DoNothing():
                pass
```

### New method on Portfolio: `get_position_snapshot()`

```python
# app/core/portfolio.py

def get_position_snapshot(self, symbol: str) -> Optional[PositionSnapshot]:
    """Return a read-only snapshot of current position. None if no position."""
    if symbol not in self.positions:
        return None
    pos = self.positions[symbol]
    return PositionSnapshot(
        has_position=True,
        symbol=symbol,
        side=pos.get("side", "BUY"),
        entry_price=Decimal(str(pos["entry_price"])),
        current_sl=Decimal(str(pos.get("sl_price", 0))),
        soft_sl=Decimal(str(pos["soft_sl"])) if pos.get("soft_sl") else None,
        tp1_hit=pos.get("meta", {}).get("tp1_hit", False),
        tp2_hit=pos.get("meta", {}).get("tp2_hit", False),
        tp3_hit=pos.get("meta", {}).get("tp3_hit", False),
        lock_profit_triggered=pos.get("meta", {}).get("lock_profit_triggered", False),
    )
```

### PR6 Checklist

- [ ] `app/core/actions.py` exists with `OpenPosition`, `ClosePosition`, `MoveSL`, `DoNothing`
- [ ] `app/core/snapshots.py` exists with `PositionSnapshot`, `ContextSnapshot`
- [ ] `app/core/analysis_result.py` exists with `AnalysisResult`
- [ ] `IStrategy.analyze()` signature updated to accept `position` and `context`
- [ ] `RsiNoRetestStrategy.analyze()` is stateless — no `self.context` mutation
- [ ] Runner no longer reaches into `strategy.context.active_trades`
- [ ] `grep -n "active_trades" app/core/runner.py` returns 0 results
- [ ] Candle-close SL works: closing below soft_sl triggers close, wick below does not
- [ ] `Portfolio.get_position_snapshot()` exists and returns frozen dataclass
- [ ] `python -m pytest tests/ -v` — all tests pass (updated to new API)

---

## PR7: Unified Engine with Event Source Pattern

**Problem**: `BacktestEngine` and `MultiSymbolRunner` both call `strategy.analyze()` but with completely different surrounding logic. You plan tick-based backtesting, making both live and backtest fundamentally similar.

**Decision**: Unified `IEngine` with `IEventSource` pattern. Both live and backtest emit the same events (Tick, CandleClose). Engine processes them identically.

### File: `app/core/events.py` (UPDATED — add new event types)

```python
# Add to existing events.py:

@dataclass
class TickEvent:
    """Real-time price tick (from WebSocket or historical replay)."""
    symbol: str
    price: Decimal
    timestamp: datetime
    volume: Optional[Decimal] = None


@dataclass
class CandleCloseEvent:
    """A candle has closed. Contains full OHLCV data."""
    candle: Candle  # existing Candle dataclass


@dataclass
class EngineStopEvent:
    """Signals the engine to stop processing."""
    reason: str = "normal"


# Union type
EngineEvent = TickEvent | CandleCloseEvent | EngineStopEvent
```

### File: `app/core/event_source.py` (NEW)

```python
"""
Event source abstraction.
Both live and backtest provide the same event types through this interface.
"""
from abc import ABC, abstractmethod
from typing import Iterator
from app.core.events import EngineEvent


class IEventSource(ABC):
    """Yields events for the engine to process."""

    @abstractmethod
    def events(self) -> Iterator[EngineEvent]:
        """
        Yield events one at a time.
        - LiveEventSource: blocks until next WS message, yields events in real-time
        - BacktestEventSource: iterates historical tick/candle file, yields instantly
        """
        pass

    @abstractmethod
    def stop(self):
        """Signal the event source to stop producing events."""
        pass
```

### File: `app/core/engine.py` (NEW — replaces the deleted stub)

```python
"""
Unified engine that processes events from any source.
Both live trading and backtesting use this same loop.
"""
import structlog
from typing import Optional, Callable, Dict
from decimal import Decimal

from app.core.event_source import IEventSource
from app.core.events import TickEvent, CandleCloseEvent, EngineStopEvent
from app.core.interfaces import IStrategy, IExchange
from app.core.snapshots import ContextSnapshot
from app.core.actions import OpenPosition, ClosePosition, MoveSL, DoNothing

logger = structlog.get_logger()


class Engine:
    """
    Unified trading engine.

    Processes events from an IEventSource. The event source determines
    whether this is live trading (real-time events) or backtesting
    (replayed historical events).
    """

    def __init__(
        self,
        event_source: IEventSource,
        strategy: IStrategy,
        portfolio,  # IPortfolio
        exchange: IExchange,
        symbols: list[str],
        on_progress: Optional[Callable] = None,
    ):
        self.event_source = event_source
        self.strategy = strategy
        self.portfolio = portfolio
        self.exchange = exchange
        self.symbols = symbols
        self.on_progress = on_progress

        # Per-symbol strategy context (stateless strategy, external state)
        self.contexts: Dict[str, ContextSnapshot] = {}
        # Per-symbol DataFrames (built from candles)
        self.dataframes: Dict[str, "pd.DataFrame"] = {}

    def run(self) -> Optional[dict]:
        """
        Main event loop. Processes events until source is exhausted or stopped.

        Returns:
            dict with results (for backtest) or None (for live — runs forever)
        """
        logger.info("engine_started", symbols=self.symbols)

        for event in self.event_source.events():
            match event:
                case TickEvent():
                    self._handle_tick(event)

                case CandleCloseEvent():
                    self._handle_candle_close(event)

                case EngineStopEvent():
                    logger.info("engine_stopped", reason=event.reason)
                    break

        return self._compute_results()

    def _handle_tick(self, tick: TickEvent):
        """Process a price tick — check fills on pending orders."""
        self.portfolio.check_fills(tick.symbol, tick.price)

    def _handle_candle_close(self, event: CandleCloseEvent):
        """Process a closed candle — run strategy analysis."""
        candle = event.candle
        symbol = candle.symbol

        # Update DataFrame
        self._update_dataframe(symbol, candle)
        df = self.dataframes.get(symbol)
        if df is None or len(df) < 50:  # not enough data for indicators
            return

        # Get position snapshot
        position = self.portfolio.get_position_snapshot(symbol)

        # Get or create context
        ctx = self.contexts.get(symbol, ContextSnapshot(state="SCANNING"))

        # Pure strategy analysis
        result = self.strategy.analyze(symbol, df, position=position, context=ctx)

        # Store new context
        self.contexts[symbol] = result.new_context

        # Apply actions
        for action in result.actions:
            self._apply_action(action)

    def _apply_action(self, action):
        """Execute a typed action."""
        match action:
            case OpenPosition():
                signal = self._action_to_signal(action)
                self.portfolio.on_signal(signal)
            case ClosePosition():
                self.portfolio.close_position(action.symbol, Decimal("1.0"))
            case MoveSL():
                self.portfolio.move_stop_loss(action.symbol, action.new_sl_price)
            case DoNothing():
                pass

    def _update_dataframe(self, symbol, candle):
        """Append candle to per-symbol DataFrame."""
        # ... build/append to DataFrame from candle data ...
        pass

    def _action_to_signal(self, action: OpenPosition):
        """Convert OpenPosition action to SignalEvent for Portfolio."""
        from app.core.events import SignalEvent
        return SignalEvent(
            symbol=action.symbol,
            signal_type="BUY",
            price=action.entry_price,
            timestamp=datetime.now(),
            reason=action.reason,
            sl_price=action.sl_price,
            soft_sl_price=action.soft_sl_price,
            tp1_price=action.tp_prices[0] if len(action.tp_prices) > 0 else None,
            tp2_price=action.tp_prices[1] if len(action.tp_prices) > 1 else None,
            tp3_price=action.tp_prices[2] if len(action.tp_prices) > 2 else None,
            tp_allocations=action.tp_allocations,
            lock_profit_price=action.lock_profit_price,
            signal_class=action.signal_class,
        )

    def _compute_results(self) -> Optional[dict]:
        """Compute results after engine stops. Override in subclass for backtest."""
        return None
```

### File: `app/services/market_data/live_event_source.py` (NEW)

```python
"""
LiveEventSource: produces events from Binance WebSocket streams.
"""
from app.core.event_source import IEventSource
from app.core.events import TickEvent, CandleCloseEvent, EngineStopEvent, EngineEvent
import threading
import queue


class LiveEventSource(IEventSource):
    """
    Wraps BinanceStreamManager. Converts WS messages to EngineEvents.
    Blocks on queue.get() — engine loop runs in real-time.
    """

    def __init__(self, stream_manager, symbols: list[str]):
        self.stream_manager = stream_manager
        self.symbols = symbols
        self._event_queue: queue.Queue[EngineEvent] = queue.Queue()
        self._stopped = threading.Event()

    def events(self):
        """Yield events as they arrive from WebSocket."""
        # Register callbacks that push to the queue
        self.stream_manager.on_tick = self._on_tick
        self.stream_manager.on_kline_close = self._on_kline_close
        self.stream_manager.subscribe(self.symbols)

        while not self._stopped.is_set():
            try:
                event = self._event_queue.get(timeout=1.0)
                yield event
                if isinstance(event, EngineStopEvent):
                    break
            except queue.Empty:
                continue

    def stop(self):
        self._stopped.set()
        self._event_queue.put(EngineStopEvent(reason="manual_stop"))

    def _on_tick(self, symbol, price, timestamp):
        self._event_queue.put(TickEvent(symbol=symbol, price=price, timestamp=timestamp))

    def _on_kline_close(self, candle):
        self._event_queue.put(CandleCloseEvent(candle=candle))
```

### File: `app/backtest/backtest_event_source.py` (NEW)

```python
"""
BacktestEventSource: replays historical tick/candle data as events.
"""
from app.core.event_source import IEventSource
from app.core.events import TickEvent, CandleCloseEvent, EngineStopEvent, Candle
from decimal import Decimal
from datetime import datetime
import pandas as pd


class BacktestEventSource(IEventSource):
    """
    Reads historical data (CSV or DataFrame) and yields events.
    For candle-based backtest: yields CandleCloseEvent per row.
    For tick-based backtest: yields TickEvent per tick + CandleCloseEvent at candle boundaries.
    """

    def __init__(self, df: pd.DataFrame, symbol: str, tick_mode: bool = False):
        self.df = df
        self.symbol = symbol
        self.tick_mode = tick_mode
        self._stopped = False

    def events(self):
        total = len(self.df)
        for i, (_, row) in enumerate(self.df.iterrows()):
            if self._stopped:
                yield EngineStopEvent(reason="cancelled")
                return

            candle = Candle(
                symbol=self.symbol,
                timestamp=row["timestamp"] if "timestamp" in row else datetime.now(),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row.get("volume", 0))),
                closed=True,
            )

            if self.tick_mode:
                # Simulate ticks: open → high → low → close (simplified)
                for price in [candle.open, candle.high, candle.low, candle.close]:
                    yield TickEvent(
                        symbol=self.symbol,
                        price=price,
                        timestamp=candle.timestamp,
                    )

            yield CandleCloseEvent(candle=candle)

        yield EngineStopEvent(reason="data_exhausted")

    def stop(self):
        self._stopped = True
```

### PR7 Checklist

- [ ] `app/core/events.py` has `TickEvent`, `CandleCloseEvent`, `EngineStopEvent`
- [ ] `app/core/event_source.py` has `IEventSource` abstract class
- [ ] `app/core/engine.py` has `Engine` class with event loop
- [ ] `app/services/market_data/live_event_source.py` wraps WebSocket stream
- [ ] `app/backtest/backtest_event_source.py` replays historical data
- [ ] `Engine.run()` processes both live and backtest events identically
- [ ] Backtest mode works with candle events (tick mode optional for now)
- [ ] `python -m pytest tests/ -v` — all tests pass

---

## PR8: Test Suite Overhaul

**Decision**: Strict — fix or delete broken tests, add proper isolation, CI must pass 100%.

### Step 1: Add `conftest.py` for state isolation

```python
# tests/conftest.py (NEW)

import pytest


@pytest.fixture(autouse=True)
def reset_indicators_global_state():
    """
    Reset Indicators class state after each test.
    Prevents test pollution from monkeypatching Indicators.last.
    """
    from app.utils.indicators import Indicators
    original_last = Indicators.last  # save original
    yield
    Indicators.last = original_last  # restore after test


@pytest.fixture(autouse=True)
def reset_structlog_context():
    """Clear any bound structlog context between tests."""
    import structlog
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
```

### Step 2: Fix or delete broken tests

| Test File | Status | Action |
|-----------|--------|--------|
| `test_dynamic_tp.py::test_tp_count_2` | Broken: strategy returns None | Fix: provide correct DataFrame that triggers EMA21 reclaim. Remove `Indicators.last` monkeypatch — use proper fixture instead |
| `test_dynamic_tp.py` (all) | Monkeypatches `Indicators.last` as class attribute | Fix: use `monkeypatch` fixture (auto-reverted) instead of direct class mutation |
| `test_soft_sl.py` | Broken: strategy emits `MOVE_SL_LOCK_PROFIT` not `CLOSE_BY_CANDLE_SL` | Fix: update assertions to match current strategy behavior |
| `test_soft_sl_noretest.py` | Same as above | Fix: update assertions |
| `test_binance_adapter.py` | Requires API keys | Mark with `@pytest.mark.skipif(not os.getenv("BINANCE_API_KEY"), reason="No API keys")` |
| `test_partial_tp_sl.py` | Passes alone, fails after `test_dynamic_tp.py` | Fixed by `conftest.py` autouse fixture |

### Step 3: Update all tests to new stateless strategy API

All tests that call `strategy.analyze()` must be updated:

```python
# Before:
signal = strategy.analyze("BTC/USDT", df)

# After:
from app.core.snapshots import ContextSnapshot, PositionSnapshot
result = strategy.analyze("BTC/USDT", df, position=None, context=ContextSnapshot(state="SCANNING"))
assert isinstance(result.actions[0], OpenPosition)
```

### Step 4: Add new test files

| File | What it tests |
|------|---------------|
| `tests/test_exceptions.py` | Custom exception hierarchy — adapters raise correct types |
| `tests/test_config.py` | `AppConfig.from_yaml()` validation, invalid config rejection |
| `tests/test_stateless_strategy.py` | Strategy.analyze() is pure: same inputs → same outputs, no side effects |
| `tests/test_candle_close_sl.py` | Candle-close SL: wick below SL → no close, close below SL → close |
| `tests/test_engine_events.py` | Unified engine processes TickEvent and CandleCloseEvent correctly |
| `tests/test_actions.py` | Typed actions: OpenPosition, ClosePosition, MoveSL construct and match correctly |

### Step 5: Add `pytest.ini` (or `pyproject.toml` section)

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: requires external services (API keys, etc.)
```

### PR8 Checklist

- [ ] `tests/conftest.py` exists with autouse fixtures for state reset
- [ ] `grep -r "Indicators.last = " tests/` returns 0 results (uses monkeypatch fixture)
- [ ] All broken tests either fixed or have skip conditions with clear reasons
- [ ] `tests/debug_test.py` and other debug scripts don't exist in `tests/` (moved in PR2)
- [ ] `python -m pytest tests/ -v` — **100% pass rate**
- [ ] `python -m pytest tests/ -v --tb=short 2>&1 | grep -c "FAILED"` returns 0
- [ ] New test files exist for exceptions, config, stateless strategy, candle-close SL, engine events

---

## Cross-Cutting: Optional Services

**Problem**: `main.py` calls `sys.exit(1)` if Telegram init fails. Telegram should be optional.

**Decision**: Config flags + null object pattern.

### Config flags (already in PR3)

```python
@dataclass(frozen=True)
class NotificationConfig:
    telegram_enabled: bool = True
    # ...
```

### Null notifier

```python
# app/services/notification/null_notifier.py (NEW)

class NullNotifier:
    """No-op notifier. Silently does nothing when notifications are disabled."""
    def send_message(self, *args, **kwargs): pass
    def on_entry(self, *args, **kwargs): pass
    def on_fill(self, *args, **kwargs): pass
    def on_exit(self, *args, **kwargs): pass
    def on_error(self, *args, **kwargs): pass
```

### main.py changes

```python
if config.notification.telegram_enabled:
    try:
        notifier = TelegramNotifier(config)
    except Exception as e:
        logger.warning("telegram_init_failed", error=str(e))
        notifier = NullNotifier()
else:
    notifier = NullNotifier()

# Never sys.exit(1) for optional services
```

---

## Cross-Cutting: Notification Thread

**Problem**: `PaperExchange` spawns unbounded daemon threads for notifications.

**Decision**: Dedicated notification thread with bounded queue.

```python
# app/services/notification/notification_worker.py (NEW)

import threading
import queue
import structlog

logger = structlog.get_logger()


class NotificationWorker:
    """
    Single background thread processing notifications FIFO.
    Bounded queue with drop policy if full.
    """

    def __init__(self, notifier, max_queue_size: int = 100):
        self.notifier = notifier
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._thread = threading.Thread(target=self._run, daemon=True, name="notification-worker")
        self._stopped = threading.Event()

    def start(self):
        self._thread.start()

    def stop(self):
        self._stopped.set()
        self._thread.join(timeout=5.0)

    def enqueue(self, method_name: str, *args, **kwargs):
        """Enqueue a notification. Drops if queue is full."""
        try:
            self._queue.put_nowait((method_name, args, kwargs))
        except queue.Full:
            logger.warning("notification_queue_full", method=method_name)

    def _run(self):
        while not self._stopped.is_set():
            try:
                method_name, args, kwargs = self._queue.get(timeout=1.0)
                method = getattr(self.notifier, method_name, None)
                if method:
                    try:
                        method(*args, **kwargs)
                    except Exception:
                        logger.exception("notification_failed", method=method_name)
            except queue.Empty:
                continue
```

Usage in `PaperExchange`:

```python
# Before:
threading.Thread(target=self.notifier.on_entry, args=(...), daemon=True).start()

# After:
self.notification_worker.enqueue("on_entry", order, pos, self.state)
```

---

## Cross-Cutting: Paper Mode Naming

**Problem**: Two paper modes exist — `PaperExchange` (local sim) and `BinanceAdapter` with `set_sandbox_mode(True)` (Binance testnet). Naming is unclear.

**Decision**: Keep both, clarify naming.

| Config mode | What it does | Class used |
|-------------|-------------|------------|
| `mock` | In-memory simulation, no network | `MockExchange` |
| `sim` | Local simulation with tick data | `PaperExchange` |
| `testnet` | Binance testnet (real exchange sandbox) | `BinanceAdapter` with `sandbox_mode=True` |
| `live` | Real trading | `BinanceAdapter` |

### Changes to `exchange_factory.py`

```python
def create_exchange(config: AppConfig) -> IExchange:
    mode = config.exchange.mode
    match mode:
        case "mock":
            return MockExchange(config)
        case "sim":
            return PaperExchange(config)
        case "testnet":
            adapter = BinanceAdapter(config)
            adapter.exchange.set_sandbox_mode(True)
            return adapter
        case "live":
            return BinanceAdapter(config)
        case _:
            raise ValueError(f"Unknown exchange mode: {mode}")
```

### Config migration

```yaml
# Old:
mode: paper  # ambiguous

# New:
exchange:
  mode: sim      # or "testnet" if you want Binance sandbox
```

---

## Cross-Cutting: Single IExchange Interface

**Problem**: `IExchange` and `IFuturesExchange` are separate. Adapters implement different subsets. `sync_from_exchange()` is a no-op for live because it checks `hasattr(exchange, 'positions')`.

**Decision**: Single `IExchange` with full portfolio query API. All adapters implement everything.

### Updated `app/core/interfaces.py`

```python
class IExchange(ABC):
    """Unified exchange interface. All adapters must implement all methods."""

    @abstractmethod
    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        pass

    @abstractmethod
    def cancel_order(self, order_id, symbol) -> bool:
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol) -> int:
        pass

    @abstractmethod
    def fetch_order(self, order_id, symbol) -> dict:
        pass

    @abstractmethod
    def fetch_open_orders(self, symbol=None) -> list:
        pass

    @abstractmethod
    def fetch_positions(self, symbols=None) -> list:
        pass

    @abstractmethod
    def fetch_balance(self, params=None) -> dict:
        pass

    @abstractmethod
    def fetch_ohlcv(self, symbol, timeframe, limit) -> list:
        pass

    @abstractmethod
    def set_leverage(self, leverage, symbol) -> bool:
        pass

    @abstractmethod
    def fetch_order_status(self, order_id, symbol) -> str:
        """Return order status: 'open', 'closed', 'cancelled', 'expired'."""
        pass
```

**Delete `IFuturesExchange`** — merge into `IExchange`.

All adapters (`BinanceAdapter`, `MockExchange`, `PaperExchange`, `HyperliquidAdapter`, `LighterAdapter`) must implement the full interface. `MockExchange.fetch_positions()` wraps its internal `self.positions` dict. This fixes `sync_from_exchange()`.

---

## Cross-Cutting: Position Reconciliation via WebSocket

**Problem**: `sync_from_exchange()` is a no-op for live/paper. No reconciliation between local state and exchange state.

**Decision**: Event-driven via WebSocket user data stream.

### Implementation (in LiveEventSource or separate UserDataStream)

```python
# app/services/market_data/user_data_stream.py (NEW)

class UserDataStream:
    """
    Subscribes to Binance user data stream.
    Emits events for order fills, position updates, balance changes.
    """

    def __init__(self, exchange: BinanceAdapter):
        self.exchange = exchange

    def start(self):
        """Start listening to user data WebSocket."""
        # Binance: create listenKey, connect to wss://fstream.binance.com/ws/<listenKey>
        # Parse events:
        #   ORDER_TRADE_UPDATE → OrderFillEvent
        #   ACCOUNT_UPDATE → PositionUpdateEvent
        pass

    def stop(self):
        pass
```

The unified engine can subscribe to user data events alongside market data events. When an order fill arrives from WS, Portfolio reconciles immediately instead of polling.

**Note**: This is a larger feature. For the initial improvement pass, ensure `fetch_positions()` exists on all adapters (via single IExchange). Full WS reconciliation can be a follow-up PR.

---

## UI & API Improvements

The existing SPEC.md covers the UI/API architecture thoroughly. The improvements here focus on what SPEC.md doesn't address:

### 1. API error responses — standardize

```python
# app/api/middleware.py (NEW)

from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.exceptions import ExchangeError

async def exchange_error_handler(request: Request, exc: ExchangeError):
    return JSONResponse(
        status_code=502,
        content={"error": str(exc), "type": exc.__class__.__name__}
    )
```

### 2. Frontend — use structlog JSON output for API server

When running `python -m app.api.main`, call `setup_logging(json_output=True)` for machine-readable logs.

### 3. Type generation — add to CI

```bash
# In CI pipeline:
npm run generate-types
npx tsc --noEmit  # must pass with generated types
```

### 4. BacktestEngine integration with unified engine

The backtest engine from SPEC.md should be refactored to use the unified `Engine` + `BacktestEventSource` from PR7:

```python
# app/backtest/engine.py — after PR7

class BacktestEngine(Engine):
    """Extends unified Engine with backtest-specific results computation."""

    def __init__(self, data_path, strategy_class, config, on_progress=None):
        df = pd.read_csv(data_path)
        event_source = BacktestEventSource(df, symbol=config.symbols[0])
        exchange = MockExchange(config)
        strategy = strategy_class(config)
        portfolio = PortfolioManager(exchange, config)

        super().__init__(
            event_source=event_source,
            strategy=strategy,
            portfolio=portfolio,
            exchange=exchange,
            symbols=config.symbols,
            on_progress=on_progress,
        )

    def _compute_results(self) -> dict:
        """Override to compute backtest metrics."""
        # ... compute round trips, metrics, equity curve ...
        return results_dict
```

---

## Implementation Order (PR Dependency Graph)

```
PR1: Custom Exceptions          ─┐
PR2: Dead Code Removal          ─┤
                                  ├→ PR5: Thread Safety + Shared Utils
PR3: Typed Config               ─┤
PR4: Structured Logging         ─┘
                                      │
                                      ▼
                                 PR6: Stateless Strategy + Actions
                                      │
                                      ▼
                                 PR7: Unified Engine + Event Source
                                      │
                                      ▼
                                 PR8: Test Suite Overhaul
```

PRs 1-4 can be done in parallel or any order. PR5 depends on PR1 (exceptions). PR6 depends on PR3 (config) + PR4 (logging). PR7 depends on PR6 (stateless strategy). PR8 should be last — updates all tests to the final API.

---

## Acceptance Criteria

After all 8 PRs are merged:

1. **`python -m pytest tests/ -v`** — 100% pass, 0 warnings about global state
2. **`grep -r "import ccxt" app/core/`** — 0 results (no CCXT in core)
3. **`grep -rn "print(" app/`** — 0 results in non-test files (all structlog)
4. **Invalid `config.yaml`** — startup fails with clear `ValueError`, not a silent KeyError deep in init
5. **Two symbol threads** — no race conditions (exchange calls serialized by lock)
6. **Strategy test** — `strategy.analyze(candle, position, context)` returns `AnalysisResult` with no side effects
7. **Candle-close SL** — wick below SL doesn't trigger close; close below SL does
8. **Telegram down** — bot logs warning, continues with `NullNotifier`
9. **`app/core/`** has zero imports from `app/services/` or `app/backtest/`
10. **All adapters** implement unified `IExchange` including `fetch_positions()` and `fetch_order_status()`
