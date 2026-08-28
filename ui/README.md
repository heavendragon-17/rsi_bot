# RSI Bot Backtest UI

React 18, TypeScript, and Vite frontend for configuring backtests and
inspecting results from the FastAPI backend.

## Development

Prerequisites: Node.js 20+ and a running API at `http://localhost:8100`.

```bash
npm ci
npm run dev
```

Vite serves the UI at `http://localhost:3100`. Override the ports or API URL
with `VITE_PORT` and `VITE_API_URL`.

## Checks and production build

```bash
npm run type-check
npm run build
```

`npm run build` writes the Git-ignored `ui/build/` directory. CI always rebuilds
it from `package-lock.json`; generated assets are not committed. Once built,
`python run_backtest_ui.py` can serve the complete application without Node.js
remaining active at runtime.

Current architecture and configuration live in
[`docs/10_frontend_dashboard/`](../docs/10_frontend_dashboard/). Files under
[`ui/docs/`](docs/) named `TASK_*` and `PROJECT_COMPLETE.md` are historical
design-delivery records, not current product specifications.
