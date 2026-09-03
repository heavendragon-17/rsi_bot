@echo off
REM Developer-only helper: rebuild the UI bundle and commit it to git.
REM The committed ui\build is what clients receive with a plain git pull, so
REM run this after every UI source change and before pushing.
setlocal
cd /d "%~dp0"

echo [INFO] Building UI...
pushd ui
call npm run build
if errorlevel 1 (
    echo [ERROR] UI build failed. Fix the errors above and re-run.
    popd
    pause
    exit /b 1
)
popd

git add ui/build
git commit -m "chore: rebuild UI bundle" -- ui/build
if errorlevel 1 (
    echo [INFO] ui\build already matches the current source - nothing to commit.
    exit /b 0
)

echo [INFO] Pushing...
git push
if errorlevel 1 (
    echo [ERROR] Push failed. Resolve the git error above, then push manually.
    pause
    exit /b 1
)
echo [OK] UI rebuilt and pushed. Clients get it on their next git pull.
pause
