@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto use_python
for %%V in (3.11 3.12 3.13) do (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        py -%%V setup_selector.py
        goto result
    )
)
:use_python
python setup_selector.py
:result
if errorlevel 1 (
    echo.
    echo Instala Python 3.11, 3.12 o 3.13 de 64 bits desde python.org y vuelve a intentarlo.
    pause
    exit /b 1
)
pause
