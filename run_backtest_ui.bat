@echo off
REM One-click launcher for the backtest UI (Windows).
REM Discovers Python via `where python` and uses the first match to run the backend.
REM Node.js is NOT required at runtime — the UI is served from ui\build\.
cd /d "%~dp0"

set "RSI_PYTHON="
for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined RSI_PYTHON set "RSI_PYTHON=%%P"
)

if not defined RSI_PYTHON (
    echo [ERROR] No python interpreter found on PATH.
    echo         Install Python or activate your conda env, then re-run this script.
    pause
    exit /b 1
)

echo [INFO] Using Python: %RSI_PYTHON%
"%RSI_PYTHON%" run_backtest_ui.py
pause
