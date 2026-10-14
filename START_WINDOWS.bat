@echo off
setlocal
title Sequence - Job-Shop Scheduling
pushd "%~dp0"

echo Checking Python and Node.js...
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 or newer is required on PATH.
    echo Install Python with Add python.exe to PATH enabled, then try again.
    goto failed
)
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 22 ? 0 : 1)" >nul 2>&1
if errorlevel 1 (
    echo Node.js 22 or newer is required. Install it, then try again.
    goto failed
)
where npx >nul 2>&1
if errorlevel 1 (
    echo npx was not found. Install Node.js with its bundled npm tools.
    goto failed
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    python -m venv .venv
    if errorlevel 1 goto failed
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install -r backend/requirements.lock
if errorlevel 1 goto failed

echo Installing frontend dependencies...
cd frontend
call npx --yes pnpm@11.19.0 install --frozen-lockfile
if errorlevel 1 (
    cd ..
    goto failed
)
cd ..

echo.
echo Open http://127.0.0.1:5173 in your browser when the servers start.
echo Keep this window open. Press Ctrl+C to stop the application.
echo.
".venv\Scripts\python.exe" scripts/dev.py
if errorlevel 1 goto failed
popd
endlocal
exit /b 0

:failed
echo.
echo Setup or startup failed. Read the error above and START_HERE.txt.
pause
popd
endlocal
exit /b 1
