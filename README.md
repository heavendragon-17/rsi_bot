# RSI Bot

RSI Bot is a Python 3.13 cryptocurrency trading and research system with
live/simulated execution, signal-only Telegram alerts, a backtest engine, and
a React/FastAPI analysis UI.

> **Risk warning:** `live` mode can place real futures orders. Start with
> `mock`, then `sim`, then testnet `paper`. Review the
> [deployment checklist](docs/12_deployment_and_ops/deployment-checklist.md)
> before enabling real-money execution.

## Capabilities

- WebSocket-driven Binance USDT-M futures execution
- Read-only signal mode with strategy-specific Telegram topics
- Simulated fills against live ticks and Binance testnet integration
- Single-symbol, portfolio, batch, and tick-replay backtests
- Grid search, walk-forward analysis, sensitivity analysis, and audit reports
- FastAPI + React backtest interface with a locally generated production bundle

## Quick start

Prerequisites: Python 3.13 and Git. Node.js 20+ is only required when changing
the frontend.

```bash
git clone https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot
python -m venv venv
```

Activate the environment, then install and configure the application:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

On PowerShell, activate with `venv\Scripts\Activate.ps1` and copy the template
with `Copy-Item .env.example .env`. On Linux/macOS, activate with
`source venv/bin/activate`.

Review `.env` and `config.yaml`, then run the configured bot mode:

```bash
python main.py
```

Configuration and exchange-mode details are in
[configuration.md](docs/03_setup_and_installation/configuration.md) and
[exchange-modes.md](docs/03_setup_and_installation/exchange-modes.md).

## Backtest UI

The one-process launcher serves the committed `ui/build/` bundle and API on
`http://localhost:8100` by default. The bundle ships with the repository, so a
plain `git pull` plus Python is enough:

```bash
python run_backtest_ui.py
```

After a frontend source change, rebuild and re-commit the bundle with
`release_ui.bat`, which runs the production build and commits `ui/build/`.

On Windows, a non-technical reviewer can double-click `run_backtest_ui.bat`
after the one-time setup. It uses the local project environment and opens the
browser-based UI automatically. See the [BTC Signal Review Lab guide](wiki/btc-signal-review-guide.md)
for the simplified human-review workflow.

For frontend development, run the API and Vite separately:

```bash
python -m app.api.main
cd ui
npm ci
npm run dev
```

The development UI defaults to `http://localhost:3100` and calls the API at
`http://localhost:8100`. Use `API_PORT`, `VITE_PORT`, and `VITE_API_URL` to
override those defaults.

## Backtest CLI

```bash
# Download OHLCV data
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 5000

# Run a single-symbol OHLCV backtest
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000

# Run portfolio, batch, or tick-replay modes
python -m app.backtest.runners.portfolio_runner
python -m app.backtest.runners.batch_runner --workers 8
python -m app.backtest.runners.tick_replay --help
```

See the [backtest guide](wiki/backtest-guide.md) and
[sim/tick-replay guide](wiki/sim-backtest.md) for complete workflows.

## Documentation

| Audience | Start here | Purpose |
|---|---|---|
| Users | [Getting started](wiki/getting-started.md) | Installation and first run |
| Human validators | [BTC Signal Review Lab](wiki/btc-signal-review-guide.md) | Run and manually review BTC M5/M15 alerts |
| Operators | [VPS deployment](docs/12_deployment_and_ops/vps-deployment-guide.md) | Production setup and recovery |
| Contributors | [Documentation index](docs/INDEX.md) | Task-based technical documentation |
| AI agents | [Onboarding](docs/00_onboarding/onboarding.md) | Repository workflow and conventions |
| Security reviewers | [Security policy](SECURITY.md) | Secret and vulnerability handling |

Historical implementation plans are retained under
[`docs/archive/`](docs/archive/) for provenance; they are not current system
specifications.

## Repository layout

```text
app/core/          Interfaces, actions, configuration, and shared models
app/data/          Market-data ingestion, normalization, and indicators
app/trading/       Strategies, execution adapters, portfolio, and runtime
app/signal/        Signal-only orchestration and BTC RSI alert workers
app/backtest/      Engines, exchanges, runners, reporting, and audit tools
app/api/           FastAPI routes and application entry point
app/notification/  Telegram and notification services
app/repository/    SQLAlchemy persistence
ui/                React/Vite frontend sources and local generated build output
tests/             Python regression suite
deploy/            systemd installation and deployment scripts
docs/              Technical specifications and operational runbooks
wiki/              User-facing guides
```

## Development checks

```bash
python -m pytest tests/ -q
python -m ruff check app tests scripts
python -m mypy app --ignore-missing-imports
python scripts/arch_lint.py
python scripts/check_markdown_links.py
cd ui && npm ci && npm run build
```

CI also runs security, dependency, secret, coverage, documentation, and UI
checks. See the [enforcement guide](docs/16_enforcement/enforcement.md).

## License

No open-source license is currently declared for this public repository.
