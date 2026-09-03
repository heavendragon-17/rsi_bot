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

`npm run build` writes `ui/build/`, which is committed to the repository so
`run_backtest_ui.bat` works after a plain `git pull` with no Node.js involved.
After UI changes, rebuild and commit it with `release_ui.bat`; CI still
rebuilds from `package-lock.json` to verify the committed bundle.

Current architecture and configuration live in
[`docs/10_frontend_dashboard/`](../docs/10_frontend_dashboard/). Files under
[`ui/docs/`](docs/) named `TASK_*` and `PROJECT_COMPLETE.md` are historical
design-delivery records, not current product specifications.
