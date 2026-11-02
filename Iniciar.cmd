@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call Instalar.cmd
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" app.py --open %*
if errorlevel 1 pause
