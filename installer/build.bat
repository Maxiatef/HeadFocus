@echo off
setlocal
rem Builds the release files into release\ :
rem   HeadFocus-Setup-<version>.exe          installer (needs Inno Setup 6)
rem   HeadFocus-<version>-portable-win64.zip no-install version
rem Only the person publishing releases needs this; users just download from Releases.
rem Keep VERSION in sync with installer\version_info.txt.
set "VERSION=1.0.0"

rem Work from the repo root (this file lives in installer\).
cd /d "%~dp0.."
set "ROOT=%cd%"
set "APP=%ROOT%\release\app\HeadFocus"

if not exist .venv\Scripts\python.exe (
    call setup.bat --quiet || goto :fail
)
.venv\Scripts\python.exe headfocus.py --download-model || goto :fail
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check pyinstaller || goto :fail

echo === Building HeadFocus.exe ===
rem Folder build, not --onefile: a single-file exe unpacks ~115 MB on every
rem launch and antivirus rescans it, so it takes up to a minute to start.
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --console ^
    --name HeadFocus ^
    --distpath "%ROOT%\release\app" ^
    --workpath "%ROOT%\release\build" ^
    --specpath "%ROOT%\release\build" ^
    --version-file "%ROOT%\installer\version_info.txt" ^
    --icon "%ROOT%\assets\icon.ico" ^
    --add-data "%ROOT%\models\face_landmarker.task;models" ^
    --collect-all mediapipe ^
    headfocus.py || goto :fail

.venv\Scripts\python.exe installer\collect_licenses.py || goto :fail
copy /y LICENSE "%APP%\LICENSE.txt" >nul
copy /y THIRD_PARTY_NOTICES.md "%APP%\" >nul
copy /y installer\README.txt "%APP%\README.txt" >nul

echo === Portable zip ===
rem Double-click helpers, since the portable version has no Start Menu shortcuts.
set "PORT=%ROOT%\release\portable\HeadFocus"
if exist "%ROOT%\release\portable" rmdir /s /q "%ROOT%\release\portable"
xcopy /e /i /q /y "%APP%" "%PORT%" >nul || goto :fail
> "%PORT%\Calibrate.bat" echo @"%%~dp0HeadFocus.exe" --calibrate
> "%PORT%\HeadFocus (preview).bat" echo @"%%~dp0HeadFocus.exe" --preview
set "ZIP=%ROOT%\release\HeadFocus-%VERSION%-portable-win64.zip"
if exist "%ZIP%" del "%ZIP%"
rem tar ships with Windows 10+ and writes real .zip files with -a.
tar -a -c -f "%ZIP%" -C "%ROOT%\release\portable" HeadFocus || goto :fail

echo === Installer ===
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
    echo Inno Setup 6 not found - skipped the installer. Get it from https://jrsoftware.org/isdl.php
    echo or run:  winget install JRSoftware.InnoSetup
    goto :done
)
"%ISCC%" /Q /DAppVersion=%VERSION% installer\HeadFocus.iss || goto :fail

:done
echo.
echo Release files in %ROOT%\release :
dir /b "%ROOT%\release\*.exe" "%ROOT%\release\*.zip" 2>nul
echo Upload them to a GitHub Release.
pause
exit /b 0

:fail
echo.
echo Build failed. See the message above.
pause
exit /b 1
