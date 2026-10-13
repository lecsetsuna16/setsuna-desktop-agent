@echo off
rem Sets PYW to the pythonw.exe that owns this install's packages (same order as run.bat).
rem Callers must cd to the project root first. PYW stays empty when nothing is usable.
set "PYW="
if exist "runtime\pythonw.exe" (set "PYW=runtime\pythonw.exe" & goto :eof)
if not exist "venv\Scripts\pythonw.exe" goto shim
if not exist "venv\pyvenv.cfg" goto shim
set "VENV_HOME="
for /f "usebackq tokens=1,* delims== " %%A in ("venv\pyvenv.cfg") do if /i "%%A"=="home" set "VENV_HOME=%%B"
rem A venv launcher only works while the base interpreter it was created from still exists.
if defined VENV_HOME if exist "%VENV_HOME%\python.exe" (set "PYW=venv\Scripts\pythonw.exe" & goto :eof)
:shim
rem Portable interpreter that borrows venv packages; run_live2d.py rejects a version mismatch.
if exist "runtime_live2d\pythonw.exe" set "PYW=runtime_live2d\pythonw.exe"
goto :eof
