# Strategy Configuration

> How strategy parameters are loaded, overridden, and validated.

---

## 3-Level Override Hierarchy

```
Level 1: Hardcoded defaults (RsiNoRetestConfig dataclass defaults)
    ↓ overridden by
Level 2: DEFAULT_CONFIG dict (in strategy file)
    ↓ overridden by
Level 3: config.yaml strategy_params (or Backtest UI sidebar)
```

Higher levels override lower levels. The merge produces the final config passed to the strategy constructor.

---

## Level 1: Dataclass Defaults

```python
# app/trading/strategy/rsi_no_retest.py
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

## Level 3: config.yaml Overrides

```yaml
strategy_params:
  nr_tp_count: 2
  nr_tp1_rr: 1.5
  tp1_close_pct: 0.5
```

These override DEFAULT_CONFIG for live bot and CLI backtest runs.

## Level 3b: Backtest UI Sidebar

The UI sidebar lets users override parameters per-run. These overrides are persisted in the `run_configs` table and do not affect `config.yaml`.

---

## How the Merge Works

In `AppConfig.from_yaml()`:
1. Load `config.yaml` → extract `strategy_params` dict
2. Strategy constructor receives merged config
3. Strategy creates `RsiNoRetestConfig(**merged_params)` — unknown keys are silently ignored by the frozen dataclass

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
