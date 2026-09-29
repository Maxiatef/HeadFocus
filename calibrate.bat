@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    call setup.bat --quiet || (pause & exit /b 1)
)
.venv\Scripts\python.exe headfocus.py --calibrate
pause
