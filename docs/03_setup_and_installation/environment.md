# Development Environment

> Defines the runtime environment, dependencies, and commands needed to build, run, and test the RSI Bot project. An AI agent should use this to understand what tools are available and how to invoke them.

---

## Python Environment

The project requires **Python 3.13+**. A standard virtual environment is the
portable default; the repository can also be used from a Conda environment.

### Virtual environment

```bash
python -m venv venv
# Linux/macOS
source venv/bin/activate
# PowerShell
venv\Scripts\Activate.ps1
```

Existing local development commonly uses a Conda environment named `rsi`:

```bash
conda create -n rsi python=3.13
conda activate rsi
```

Whichever environment is selected, invoke tools through `python -m ...` so
they use the same interpreter as the application.

### Key Python Dependencies

Defined in `requirements.txt` (project root):

| Package | Purpose |
|---|---|
| `ccxt` | Unified exchange API (Binance USDT-M futures) |
| `pandas` | DataFrame operations for candle data |
| `pandas_ta` | Technical indicators (RSI, WMA, etc.) |
| `numpy` | Numerical operations |
| `fastapi>=0.111.0` | REST API framework for backtest UI |
| `uvicorn[standard]>=0.29.0` | ASGI server |
| `sse-starlette>=2.1.0` | Server-Sent Events for backtest progress streaming |
| `sqlalchemy` | ORM for backtest result storage (SQLite) |
| `structlog>=24.0.0` | Structured logging (zero print statements allowed) |
| `pyyaml` | Config file parsing |
| `python-dotenv` | `.env` file loading |
| `pydantic` | Data validation (used by FastAPI) |
| `websocket-client` | Binance WebSocket connections |
| `binance` | Binance Python SDK |
| `binance-futures-connector` | Binance futures-specific SDK |
| `hyperliquid-python-sdk` | Hyperliquid DEX integration |
| `python-dateutil` | Date parsing utilities |
| `pytest` | Test framework |

Install all dependencies:

```bash
python -m pip install -r requirements.txt
```

### Container build

The root `Dockerfile` uses Python 3.13 and runs as an unprivileged `bot` user.
The build context excludes secrets, databases, logs, caches, and local data via
`.dockerignore`.

```bash
docker build -t rsi-bot:local .
docker run --rm rsi-bot:local python -c "from app.core import config; print('container import OK')"
```

The container is currently a reproducible local runtime option, not the VPS
release mechanism. The production path remains the tagged systemd workflow in
`docs/12_deployment_and_ops/vps-deployment-guide.md`.

---

## Node.js Frontend Environment

The frontend lives in `ui/` and requires **Node.js 20+**.

### Key Frontend Dependencies

Defined in `ui/package.json`:

| Package | Purpose |
|---|---|
| `react ^18.3.1` | UI framework |
| `react-dom ^18.3.1` | React DOM renderer |
| `typescript ^5.9.3` | Type system |
| `zustand` | State management (stores) |
| `lightweight-charts` | TradingView Lightweight Charts (v5) for candlestick rendering |
| `recharts ^2.15.2` | Chart components for metrics visualization |
| `@radix-ui/*` | Headless UI primitives (shadcn/ui foundation) |
| `tailwind-merge` | Tailwind CSS class merging |
| `class-variance-authority ^0.7.1` | Variant-based component styling |
| `lucide-react ^0.487.0` | Icon library |
| `sonner ^2.0.3` | Toast notifications |
| `react-resizable-panels ^2.1.7` | Resizable panel layouts |
| `papaparse` | CSV parsing (data import/export) |
| `html2canvas` / `jspdf` / `jszip` | Report export (PDF, ZIP) |
| `motion` | Animations |
| `vite 6.3.5` | Build tool and dev server |
| `@vitejs/plugin-react-swc ^3.10.2` | SWC-based React plugin for Vite |

### Frontend Build Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server (HMR) |
| `npm run build` | Type-check then production build (`tsc --noEmit && vite build`) |
| `npm run type-check` | TypeScript type checking only (`tsc --noEmit`) |
| `npm run generate-types` | Export Python API schema to TypeScript types (`cd .. && python -m app.api.export_schema`) |

---

## Run Commands

### Live Bot

```bash
python main.py
```

Reads `config.yaml` for mode, symbols, strategy, and risk parameters. Connects to exchange based on `bot.mode` setting.

### Backtest UI (Full Stack)

**Development** — backend + Vite dev server (hot reload):

```bash
python -m app.api.main                # backend on :8100
cd ui && npm run dev                  # UI on :3100, talks to :8100
```

**Production / one-click (no Node.js needed at runtime)**:

```bash
cd ui && npm ci && npm run build       # one-time, on a machine with Node
python run_backtest_ui.py              # or run_backtest_ui.{sh,bat}
```

`run_backtest_ui.py` starts FastAPI, which serves the prebuilt `ui/build/`
bundle at the same origin (`http://localhost:8100`) and opens a browser tab.
The generated directory is intentionally ignored by Git. Once it exists, end
users only need Python — Node is not required while the application runs.
On Windows, `run_backtest_ui.bat` prefers the repository's
`venv\Scripts\python.exe` and checks that the UI bundle and core dependencies
are ready before starting. This supports a one-click handoff to a human chart
reviewer; the reviewer workflow is documented in
[`wiki/btc-signal-review-guide.md`](../../wiki/btc-signal-review-guide.md).

### Backtest CLI

Download historical data then run backtest:

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 5000
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

### Tests

```bash
python -m pytest tests/ -v              # All tests
python -m pytest tests/test_file.py -v  # Single file
python -m pytest tests/test_file.py::test_name  # Single test
```

Notes:
- `pytest` version: 9.0.2
- Some test files (e.g., `test_binance_adapter.py`) require real API keys and will fail locally without them.
- Set `RUN_INTEGRATION_TESTS=1` in `.env` to enable live integration tests.

### Database Docs Regeneration

```bash
python scripts/gen_db_docs.py
```

Regenerates `docs/14_api_reference/database.md` from the ORM models in
`app/repository/backtest/models.py`.

---

## File Locations

| Item | Path |
|---|---|
| Python dependencies | `requirements.txt` (project root) |
| Frontend dependencies | `ui/package.json` |
| Bot configuration | `config.yaml` (project root) |
| Environment variables | `.env` (project root, git-ignored) |
| Environment template | `.env.example` (project root, committed) |
| SQLite database | `data/backtest.db` (auto-created on first backtest run) |
| Backtest CSV data | `app/backtest/data/` |
| Frontend source | `ui/src/` |
| Backend API | `app/api/` |

---

## Environment Variables Setup

1. Copy the template:
   ```bash
   cp .env.example .env
   ```

2. Fill in the required values for your target mode (see `configuration.md` for the full variable reference).

3. Never commit `.env` to version control. The `.gitignore` already excludes it.

---

## Database

The project uses **SQLite** for backtest result persistence. The database file is auto-created at `data/backtest.db` on the first backtest run. No manual database setup is required.

SQLAlchemy ORM models are defined in `app/repository/backtest/models.py`. The
schema is documented in `docs/14_api_reference/database.md` (auto-generated).
