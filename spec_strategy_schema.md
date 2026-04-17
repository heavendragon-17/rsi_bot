# RSI Bot — Strategy Param Schema Spec

## Overview

Each strategy has a frozen dataclass config (`RsiNoRetestConfig`, `RsiMomentumConfig`, `RsiWmaRetestConfig`) with typed fields and defaults. The UI needs more than just types — it needs min/max bounds, step sizes, groupings, and descriptions to render dynamic parameter forms.

**Design decisions:**
- `param_schema()` classmethod inherited via `SchemaConfigMixin` (DRY — written once)
- Metadata lives in a shared file (`param_metadata.py`), imported by each config
- Schema auto-generated from dataclass introspection + metadata merge
- Config class discoverable via `StrategyClass.CONFIG_CLASS` (no separate registry)

---

## Current Config Dataclasses

Three strategies, each with a frozen config dataclass:

| Strategy | Config Class | File | Status |
|----------|-------------|------|--------|
| `rsi_no_retest` | `RsiNoRetestConfig` | `app/trading/strategy/rsi_no_retest.py` | Exists |
| `rsi_momentum` | `RsiMomentumConfig` | `app/trading/strategy/rsi_momentum.py` | Exists |
| `rsi_wma_retest` | `RsiWmaRetestConfig` | `app/trading/strategy/rsi_wma_retest.py` | **To be created** (pre-requisite — currently dict-based) |

---

## Architecture: Three New Files

```
app/trading/strategy/utils/
├── schema_helper.py     ← SchemaConfigMixin + generate_schema_from_dataclass()
├── param_metadata.py    ← NEW — UI metadata for all strategies
├── config_helpers.py    ← (existing — merge_config)
└── ...
```

---

## 1. SchemaConfigMixin + Schema Generator

**File:** `app/trading/strategy/utils/schema_helper.py`

```python
import dataclasses
from typing import Any, get_type_hints

# Python type → JSON Schema type mapping
_TYPE_MAP = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
}


class SchemaConfigMixin:
    """Mixin that adds param_schema() to any frozen dataclass with a METADATA class var.

    Usage:
        @dataclass(frozen=True)
        class MyConfig(SchemaConfigMixin):
            METADATA = MY_METADATA
            UI_GROUPS = MY_GROUPS
            field1: int = 10
    """

    METADATA: dict[str, dict[str, Any]] = {}
    UI_GROUPS: dict[str, dict[str, Any]] = {}

    @classmethod
    def param_schema(cls) -> dict:
        """Returns JSON Schema with UI metadata for dynamic form generation."""
        return generate_schema_from_dataclass(cls, cls.METADATA, cls.UI_GROUPS)


def generate_schema_from_dataclass(
    cls,
    metadata: dict[str, dict[str, Any]] | None = None,
    ui_groups: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Auto-generate JSON Schema from frozen dataclass fields + metadata.

    1. Introspects dataclass fields for name, type, default
    2. Merges UI metadata (title, min/max, group, etc.) from metadata dict
    3. Attaches ui_groups for frontend collapsible sections
    """
    hints = get_type_hints(cls)
    meta = metadata or {}
    properties: dict[str, Any] = {}

    for field in dataclasses.fields(cls):
        # Skip non-serializable or internal fields
        if field.name in ("METADATA", "UI_GROUPS"):
            continue

        field_type = hints.get(field.name, str)
        prop: dict[str, Any] = {
            "title": field.name.replace("_", " ").title(),
            "type": _TYPE_MAP.get(field_type, "string"),
        }

        # Extract default value
        if field.default is not dataclasses.MISSING:
            prop["default"] = field.default
        elif field.default_factory is not dataclasses.MISSING:
            # Serialize factory output — don't store live mutable object
            val = field.default_factory()
            if isinstance(val, (dict, list)):
                import copy
                val = copy.deepcopy(val)
            prop["default"] = val

        # Merge UI metadata overrides (title, min, max, group, etc.)
        if field.name in meta:
            prop.update(meta[field.name])

        properties[field.name] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if ui_groups:
        schema["ui_groups"] = ui_groups

    return schema
```

**Key improvements over original spec:**
- `param_schema()` written **once** in the mixin — no duplication per strategy
- `default_factory` output is deep-copied (fixes the mutable-default bug)
- `METADATA`/`UI_GROUPS` class vars are skipped during field introspection
- `ui_groups` attached to schema for frontend section rendering

---

## 2. Shared Metadata File

**File:** `app/trading/strategy/utils/param_metadata.py`

Each strategy's metadata is a plain dict: `{field_name: {title, min, max, group, ...}}`.
The schema helper merges these on top of the auto-generated base.

```python
"""UI metadata for strategy parameter schemas.

Each dict maps field_name -> {title, minimum, maximum, ui_group, ui_order, ...}.
These are merged into the auto-generated JSON Schema by SchemaConfigMixin.
"""

# ──────────────────────────────────────────────────────────
# Shared UI group definitions (reused across strategies)
# ──────────────────────────────────────────────────────────

INDICATOR_GROUPS = {
    "indicators": {"title": "Indicators", "icon": "sliders", "order": 1},
    "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
    "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 3},
    "exit_tp": {"title": "Take Profit", "icon": "target", "order": 4},
    "management": {"title": "Trade Management", "icon": "settings", "order": 5},
}


# ──────────────────────────────────────────────────────────
# RSI No Retest
# ──────────────────────────────────────────────────────────

RSI_NO_RETEST_GROUPS = {**INDICATOR_GROUPS}

RSI_NO_RETEST_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "description": "RSI calculation lookback period",
        "ui_group": "indicators", "ui_order": 1,
    },
    "rsi_ema_length": {
        "title": "RSI EMA Length",
        "minimum": 2, "maximum": 50,
        "description": "EMA smoothing on RSI line",
        "ui_group": "indicators", "ui_order": 2,
    },
    "rsi_wma_length": {
        "title": "RSI WMA Length",
        "minimum": 5, "maximum": 100,
        "description": "WMA smoothing on RSI (slow signal)",
        "ui_group": "indicators", "ui_order": 3,
    },
    "price_ema_fast": {
        "title": "Price EMA Fast",
        "minimum": 5, "maximum": 50,
        "ui_group": "indicators", "ui_order": 4,
    },
    "price_ema_slow": {
        "title": "Price EMA Slow",
        "minimum": 50, "maximum": 500,
        "ui_group": "indicators", "ui_order": 5,
    },
    # Entry
    "nr_lookback": {
        "title": "Lookback Period",
        "minimum": 5, "maximum": 100,
        "ui_group": "entry", "ui_order": 1,
    },
    "nr_max_above_ema21": {
        "title": "Max Candles Above EMA21",
        "minimum": 0, "maximum": 10,
        "ui_group": "entry", "ui_order": 2,
    },
    "nr_rsi_spread_min": {
        "title": "Min RSI Spread",
        "minimum": 0.0, "maximum": 10.0, "ui_step": 0.1,
        "ui_group": "entry", "ui_order": 3,
    },
    # Stop Loss
    "nr_sl_mode": {
        "title": "Stop Loss Mode",
        "enum": ["lowest_close", "rsi_ema9", "lowest_wick"],
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "sl_buffer_pct": {
        "title": "SL Buffer",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "ui_group": "exit_sl", "ui_order": 3,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.01, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 4,
    },
    # Take Profit
    "nr_tp1_rr": {
        "title": "TP1 R:R",
        "minimum": 0.1, "maximum": 10.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "nr_tp2_rr": {
        "title": "TP2 R:R",
        "minimum": 0.1, "maximum": 15.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "nr_tp3_rr": {
        "title": "TP3 R:R",
        "minimum": 0.1, "maximum": 20.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    "nr_tp_count": {
        "title": "Number of TP Levels",
        "minimum": 1, "maximum": 3,
        "ui_group": "exit_tp", "ui_order": 4,
    },
    "tp1_close_pct": {
        "title": "TP1 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 5,
    },
    "tp2_close_pct": {
        "title": "TP2 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 6,
    },
    "tp3_close_pct": {
        "title": "TP3 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 7,
    },
    # Management
    "nr_move_sl_rr": {
        "title": "Move SL at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 1,
    },
    "nr_lock_profit_rr": {
        "title": "Lock Profit at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 2,
    },
    "use_active_trades": {
        "title": "Use Active Trades",
        "description": "Track concurrent open positions",
        "ui_group": "management", "ui_order": 3,
    },
}


# ──────────────────────────────────────────────────────────
# RSI Momentum
# ──────────────────────────────────────────────────────────

RSI_MOMENTUM_GROUPS = {**INDICATOR_GROUPS}

RSI_MOMENTUM_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "ui_group": "indicators", "ui_order": 1,
    },
    "ema_period": {
        "title": "EMA Period",
        "minimum": 2, "maximum": 50,
        "description": "RSI EMA smoothing period",
        "ui_group": "indicators", "ui_order": 2,
    },
    "wma_period": {
        "title": "WMA Period",
        "minimum": 5, "maximum": 100,
        "description": "RSI WMA slow signal period",
        "ui_group": "indicators", "ui_order": 3,
    },
    # Entry
    "spread_threshold": {
        "title": "Spread Threshold",
        "minimum": 0.0, "maximum": 10.0, "ui_step": 0.1,
        "description": "Min WMA45-EMA9 distance for entry",
        "ui_group": "entry", "ui_order": 1,
    },
    "divergence_lookback": {
        "title": "Divergence Lookback",
        "minimum": 5, "maximum": 100,
        "ui_group": "entry", "ui_order": 2,
    },
    "pivot_strength": {
        "title": "Pivot Strength",
        "minimum": 1, "maximum": 20,
        "description": "N-bar pivot for divergence detection",
        "ui_group": "entry", "ui_order": 3,
    },
    "min_candles": {
        "title": "Min Candles (Warmup)",
        "minimum": 20, "maximum": 200,
        "ui_group": "entry", "ui_order": 4, "ui_hidden": True,
    },
    # Stop Loss
    "sl_lookback": {
        "title": "SL Lookback",
        "minimum": 5, "maximum": 100,
        "description": "Highest-high lookback for soft SL",
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    # Take Profit
    "tp1_rr": {
        "title": "TP1 R:R",
        "minimum": 0.1, "maximum": 10.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "tp2_rr": {
        "title": "TP2 R:R",
        "minimum": 0.1, "maximum": 15.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "tp3_rr": {
        "title": "TP3 R:R",
        "minimum": 0.1, "maximum": 20.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    "tp_count": {
        "title": "Number of TP Levels",
        "minimum": 1, "maximum": 3,
        "ui_group": "exit_tp", "ui_order": 4,
    },
    "tp1_close_pct": {
        "title": "TP1 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 5,
    },
    "tp2_close_pct": {
        "title": "TP2 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 6,
    },
    # Management
    "move_sl_rr": {
        "title": "Move SL at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 1,
    },
    "lock_profit_rr": {
        "title": "Lock Profit at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 2,
    },
    "use_active_trades": {
        "title": "Use Active Trades",
        "ui_group": "management", "ui_order": 3,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.01, "ui_suffix": "%",
        "ui_group": "management", "ui_order": 4,
    },
    # Fees — hidden from UI (use server defaults)
    "taker_fee": {"ui_hidden": True},
    "maker_fee": {"ui_hidden": True},
}


# ──────────────────────────────────────────────────────────
# RSI WMA Retest
# ──────────────────────────────────────────────────────────

RSI_WMA_RETEST_GROUPS = {
    "indicators": {"title": "Indicators", "icon": "sliders", "order": 1},
    "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
    "h1_filter": {"title": "H1 Timeframe Filter", "icon": "filter", "order": 3},
    "exit_tp": {"title": "Take Profit (RSI Levels)", "icon": "target", "order": 4},
    "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 5},
    "management": {"title": "Trade Management", "icon": "settings", "order": 6},
}

RSI_WMA_RETEST_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "ui_group": "indicators", "ui_order": 1,
    },
    "rsi_ema_length": {
        "title": "RSI EMA Length",
        "minimum": 2, "maximum": 50,
        "ui_group": "indicators", "ui_order": 2,
    },
    "rsi_wma_length": {
        "title": "RSI WMA Length",
        "minimum": 5, "maximum": 100,
        "ui_group": "indicators", "ui_order": 3,
    },
    "price_ema_fast": {
        "title": "Price EMA Fast",
        "minimum": 5, "maximum": 50,
        "ui_group": "indicators", "ui_order": 4,
    },
    "price_ema_slow": {
        "title": "Price EMA Slow",
        "minimum": 50, "maximum": 500,
        "ui_group": "indicators", "ui_order": 5,
    },
    # Entry
    "wma_retest_distance": {
        "title": "WMA Retest Distance",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1,
        "description": "Max RSI distance for valid WMA45 retest",
        "ui_group": "entry", "ui_order": 1,
    },
    "rsi_floor": {
        "title": "RSI Floor",
        "minimum": 0, "maximum": 100,
        "description": "No close below this RSI level during retest",
        "ui_group": "entry", "ui_order": 2,
    },
    "wma45_min": {
        "title": "WMA45 Min",
        "minimum": 0, "maximum": 100,
        "description": "Class 1 signal minimum WMA45 value",
        "ui_group": "entry", "ui_order": 3,
    },
    "wma45_max": {
        "title": "WMA45 Max",
        "minimum": 0, "maximum": 100,
        "description": "Class 1 signal maximum WMA45 value",
        "ui_group": "entry", "ui_order": 4,
    },
    # H1 Filter
    "check_h1_wma45": {
        "title": "Enable H1 WMA45 Filter",
        "description": "Require H1 WMA45 above threshold",
        "ui_group": "h1_filter", "ui_order": 1,
    },
    "h1_wma45_min": {
        "title": "H1 WMA45 Min",
        "minimum": 0.0, "maximum": 100.0, "ui_step": 1.0,
        "ui_group": "h1_filter", "ui_order": 2,
    },
    # Take Profit (RSI-based)
    "tp1_rsi": {
        "title": "TP1 RSI Level",
        "minimum": 40, "maximum": 100,
        "description": "Close partial at this RSI",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "tp2_rsi": {
        "title": "TP2 RSI Level",
        "minimum": 50, "maximum": 100,
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "tp3_rsi": {
        "title": "TP3 RSI Level",
        "minimum": 60, "maximum": 100,
        "description": "Close all remaining at this RSI",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    # Stop Loss
    "sl_buffer_pct": {
        "title": "SL Buffer",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.001, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.001, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 3,
    },
    # Management
    "use_active_trades": {
        "title": "Use Active Trades",
        "ui_group": "management", "ui_order": 1,
    },
}
```

---

## 3. Config Dataclass Changes

### Pattern: Inherit `SchemaConfigMixin`, set `METADATA` and `UI_GROUPS`

Each config dataclass adds 3 things:
1. Inherit from `SchemaConfigMixin`
2. Set `METADATA = RSI_*_METADATA` (from `param_metadata.py`)
3. Set `UI_GROUPS = RSI_*_GROUPS` (from `param_metadata.py`)

**Example — `RsiNoRetestConfig`:**

```python
# app/trading/strategy/rsi_no_retest.py
from app.trading.strategy.utils.schema_helper import SchemaConfigMixin
from app.trading.strategy.utils.param_metadata import (
    RSI_NO_RETEST_METADATA, RSI_NO_RETEST_GROUPS,
)

@dataclass(frozen=True)
class RsiNoRetestConfig(SchemaConfigMixin):
    METADATA = RSI_NO_RETEST_METADATA
    UI_GROUPS = RSI_NO_RETEST_GROUPS

    rsi_period: int = 21
    rsi_ema_length: int = 9
    rsi_wma_length: int = 45
    # ... rest unchanged
```

**Example — `RsiMomentumConfig`:**

```python
# app/trading/strategy/rsi_momentum.py
from app.trading.strategy.utils.schema_helper import SchemaConfigMixin
from app.trading.strategy.utils.param_metadata import (
    RSI_MOMENTUM_METADATA, RSI_MOMENTUM_GROUPS,
)

@dataclass(frozen=True)
class RsiMomentumConfig(SchemaConfigMixin):
    METADATA = RSI_MOMENTUM_METADATA
    UI_GROUPS = RSI_MOMENTUM_GROUPS

    rsi_period: int = 14
    ema_period: int = 9
    # ... rest unchanged
```

**New — `RsiWmaRetestConfig` (to be created from existing `DEFAULT_CONFIG` dict):**

```python
# app/trading/strategy/rsi_wma_retest.py
from dataclasses import dataclass
from app.trading.strategy.utils.schema_helper import SchemaConfigMixin
from app.trading.strategy.utils.param_metadata import (
    RSI_WMA_RETEST_METADATA, RSI_WMA_RETEST_GROUPS,
)

@dataclass(frozen=True)
class RsiWmaRetestConfig(SchemaConfigMixin):
    METADATA = RSI_WMA_RETEST_METADATA
    UI_GROUPS = RSI_WMA_RETEST_GROUPS

    # Indicator parameters
    rsi_period: int = 14
    rsi_ema_length: int = 9
    rsi_wma_length: int = 45
    price_ema_fast: int = 21
    price_ema_slow: int = 200
    # Entry conditions
    wma_retest_distance: float = 0.3
    rsi_floor: int = 40
    wma45_min: int = 30
    wma45_max: int = 50
    # H1 Filter
    check_h1_wma45: bool = True
    h1_wma45_min: float = 45.0
    # TP levels (RSI values)
    tp1_rsi: int = 60
    tp2_rsi: int = 70
    tp3_rsi: int = 80
    # SL settings
    sl_buffer_pct: float = 0.003
    disaster_sl_multiplier: float = 3.0
    candle_close_slippage_pct: float = 0.001
    # Trade management
    use_active_trades: bool = True
```

---

## 4. Strategy Class → Config Class Link

Each strategy class exposes its config class via `CONFIG_CLASS` attribute. No separate registry needed.

```python
# app/trading/strategy/rsi_no_retest.py
class RsiNoRetestStrategy(BaseStrategy):
    CONFIG_CLASS = RsiNoRetestConfig
    DEFAULT_CONFIG = { ... }  # existing

# app/trading/strategy/rsi_momentum.py
class RsiMomentumStrategy(BaseStrategy):
    CONFIG_CLASS = RsiMomentumConfig
    DEFAULT_CONFIG = { ... }  # existing

# app/trading/strategy/rsi_wma_retest.py
class RsiWmaRetestStrategy(BaseStrategy):
    CONFIG_CLASS = RsiWmaRetestConfig
    DEFAULT_CONFIG = { ... }  # existing
```

**Usage anywhere** (no second map to maintain):

```python
from app.trading.strategy.loader import STRATEGY_MAP

strategy_class = STRATEGY_MAP["rsi_no_retest"]     # RsiNoRetestStrategy
config_class = strategy_class.CONFIG_CLASS           # RsiNoRetestConfig
schema = config_class.param_schema()                 # JSON Schema dict
```

---

## 5. API Integration

### `GET /api/strategies` route — add `param_schema`:

```python
# app/api/routes/strategies.py
from app.trading.strategy.loader import STRATEGY_MAP

@router.get("/api/strategies")
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    results = []
    for s in strategies:
        strategy_cls = STRATEGY_MAP.get(s.name)
        config_cls = getattr(strategy_cls, "CONFIG_CLASS", None) if strategy_cls else None
        schema = config_cls.param_schema() if config_cls else {}
        results.append(StrategyInfo(
            id=s.id,
            name=s.name,
            description=s.description or "",
            default_config=s.default_config or {},
            param_schema=schema,
        ))
    return results
```

### Pydantic response schema update:

```python
# app/api/schemas.py
class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict
    param_schema: dict = {}  # JSON Schema with UI metadata
```

---

## 6. JSON Schema Extensions (UI Metadata)

Standard JSON Schema fields:
- `type`: `"integer"`, `"number"`, `"boolean"`, `"string"`
- `title`: Human-readable label
- `default`: Default value from dataclass
- `minimum` / `maximum`: Bounds for sliders/validation
- `description`: Tooltip text
- `enum`: For string fields with fixed options (e.g., `nr_sl_mode`)

Custom UI extensions (prefixed `ui_`):
- `ui_group`: Which collapsible section this param belongs to
- `ui_order`: Sort order within its group
- `ui_step`: Step size for sliders/number inputs (default: 1 for int, 0.1 for float)
- `ui_suffix`: Display suffix (`"%"`, `"R"`, `"x"`)
- `ui_hidden`: Boolean — hide from form (for internal params like fees)

---

## 7. Frontend Consumption

### Fetch schema on mount + strategy change:

```typescript
// backtestStore.ts — loadStrategies()
loadStrategies: async () => {
  const strategies = await fetchStrategies();
  set({ availableStrategies: strategies });

  // Auto-set params from default_config of selected strategy
  const current = strategies.find(s => s.name === get().strategy);
  if (current?.default_config) {
    set({ params: { ...current.default_config } });
  }
}
```

### Render dynamic form from `param_schema`:

```typescript
// New component: DynamicParamForm.tsx
const DynamicParamForm = ({ schema, values, onChange }) => {
  const groups = schema.ui_groups || {};
  const sortedGroups = Object.entries(groups)
    .sort(([,a], [,b]) => a.order - b.order);

  return sortedGroups.map(([groupKey, groupMeta]) => {
    const groupParams = Object.entries(schema.properties)
      .filter(([, prop]) => prop.ui_group === groupKey)
      .sort(([, a], [, b]) => (a.ui_order || 0) - (b.ui_order || 0));

    return (
      <CollapsibleSection title={groupMeta.title} key={groupKey}>
        {groupParams.map(([paramName, prop]) => (
          <DynamicInput
            key={paramName}
            name={paramName}
            schema={prop}
            value={values[paramName]}
            onChange={(v) => onChange(paramName, v)}
          />
        ))}
      </CollapsibleSection>
    );
  });
};
```

### Client-side validation from schema:

```typescript
const validateFromSchema = (paramName: string, value: any, schema: any): string | null => {
  const prop = schema.properties?.[paramName];
  if (!prop) return null;

  if (prop.type === "integer" || prop.type === "number") {
    const num = Number(value);
    if (isNaN(num)) return `${prop.title} must be a number`;
    if (prop.minimum !== undefined && num < prop.minimum) return `Min: ${prop.minimum}`;
    if (prop.maximum !== undefined && num > prop.maximum) return `Max: ${prop.maximum}`;
  }

  if (prop.enum && !prop.enum.includes(value)) {
    return `Must be one of: ${prop.enum.join(", ")}`;
  }

  return null;
};
```

---

## 8. TypeScript Type Update

Add to `types/generated.ts`:

```typescript
export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  default_config: Record<string, unknown>;
  param_schema: JSONSchema;  // NEW
}

export interface JSONSchema {
  type: "object";
  properties: Record<string, ParamSchemaProp>;
  ui_groups?: Record<string, {title: string; icon?: string; order: number}>;
  required?: string[];
}

export interface ParamSchemaProp {
  type: "integer" | "number" | "boolean" | "string";
  title: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  description?: string;
  ui_group?: string;
  ui_order?: number;
  ui_step?: number;
  ui_suffix?: string;
  ui_hidden?: boolean;
}
```

---

## Files Changed

| File | Change |
|------|--------|
| `app/trading/strategy/utils/schema_helper.py` | **NEW** — `SchemaConfigMixin` + `generate_schema_from_dataclass()` |
| `app/trading/strategy/utils/param_metadata.py` | **NEW** — UI metadata dicts + group defs for all 3 strategies |
| `app/trading/strategy/rsi_no_retest.py` | Add `SchemaConfigMixin` to config, add `CONFIG_CLASS` to strategy |
| `app/trading/strategy/rsi_momentum.py` | Add `SchemaConfigMixin` to config, add `CONFIG_CLASS` to strategy |
| `app/trading/strategy/rsi_wma_retest.py` | **Create** `RsiWmaRetestConfig` dataclass, add `CONFIG_CLASS` to strategy |
| `app/api/routes/strategies.py` | Return `param_schema` via `CONFIG_CLASS.param_schema()` |
| `app/api/schemas.py` | Add `param_schema: dict` to `StrategyInfo` |
