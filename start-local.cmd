@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-local.ps1"
if errorlevel 1 (
  echo Project startup failed. See the error above and .runtime\logs.
  pause
  exit /b 1
)
if /I "%~1"=="--no-browser" exit /b 0
start "" "http://127.0.0.1:5173/"
