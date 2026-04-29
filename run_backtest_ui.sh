#!/usr/bin/env bash
# One-click launcher for the backtest UI (macOS/Linux).
# Requires Python + the project's Python deps. Node.js is NOT required at
# runtime — the UI is served from the prebuilt ui/build/ folder.
set -e
cd "$(dirname "$0")"
exec python run_backtest_ui.py
