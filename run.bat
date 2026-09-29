@echo off
cd /d "%~dp0"
rem First time on a new PC: install everything automatically.
if not exist .venv\Scripts\python.exe (
    call setup.bat --quiet || (pause & exit /b 1)
)
rem Calibrates automatically when needed (first run, old calibration, or monitors changed).
.venv\Scripts\python.exe headfocus.py %*
pause
