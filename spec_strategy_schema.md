# RSI Bot — Strategy Param Schema Spec

## Overview

Each strategy has a frozen dataclass config (`RsiNoRetestConfig`, `RsiMomentumConfig`, etc.) with typed fields and defaults. The UI needs more than just types — it needs min/max bounds, step sizes, groupings, and descriptions to render dynamic parameter forms.

**Decision:** Each strategy config dataclass exposes a `@classmethod param_schema()` that returns JSON Schema with UI extensions.

---

## Current Dataclass Example

```python
# app/trading/strategy/rsi_no_retest.py
@dataclass(frozen=True)
class RsiNoRetestConfig:
    rsi_period: int = 21
    rsi_ema_length: int = 9
    rsi_wma_length: int = 45
    price_ema_fast: int = 21
    price_ema_slow: int = 200
    nr_lookback: int = 30
    nr_max_above_ema21: int = 1
    nr_rsi_spread_min: float = 1.5
    nr_sl_mode: str = "lowest_close"
    sl_buffer_pct: float = 0.0
    disaster_sl_multiplier: float = 3.0
    nr_tp1_rr: float = 1.5
    nr_tp2_rr: float = 3.0
    nr_tp3_rr: float = 5.0
    nr_tp_count: int = 2
    tp1_close_pct: float = 0.5
    tp2_close_pct: float = 0.5
    tp3_close_pct: float = 1.0
    nr_move_sl_rr: float = 0.5
    nr_lock_profit_rr: float = 0.2
    use_active_trades: bool = True
```

---

## Target: `param_schema()` Classmethod

Add to each config dataclass:

```python
@dataclass(frozen=True)
class RsiNoRetestConfig:
    # ... fields ...

    @classmethod
    def param_schema(cls) -> dict:
        """Returns JSON Schema with UI metadata for dynamic form generation."""
        return {
            "type": "object",
            "properties": {
                "rsi_period": {
                    "type": "integer",
                    "title": "RSI Period",
                    "default": 21,
                    "minimum": 2,
                    "maximum": 100,
                    "description": "RSI calculation lookback period",
                    "ui_group": "indicators",
                    "ui_order": 1
                },
                "rsi_ema_length": {
                    "type": "integer",
                    "title": "RSI EMA Length",
                    "default": 9,
                    "minimum": 2,
                    "maximum": 50,
                    "description": "EMA smoothing applied to RSI",
                    "ui_group": "indicators",
                    "ui_order": 2
                },
                # ... etc
            },
            "ui_groups": {
                "indicators": {"title": "Oscillators", "icon": "sliders", "order": 1},
                "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
                "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 3},
                "exit_tp": {"title": "Take Profit", "icon": "target", "order": 4},
                "management": {"title": "SL Management", "icon": "shield", "order": 5}
            }
        }
```

---

## JSON Schema Extensions (UI Metadata)

Standard JSON Schema fields used:
- `type`: `"integer"`, `"number"`, `"boolean"`, `"string"`
- `title`: Human-readable label
- `default`: Default value from dataclass
- `minimum` / `maximum`: Bounds for sliders/validation
- `description`: Tooltip text
- `enum`: For string fields with fixed options (e.g., `sl_mode`)

Custom UI extensions (prefixed `ui_`):
- `ui_group`: Which collapsible section this param belongs to
- `ui_order`: Sort order within its group
- `ui_step`: Step size for sliders/number inputs (default: 1 for int, 0.1 for float)
- `ui_suffix`: Display suffix (`"%"`, `"R"`, `"x"`)
- `ui_hidden`: Boolean — hide from form (for internal params)

---

## Helper: Auto-Generate Base Schema from Dataclass

To avoid manually writing schema for every field, create a helper that introspects the dataclass and generates a base schema, which can then be enriched:

```python
# app/trading/strategy/utils/schema_helper.py
import dataclasses
from typing import get_type_hints

# Metadata registry — strategies override this
PARAM_METADATA: dict[str, dict[str, dict]] = {}

def generate_schema_from_dataclass(cls) -> dict:
    """Auto-generate JSON Schema from frozen dataclass fields."""
    hints = get_type_hints(cls)
    properties = {}
    meta = PARAM_METADATA.get(cls.__name__, {})

    for field in dataclasses.fields(cls):
        field_type = hints[field.name]
        prop: dict = {"title": field.name.replace("_", " ").title()}

        # Map Python types to JSON Schema types
        if field_type == int:
            prop["type"] = "integer"
        elif field_type == float:
            prop["type"] = "number"
        elif field_type == bool:
            prop["type"] = "boolean"
        elif field_type == str:
            prop["type"] = "string"
        else:
            prop["type"] = "string"  # fallback

        # Set default
        if field.default is not dataclasses.MISSING:
            prop["default"] = field.default
        elif field.default_factory is not dataclasses.MISSING:
            prop["default"] = field.default_factory()

        # Merge manual metadata overrides
        if field.name in meta:
            prop.update(meta[field.name])

        properties[field.name] = prop

    return {"type": "object", "properties": properties}
```

---

## Metadata Registry Example

```python
# app/trading/strategy/rsi_no_retest.py

from .utils.schema_helper import PARAM_METADATA

PARAM_METADATA["RsiNoRetestConfig"] = {
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "description": "RSI calculation lookback period",
        "ui_group": "indicators", "ui_order": 1
    },
    "rsi_ema_length": {
        "title": "RSI EMA Length",
        "minimum": 2, "maximum": 50,
        "description": "EMA smoothing on RSI line",
        "ui_group": "indicators", "ui_order": 2
    },
    "rsi_wma_length": {
        "title": "RSI WMA Length",
        "minimum": 5, "maximum": 100,
        "description": "WMA smoothing on RSI (slow signal)",
        "ui_group": "indicators", "ui_order": 3
    },
    "price_ema_fast": {
        "title": "Price EMA Fast",
        "minimum": 5, "maximum": 50,
        "ui_group": "indicators", "ui_order": 4
    },
    "price_ema_slow": {
        "title": "Price EMA Slow",
        "minimum": 50, "maximum": 500,
        "ui_group": "indicators", "ui_order": 5
    },
    "nr_lookback": {
        "title": "Lookback Period",
        "minimum": 5, "maximum": 100,
        "ui_group": "entry", "ui_order": 1
    },
    "nr_max_above_ema21": {
        "title": "Max Candles Above EMA21",
        "minimum": 0, "maximum": 10,
        "ui_group": "entry", "ui_order": 2
    },
    "nr_rsi_spread_min": {
        "title": "Min RSI Spread",
        "minimum": 0.0, "maximum": 10.0, "ui_step": 0.1,
        "ui_group": "entry", "ui_order": 3
    },
    "nr_sl_mode": {
        "title": "Stop Loss Mode",
        "enum": ["lowest_close", "rsi_ema9", "lowest_wick"],
        "ui_group": "exit_sl", "ui_order": 1
    },
    "sl_buffer_pct": {
        "title": "SL Buffer",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1,
        "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 2
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5,
        "ui_suffix": "x",
        "ui_group": "exit_sl", "ui_order": 3
    },
    "nr_tp1_rr": {
        "title": "TP1 R:R",
        "minimum": 0.1, "maximum": 10.0, "ui_step": 0.1,
        "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 1
    },
    "nr_tp2_rr": {
        "title": "TP2 R:R",
        "minimum": 0.1, "maximum": 15.0, "ui_step": 0.1,
        "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 2
    },
    "nr_tp3_rr": {
        "title": "TP3 R:R",
        "minimum": 0.1, "maximum": 20.0, "ui_step": 0.1,
        "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 3
    },
    "nr_tp_count": {
        "title": "Number of TP Levels",
        "minimum": 1, "maximum": 3,
        "ui_group": "exit_tp", "ui_order": 4
    },
    "tp1_close_pct": {
        "title": "TP1 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05,
        "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 5
    },
    "tp2_close_pct": {
        "title": "TP2 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05,
        "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 6
    },
    "tp3_close_pct": {
        "title": "TP3 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05,
        "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 7
    },
    "nr_move_sl_rr": {
        "title": "Move SL at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1,
        "ui_suffix": "R",
        "ui_group": "management", "ui_order": 1
    },
    "nr_lock_profit_rr": {
        "title": "Lock Profit at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1,
        "ui_suffix": "R",
        "ui_group": "management", "ui_order": 2
    },
    "use_active_trades": {
        "title": "Use Active Trades",
        "description": "Track concurrent open positions",
        "ui_group": "management", "ui_order": 3
    },
}
```

---

## API Integration

### In `/api/strategies` route:

```python
@router.get("/api/strategies")
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    result = []
    for s in strategies:
        config_cls = STRATEGY_CONFIG_MAP.get(s.name)
        schema = config_cls.param_schema() if config_cls else {}
        result.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "default_config": s.default_config or {},
            "param_schema": schema
        })
    return result
```

### Strategy Config Map:

```python
# app/trading/strategy/__init__.py or registry.py
STRATEGY_CONFIG_MAP = {
    "rsi_no_retest": RsiNoRetestConfig,
    "rsi_momentum": RsiMomentumConfig,
    # future strategies auto-registered
}
```

---

## Frontend Consumption

### 1. Fetch schema on mount + strategy change:

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

### 2. Render dynamic form from `param_schema`:

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

### 3. Client-side validation from schema:

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

## TypeScript Type Update

Add to `types/generated.ts`:

```typescript
export interface StrategyInfo {
  id: number;
  name: string;
  description: string | null;
  default_config: Record<string, unknown>;
  param_schema: JSONSchema;  // ← NEW
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
