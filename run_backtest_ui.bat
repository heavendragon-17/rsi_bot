@echo off
REM One-click launcher for the backtest UI (Windows).
REM Uses the project's conda env (rsi) — the system Python lacks deps like uvicorn.
REM Node.js is NOT required at runtime — the UI is served from ui\build\.
cd /d "%~dp0"

set "RSI_PYTHON=C:\ProgramData\anaconda3\envs\rsi\python.exe"
if not exist "%RSI_PYTHON%" (
    echo [WARN] %RSI_PYTHON% not found. Falling back to PATH python.
    echo        If you hit ModuleNotFoundError, edit RSI_PYTHON in this script.
    set "RSI_PYTHON=python"
)

"%RSI_PYTHON%" run_backtest_ui.py
pause
