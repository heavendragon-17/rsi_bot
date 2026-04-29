@echo off
REM One-click launcher for the backtest UI (Windows).
REM Requires Python + the project's Python deps. Node.js is NOT required at
REM runtime — the UI is served from the prebuilt ui\build\ folder.
cd /d "%~dp0"
python run_backtest_ui.py
pause
