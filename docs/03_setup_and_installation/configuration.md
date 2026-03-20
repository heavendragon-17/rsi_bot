# Configuration Reference

> Complete schema reference for `config.yaml`, typed config classes in `app/core/config.py`, and environment variables in `.env`. An AI agent should consult this before modifying any configuration-related code.

---

## config.yaml Full Schema

The bot reads `config.yaml` from the project root at startup via `AppConfig.from_yaml("config.yaml")`. Below is every key, its type, default value, and validation rules.

```yaml
bot:
    active: true              # bool, default: true — master enable flag
    mode: 'paper'             # str, default: 'mock' — mock | sim | paper | testnet | live
    debug: true               # bool, default: false — toggle verbose strategy logging
    telegram_enabled: true    # bool, default: true — enable Telegram notifications

exchange:
    name: 'binanceusdm'      # str, default: 'binanceusdm' — binanceusdm | binance | lighter | hyperliquid
    margin_type: 'ISOLATED'   # str, default: 'ISOLATED' — margin mode for futures

timeframe: '15m'              # str, default: '5m' — candle timeframe
warmup_candles: 200           # int, default: 200 — candles to load before first signal
symbols:                      # List[str], default: ['BTC/USDT']
    - 'BTC/USDT'
    - 'ETH/USDT'

# Strategy selection
strategy: 'rsi_no_retest'    # str, default: 'rsi_no_retest' — strategy module name

# Optional: Override strategy default parameters
# Merged with strategy's DEFAULT_CONFIG (see Strategy Param Hierarchy below)
strategy_params:              # Dict[str, Any], default: {} (empty dict)
    # rsi_period: 14
    # wma_retest_distance: 0.5

risk:
    max_position_size_pct: 0.99       # Decimal, default: 0.99 — max margin % per trade
    risk_per_trade_pct: 0.02          # Decimal, default: 0.02 — risk % of capital per trade
    use_risk_based_sizing: true       # bool, default: true — size by SL distance
    use_initial_capital_for_risk: true # bool, default: false — risk on initial vs current balance
    min_sl_distance_pct: 0.003        # Decimal, default: 0.003 — min SL distance; skip closer trades
    leverage: 10                       # int, default: 10 — futures leverage (1-125)
    tp1_close_pct: 0.33               # Decimal, default: 0.33 — close 1/3 at TP1
    tp2_close_pct: 0.50               # Decimal, default: 0.50 — close 1/2 of remaining at TP2

backtest:
    initial_balance: 10000            # Decimal, default: 10000 — starting USDT for backtest

paper_sim:
    initial_balance: 10000            # Decimal, default: 10000 — starting USDT for sim mode
    telegram_token: ""                # str — override Telegram token for paper; blank = reuse main
    chat_id: ""                       # str — override chat ID for paper; blank = reuse main
    tick_sample_interval_ms: 500      # int, default: 500 — aggTrade sampling interval (ms)
```

---

## Typed Config Classes

All configuration is loaded into frozen dataclasses defined in `app/core/config.py`. Validation runs in `__post_init__` at construction time. The config object is passed to constructors -- it is not a global singleton.

### AppConfig (Root)

```python
@dataclass(frozen=True)
class AppConfig:
    exchange: ExchangeConfig
    risk: RiskConfig
    notification: NotificationConfig
    backtest: BacktestConfig
    paper_sim: PaperSimConfig
    symbols: List[str]           # default: ["BTC/USDT"]
    strategy_name: str           # default: "rsi_no_retest"
    strategy_params: Dict[str, Any]  # default: {}
    timeframe: str               # default: "5m"
    warmup_candles: int          # default: 200
    debug: bool                  # default: False
```

**Loading:**

```python
config = AppConfig.from_yaml("config.yaml")
```

**Legacy compatibility:** For constructors not yet migrated to accept `AppConfig`, call:

```python
legacy_dict = config.to_legacy_dict()
```

This returns the raw dict format matching the YAML structure.

### ExchangeConfig

```python
@dataclass(frozen=True)
class ExchangeConfig:
    name: str          # default: "binanceusdm"
    mode: str          # default: "mock"
    leverage: int      # default: 10
    margin_type: str   # default: "ISOLATED"
```

**Validation:**
- `mode` must be one of: `mock`, `sim`, `paper`, `testnet`, `live`
- `name` must be one of: `binanceusdm`, `binance`, `hyperliquid`, `lighter`

**YAML mapping:** `mode` comes from `bot.mode`, `leverage` from `risk.leverage`, others from `exchange.*`.

### RiskConfig

```python
@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: Decimal      # default: 0.02
    max_position_size_pct: Decimal   # default: 0.99
    leverage: int                     # default: 10
    use_initial_capital_for_risk: bool  # default: False
    use_risk_based_sizing: bool      # default: True
    tp1_close_pct: Decimal           # default: 0.33
    tp2_close_pct: Decimal           # default: 0.50
    min_sl_distance_pct: Decimal     # default: 0.003
```

**Validation:**
- `risk_per_trade_pct`: must satisfy `0 < value <= 0.1` (max 10%)
- `leverage`: must be in range `1-125` inclusive

**Precision:** All percentage values use `Decimal` for financial precision. The YAML float values are converted via `Decimal(str(value))`.

### NotificationConfig

```python
@dataclass(frozen=True)
class NotificationConfig:
    telegram_enabled: bool   # default: True
```

**YAML mapping:** Reads from `bot.telegram_enabled`.

### BacktestConfig

```python
@dataclass(frozen=True)
class BacktestConfig:
    initial_balance: Decimal   # default: 10000
```

### PaperSimConfig

```python
@dataclass(frozen=True)
class PaperSimConfig:
    initial_balance: Decimal          # default: 10000
    tick_sample_interval_ms: int      # default: 500
```

---

## YAML-to-Dataclass Mapping

The `from_yaml` method flattens and remaps certain YAML keys. This is important to understand when modifying either the YAML schema or the config classes.

| YAML Path | Dataclass Field |
|---|---|
| `bot.mode` | `ExchangeConfig.mode` |
| `bot.debug` | `AppConfig.debug` |
| `bot.telegram_enabled` | `NotificationConfig.telegram_enabled` |
| `exchange.name` | `ExchangeConfig.name` |
| `exchange.margin_type` | `ExchangeConfig.margin_type` |
| `risk.leverage` | `ExchangeConfig.leverage` AND `RiskConfig.leverage` (duplicated) |
| `risk.*` (all others) | `RiskConfig.*` |
| `backtest.initial_balance` | `BacktestConfig.initial_balance` |
| `paper_sim.initial_balance` | `PaperSimConfig.initial_balance` |
| `paper_sim.tick_sample_interval_ms` | `PaperSimConfig.tick_sample_interval_ms` |
| `symbols` | `AppConfig.symbols` |
| `strategy` | `AppConfig.strategy_name` |
| `strategy_params` | `AppConfig.strategy_params` |
| `timeframe` | `AppConfig.timeframe` |
| `warmup_candles` | `AppConfig.warmup_candles` |

Note: `bot.active` and `paper_sim.telegram_token` / `paper_sim.chat_id` are present in YAML but not mapped to `AppConfig` fields. `bot.active` is included in the `to_legacy_dict()` output as a hardcoded `True`. The paper sim Telegram overrides are read directly from the config dict by `PaperTelegramNotifier`.

---

## Strategy Parameter Hierarchy

Strategy parameters follow a 3-level merge hierarchy (lowest to highest priority):

1. **Hardcoded defaults** -- Built into the strategy class constructor as fallback values.
2. **DEFAULT_CONFIG** -- Class-level dict on the strategy defining its standard parameters.
3. **config.yaml `strategy_params`** -- User overrides from the YAML file.

At runtime, `strategy_params` from the YAML is merged on top of the strategy's `DEFAULT_CONFIG`. Any key in `strategy_params` overwrites the same key in `DEFAULT_CONFIG`. Keys not present in `strategy_params` retain their `DEFAULT_CONFIG` values.

Example:

```yaml
# config.yaml
strategy: 'rsi_no_retest'
strategy_params:
    rsi_period: 21          # overrides DEFAULT_CONFIG's rsi_period
    # wma_period not specified → uses DEFAULT_CONFIG value
```

---

## Environment Variables (.env)

Environment variables are loaded from `.env` in the project root via `python-dotenv`. Copy `.env.example` to `.env` and fill in values.

### Variable Reference

| Variable | Required For | Purpose |
|---|---|---|
| `BINANCE_TESTNET_API_KEY` | `paper` mode | Binance testnet API key |
| `BINANCE_TESTNET_SECRET_KEY` | `paper` mode | Binance testnet secret |
| `BINANCE_API_KEY` | `live` mode | Binance mainnet API key (REAL MONEY) |
| `BINANCE_SECRET_KEY` | `live` mode | Binance mainnet secret |
| `TELEGRAM_BOT_TOKEN` | notifications | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | notifications | Telegram chat/channel ID |
| `LIGHTER_SECRET_KEY` | `lighter` exchange | DEX private key |
| `LIGHTER_ACCOUNT_INDEX` | `lighter` exchange | Account index (e.g., `0`) |
| `LIGHTER_L1_ADDRESS` | `lighter` exchange | Wallet address |
| `LIGHTER_API_KEY_INDEX` | `lighter` (optional) | Default: `2` |
| `LIGHTER_BASE_URL` | `lighter` (optional) | Override base URL |
| `HYPERLIQUID_PRIVATE_KEY` | `hyperliquid` exchange | Wallet private key |
| `PAPER_TELEGRAM_BOT_TOKEN` | paper sim (optional) | Override Telegram token for paper/sim mode |
| `PAPER_TELEGRAM_CHAT_ID` | paper sim (optional) | Override chat ID for paper/sim mode |
| `RUN_INTEGRATION_TESTS` | testing | Set to `1` to enable live Binance integration tests |

### Credential Loading Behavior

Credentials are loaded by `BinanceAdapter` at construction time (`app/trading/exchange/binance_adapter.py`):

- **Paper mode:** Reads `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_SECRET_KEY`. Raises `RuntimeError` if either is missing.
- **Live mode:** Reads `BINANCE_API_KEY` and `BINANCE_SECRET_KEY`. Raises `RuntimeError` if either is missing.
- **Mock/sim modes:** No exchange credentials required (MockExchange and PaperExchange are local simulators).

The `.env` file is located by `BinanceAdapter` via:

```python
env_path = Path(__file__).parent.parent.parent.parent / ".env"
```

This resolves to the project root regardless of working directory.

---

## Adding a New Config Field

To add a new configuration option:

1. Add the YAML key to `config.yaml` with a sensible default.
2. Add the field to the appropriate frozen dataclass in `app/core/config.py`.
3. Map it in `AppConfig.from_yaml()` with a `.get()` call and matching default.
4. If needed for legacy code paths, add it to `to_legacy_dict()`.
5. Add validation in `__post_init__` if the field has constraints.
6. Update this document.
