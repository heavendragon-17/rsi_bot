@echo off
REM One-click launcher for the local RSI Bot review UI (Windows).
REM Prefer the repository venv so the launcher does not use an unrelated Python.
REM Node.js is NOT required at runtime - the UI is served from ui\build\.
cd /d "%~dp0"

set "RSI_PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%RSI_PYTHON%" set "RSI_PYTHON="

for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined RSI_PYTHON set "RSI_PYTHON=%%P"
)

if not defined RSI_PYTHON (
    echo [ERROR] No python interpreter found on PATH.
    echo         Install Python or activate your conda env, then re-run this script.
    pause
    exit /b 1
)

if not exist "%~dp0ui\build" (
    echo [ERROR] ui\build is missing from this repository copy.
    echo         Run "git pull" to receive the committed UI build, or ask the
    echo         developer to rebuild it with release_ui.bat.
    pause
    exit /b 1
)

"%RSI_PYTHON%" -c "import fastapi, pandas, sqlalchemy, structlog" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The project Python environment is not ready.
    echo         Ask the developer to run setup.ps1 in the rsi_bot folder.
    pause
    exit /b 1
)

echo [INFO] Using Python: %RSI_PYTHON%
"%RSI_PYTHON%" run_backtest_ui.py
if errorlevel 1 (
    echo [ERROR] The review UI stopped unexpectedly.
    echo         Send this window's message to the developer.
)
pause
