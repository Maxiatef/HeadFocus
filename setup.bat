@echo off
setlocal
cd /d "%~dp0"
echo === HeadFocus setup ===
echo.

rem Prefer the Python launcher (py), fall back to python on PATH.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python was not found.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during install. Then run setup.bat again.
    goto :fail
)

echo [1/3] Creating private Python environment in .venv ...
if not exist .venv\Scripts\python.exe (
    %PY% -m venv .venv || goto :fail
)

echo [2/3] Installing packages (a few minutes the first time) ...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet --disable-pip-version-check
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet --disable-pip-version-check || goto :fail

echo [3/3] Downloading face model ...
.venv\Scripts\python.exe headfocus.py --download-model || goto :fail

echo.
echo Setup complete. Double-click run.bat to start.
if "%~1"=="--quiet" exit /b 0
pause
exit /b 0

:fail
echo.
echo Setup failed. See the message above.
if "%~1"=="--quiet" exit /b 1
pause
exit /b 1
