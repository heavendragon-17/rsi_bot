# Development Environment

> Defines the runtime environment, dependencies, and commands needed to build, run, and test the RSI Bot project. An AI agent should use this to understand what tools are available and how to invoke them.

---

## Python Environment

The project requires **Python 3.13+** managed via conda.

### Activation

```bat
call C:\ProgramData\anaconda3\Scripts\activate.bat rsi
python --version
python -m pytest --version
```

The conda environment name is `rsi`. The verified workstation environment on
2026-08-20 used Python 3.13.12 and pytest 9.0.2. Run tests as
`python -m pytest` so discovery uses that interpreter. From a PowerShell
session where Conda activation is unavailable, the equivalent explicit
interpreter is:

```powershell
& 'C:\ProgramData\anaconda3\envs\rsi\python.exe' -m pytest tests -q
```

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
pip install -r requirements.txt
```

---

## Node.js Frontend Environment

The frontend lives in `ui/` and requires **Node.js 18+**.

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
cd ui && npm install && npm run build  # one-time, on a machine with Node
python run_backtest_ui.py              # or run_backtest_ui.{sh,bat}
```

`run_backtest_ui.py` starts FastAPI, which serves the prebuilt `ui/build/`
bundle at the same origin (`http://localhost:8100`) and opens a browser tab.
Once `ui/build/` exists, end users only need Python — Node is not required.

### Backtest CLI

Download historical data then run backtest:

```bash
python app/backtest/data/download.py --symbol BTC/USDT --timeframe 5m --limit 5000
python app/backtest/backtest.py --data app/backtest/data/BTCUSDT_5m.csv --balance 10000
```

### Core V2.1 acquisition, replay, and signal runtime

```bash
# Refresh the locked Binance universe and BTC benchmark
python -m app.backtest.core_v2_1.binance_data --data-dir app/backtest/data --candle-count 5000 --manifest artifacts/core_v2_1/binance_refresh.json

# Extend canonical Hyperliquid PUMP history
python -m app.signal.core_v2_1.hyperliquid_export --data-dir app/backtest/data --candle-count 5000 --manifest artifacts/core_v2_1/hyperliquid_refresh.json

# Reproduce the full 25-candidate point-in-time audit
python -m app.backtest.core_v2_1 --universe-mode full --data-dir app/backtest/data --output-dir artifacts/core_v2_1/full_replay

# Run durable public-data Telegram advisories (no orders)
python -m app.signal.core_v2_1.live --state-db data/core_v2_1_signal.sqlite3 --data-dir app/backtest/data --chat-id -1001234567890 --topic-id 42 --poll-seconds 15
```

The two market-data commands use public endpoints. The live signal process
needs `TELEGRAM_BOT_TOKEN`; `--chat-id` may instead come from
`TELEGRAM_CHAT_ID`. It does not need Binance API keys or a Hyperliquid wallet
because it has no order execution surface.

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

Regenerates `docs/database.md` from the ORM models in `app/repository/backtest/models.py`.

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
| Core V2.1 signal SQLite | `data/core_v2_1_signal.sqlite3` (default; auto-created) |
| Core V2.1 replay/manifests | `artifacts/core_v2_1/` |
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

SQLAlchemy ORM models are defined in `app/repository/backtest/models.py`. The schema is documented in `docs/database.md` (auto-generated).
