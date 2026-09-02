# Configuration Reference

> Complete schema reference for `config.yaml`, typed config classes in `app/core/config.py`, and environment variables in `.env`. An AI agent should consult this before modifying any configuration-related code.

## Local Python environment

On the Windows development workstation, use the existing Conda environment
named `rsi` for repository commands:

```bat
call C:\ProgramData\anaconda3\Scripts\activate.bat rsi
python --version
python -m pytest tests -q
```

The verified baseline on 2026-08-20 used Python 3.13.12 and pytest 9.0.2.
Run pytest as `python -m pytest` so the selected Conda interpreter, rather
than a different global launcher, owns test discovery.

---

## config.yaml Full Schema

The bot reads `config.yaml` from the project root at startup.

* **Live modes** (`mock` / `sim` / `paper` / `testnet` / `live`) parse via
  `AppConfig.from_yaml("config.yaml")` and drive `MultiSymbolRunner`.
* **Signal mode** (`bot.mode: "signal"`) bypasses `AppConfig` and feeds the
  raw dict to `resolve_strategy_configs()` in `app/signal/strategy_config.py`.
  See the [Signal mode schema](#signal-mode-schema) section below.

Below is every live-mode key, its type, default value, and validation rules.

```yaml
bot:
    active: true              # compatibility field; currently not a runtime stop switch
    mode: 'paper'             # str, default: 'mock' — mock | sim | paper | testnet | live | signal
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

# NOTE: strategy_params has been removed from config.yaml.
# Strategy parameters are now defined in frozen config dataclasses
# within each strategy file (e.g., RsiNoRetestConfig, RsiMomentumConfig).
# See docs/07_trading_strategies/strategy-config.md for details.

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
| `timeframe` | `AppConfig.timeframe` |
| `warmup_candles` | `AppConfig.warmup_candles` |

> **Important:** `bot.active` is not currently enforced by `main.py` or mapped
> to `AppConfig`; `to_legacy_dict()` emits a hardcoded `True`. Do not rely on it
> as a production kill switch. Stop/disable the systemd service or change to a
> non-executing mode. The paper-sim Telegram overrides are read directly from
> the raw config by the simulation notification path.

---

## Strategy Parameter Hierarchy

Strategy parameters are now self-contained in frozen config dataclasses within each strategy file (e.g., `RsiNoRetestConfig`, `RsiMomentumConfig`). They are **not** stored in `config.yaml`.

The hierarchy (lowest to highest priority):

1. **Frozen dataclass defaults** -- Built into the strategy's config dataclass (e.g., `RsiNoRetestConfig`).
2. **DEFAULT_CONFIG** -- Class-level dict on the strategy defining its standard parameters.
3. **Backtest UI sidebar** -- Per-run overrides in the backtest UI.

See `docs/07_trading_strategies/strategy-config.md` for full details.

## Constants (`app/core/constants.py`)

System-wide constants are centralized in `app/core/constants.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `WARMUP` | `220` | Minimum candles before first signal |
| `MAX_CANDLES_IN_RAM` | `6000` | Memory cap per symbol in MarketDataStore |
| `DEFAULT_TAKER_FEE` | `0.0005` | Default taker fee rate (0.05%) |
| `DEFAULT_MAKER_FEE` | `0.0002` | Default maker fee rate (0.02%) |

All constants must be imported from this module. Do not hardcode these values elsewhere.

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

Core V2.1's standalone signal runtime uses `TELEGRAM_BOT_TOKEN` and either
`--chat-id` or `TELEGRAM_CHAT_ID`. Its Binance and Hyperliquid market-data
clients are public: it does not read Binance API keys,
`HYPERLIQUID_PRIVATE_KEY`, or any trading-wallet credential.

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

## Core V2.1 standalone signal runtime

Core V2.1 is launched separately from `main.py` and does not consume the
`config.yaml` signal-mode schema below:

```bat
call C:\ProgramData\anaconda3\Scripts\activate.bat rsi
python -m app.signal.core_v2_1.live ^
  --state-db data\core_v2_1_signal.sqlite3 ^
  --data-dir app\backtest\data ^
  --chat-id -1001234567890 ^
  --topic-id 42 ^
  --poll-seconds 15
```

| CLI option | Default | Meaning |
|---|---|---|
| `--state-db` | `data/core_v2_1_signal.sqlite3` | Durable raw candles, strategy state/cursors, transition/event audit, bootstrap record, and Telegram outbox |
| `--data-dir` | `app/backtest/data` | Canonical anchored CSV directory used to seed cold runtime state, especially Hyperliquid PUMP |
| `--chat-id` | `TELEGRAM_CHAT_ID` | Target chat or supergroup; one of CLI/env is required |
| `--topic-id` | none | Optional shared Telegram forum topic for every Core V2.1 candidate |
| `--poll-seconds` | `15` | Public mixed-venue REST poll interval |

On a cold database the production composition validates and, when present,
seeds the locked Hyperliquid PUMP history from the canonical
`app/backtest/data/HYPERLIQUID__PUMP_USDC_PERP_15m.csv`, then reconciles the
latest public venue tails. If the file is absent, it falls through to public
venue hydration, which still must reach the anchor and therefore fails closed
after the rolling API window has advanced past it. A malformed or wrongly
routed seed is always rejected. The runtime also requires authoritative
exchange clocks and all required market keys to reach the exact finalized tail
before it reports ready.

This command is signal-only. It has no exchange adapter or order credentials,
and the database contains no positions, fills, or PnL ledger. See
[Core V2.1 standalone durable runtime](../07_trading_strategies/signal-bot.md#core-v21-standalone-durable-runtime).

---

## Adding a New Config Field

To add a new configuration option:

1. Add the YAML key to `config.yaml` with a sensible default.
2. Add the field to the appropriate frozen dataclass in `app/core/config.py`.
3. Map it in `AppConfig.from_yaml()` with a `.get()` call and matching default.
4. If needed for legacy code paths, add it to `to_legacy_dict()`.
5. Add validation in `__post_init__` if the field has constraints.
6. Update this document.

---

## Signal mode schema

When `bot.mode: "signal"` is set, `main.py` bypasses `AppConfig.from_yaml` and
passes the raw YAML dict directly to `resolve_strategy_configs()` in
`app/signal/strategy_config.py`. The live-mode keys above remain valid in the
file (they are ignored by the signal path) — only the keys documented here
are consumed in signal mode.

**Authoritative spec**: [docs/07_trading_strategies/signal-bot.md](../07_trading_strategies/signal-bot.md) §3.

```yaml
bot:
    mode: "signal"           # required — selects the signal-bot runtime

telegram:
    group_id: -1001234567890 # int, required — supergroup with topics enabled
    debug_topic_id: 99       # int, required — receives expiry/failure/warn messages

timeframe: "15m"             # str, required — global default, overridable per strategy
symbols:                     # List[str], required — global default, overridable per strategy
    - "BTC/USDT"
    - "ETH/USDT"

strategies:                  # List[dict], required
    - name: rsi_no_retest    # str, required — must exist in STRATEGY_MAP
      active: true           # bool, default: true
      telegram_topic_id: 42  # int, required — must be unique and != debug_topic_id
      # Optional overrides; missing keys fall through to the globals above.
      # timeframe: "1h"
      # symbols: ["BTC/USDT"]
      # risk:
      #   tp1_close_pct: 0.5 # merges into the global risk block
    # Alert-only component (Telegram advisory, never places orders).
    # Not in STRATEGY_MAP; resolved by app/signal/btc_rsi_cross_alert/config.py.
    - name: btc_rsi_cross_alert
      active: true           # Telegram-only BTC alert component
      telegram_topic_id: 1147       # M5 checker topic
      m15_telegram_topic_id: 1003   # M15 checker topic
      symbol: "BTC/USDT"     # locked — canonical BTC/USDT only
      trigger_timeframes: ["5m", "15m"]  # locked — exactly {5m, 15m}
      confirmation_timeframe: "1h"  # locked — native Binance H1 EMA21 gate
      trend_timeframe: "4h"  # locked — native Binance H4 (no resampling)
      rsi_period: 21         # locked
      rsi_ema_period: 9      # locked
      rsi_wma_period: 45     # locked
      context_settle_seconds: 5  # int, locked range [0, 30]

virtual_positions:
    max_age_candles: 50      # int, default: 50 (SIGNAL_MAX_VP_AGE_CANDLES) — auto-expire

signal_runner:
    max_consecutive_failures: 3  # int, default: 3 — thread dies after N errors on same symbol

data:
    max_candles_per_timeframe: # dict[str, int] — per-TF RAM cap for the multiplexer
        "1m": 6000
        "5m": 6000
        "15m": 6000
        "1h": 3000
        "4h": 1500
        "1d": 500
```

### Validation rules (enforced at startup)

| Rule | Raises |
|------|--------|
| `telegram.group_id` present | `ValueError` |
| `telegram.debug_topic_id` present and int-coercible | `ValueError` |
| Every active strategy declares a `name` that exists in `STRATEGY_MAP` (or is `btc_rsi_cross_alert`) | `ValueError` |
| Every active strategy declares `telegram_topic_id` | `ValueError` |
| `telegram_topic_id` values are unique across active strategies **and** alert component routes | `ValueError` |
| No strategy/component route uses `debug_topic_id` | `ValueError` |
| If every strategy and component is inactive (or the list is empty), runner warn-logs and exits cleanly | (no raise) |

#### `btc_rsi_cross_alert` component validation

Resolved by `resolve_btc_rsi_cross_alert_config()` (see
[docs/07_trading_strategies/btc-rsi-cross-alert-spec.md](../07_trading_strategies/btc-rsi-cross-alert-spec.md)
§6). All values are explicit in YAML for auditability but **locked** for v1:

| Rule | Raises |
|------|--------|
| `symbol` is exactly `"BTC/USDT"` | `ValueError` |
| `trigger_timeframes` present, duplicate-free, exactly `{5m, 15m}` | `ValueError` |
| `confirmation_timeframe == "1h"` | `ValueError` |
| `trend_timeframe == "4h"` | `ValueError` |
| `rsi_period`, `rsi_ema_period`, `rsi_wma_period` are exactly `21`, `9`, `45` (plain integers; no float/string coercion) | `ValueError` |
| `context_settle_seconds` is an integer in `[0, 30]` (bools rejected) | `ValueError` |
| `telegram_topic_id` (M5) and `m15_telegram_topic_id` (M15) are present and integer-coercible | `ValueError` |
| M5 and M15 topic IDs are different and do not collide with an active strategy or debug topic | `ValueError` |
| At most one active `btc_rsi_cross_alert` entry | `ValueError` |
| Disabled entries are ignored entirely — their topic is **not** reserved | (no raise) |

An alert-only configuration (zero ordinary strategies + one active BTC alert)
is valid and starts the full signal runtime. The checked-in default disables
the ordinary `rsi_no_retest` strategy and routes the BTC M5/M15 checkers to
topics `1147` and `1003`, respectively.

### Merge semantics (global → per-strategy override)

| Field | Rule |
|-------|------|
| `symbols` | Per-strategy `symbols` replaces the global list when present. |
| `timeframe` | Per-strategy `timeframe` replaces the global value when present. |
| `risk` | Per-strategy `risk` **merges field-by-field** into the global `RiskConfig` (unspecified keys fall through). Unknown keys are warn-logged and ignored to catch typos. |
| `active` | Defaults to `true` when the key is missing. |

### Runtime constants

Signal-mode defaults live in `app/core/constants.py`:

* `SIGNAL_MAX_VP_AGE_CANDLES = 50`
* `SIGNAL_MAX_CONSECUTIVE_FAILURES = 3`
* `SIGNAL_WORKER_QUEUE_SIZE = 500`
* `SIGNAL_SHUTDOWN_JOIN_SECONDS = 10`
* `MAX_CANDLES_IN_RAM_PER_TF` — fallback for `data.max_candles_per_timeframe`
* `TIMEFRAME_SECONDS` — the exit monitor's TF→seconds lookup
