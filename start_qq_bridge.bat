@echo off
cd /d %~dp0
echo [Resona QQ Bridge] Starting...

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe qq_bridge.py
) else if exist "runtime\python.exe" (
    runtime\python.exe qq_bridge.py
) else (
    python qq_bridge.py
)

pause
