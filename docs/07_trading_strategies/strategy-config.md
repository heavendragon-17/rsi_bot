# Strategy Configuration

> How strategy parameters are loaded, overridden, and validated.

---

## 2-Level Override Hierarchy

```
Level 1: Frozen config dataclass defaults (e.g., RsiNoRetestConfig)
    ↓ overridden by
Level 2: DEFAULT_CONFIG dict (in strategy file) or Backtest UI sidebar
```

Strategy parameters are defined in frozen config dataclasses within each strategy file. They are **not** stored in `config.yaml`. The `strategy_params` key has been removed from `config.yaml`. Higher levels override lower levels. The merge produces the final config passed to the strategy constructor.

---

## Level 1: Dataclass Defaults

```python
# app/trading/strategy/rsi_no_retest/strategy.py
@dataclass(frozen=True)
class RsiNoRetestConfig:
    rsi_period: int = 21
    rsi_ema_length: int = 9
    nr_tp1_rr: float = 1.0
    # ... all fields with defaults
```

These are the ultimate fallback values.

## Level 2: DEFAULT_CONFIG

```python
DEFAULT_CONFIG = {
    "rsi_period": 21,
    "nr_lookback": 30,
    # ... strategy's preferred defaults
}
```

This dict is what the backtest UI shows as default values. It may differ from dataclass defaults for specific deployment scenarios.

## Backtest UI Sidebar

The UI sidebar lets users override parameters per-run. These overrides are persisted in the `run_configs` table and are merged on top of `DEFAULT_CONFIG`.

---

## How the Merge Works

In live bot:
1. Strategy is instantiated with its frozen config dataclass defaults
2. No external parameter overrides from `config.yaml` (strategy params are self-contained)

In backtest API:
1. `POST /api/backtest/run` body includes `params` dict
2. API merges: `strategy.DEFAULT_CONFIG | request.params`
3. Passed to `BacktestEngine` constructor

---

## Adding New Config Parameters

When adding a new parameter to a strategy:

1. Add field to the config dataclass with a sensible default
2. Add to `DEFAULT_CONFIG` dict
3. Use the parameter in `analyze()` via `self.config.new_param`
4. Update `docs/07_trading_strategies/strategy-reference.md`
5. No migration needed — existing configs simply use the default value
