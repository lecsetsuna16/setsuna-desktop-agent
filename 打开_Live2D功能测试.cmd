@echo off
cd /d "%~dp0"
call "tools\find_pythonw.cmd"
if not defined PYW (
    echo [Setsuna] No usable Python environment found. Run setup.ps1 first.
    pause
    exit /b 1
)
start "" "%PYW%" "run_live2d.py" --preview
