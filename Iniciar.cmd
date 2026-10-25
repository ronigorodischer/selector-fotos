@echo off
cd /d "%~dp0"
python app.py --open
if errorlevel 1 pause
