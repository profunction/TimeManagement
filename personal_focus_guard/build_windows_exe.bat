@echo off
rem Run this on Windows to package personal_focus_guard.py into a standalone .exe
rem (no Python install needed to run it afterwards).
rem PyInstaller does not cross-compile: this must run on an actual Windows machine.

setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Prefer the "py" launcher (installed by the official python.org installer) over
rem "python", because on many Windows machines "python" is a Microsoft Store shim
rem that just prints an install nag and exits instead of running anything.
set PYTHON_CMD=
py -3 --version >nul 2>nul
if %errorlevel%==0 set PYTHON_CMD=py -3
if not defined PYTHON_CMD (
    python --version >nul 2>nul
    if %errorlevel%==0 set PYTHON_CMD=python
)
if not defined PYTHON_CMD (
    echo [ERROR] No working Python found.
    echo   1. Install Python from https://www.python.org/downloads/
    echo      - Check "Add python.exe to PATH" during install.
    echo      - Make sure "py launcher" is included ^(checked by default^).
    echo   2. Then go to Settings ^> Apps ^> Advanced app settings ^> App execution aliases
    echo      and turn OFF the "python.exe" / "python3.exe" entries if they're on ^-^-
    echo      those are Microsoft Store shims that shadow a real Python install.
    echo   3. Close this window, reopen cmd, and run build_windows_exe.bat again.
    pause
    exit /b 1
)
echo Using Python command: %PYTHON_CMD%

if not exist .venv (
    echo [1/4] Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies ^(including PyInstaller^)...
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] Building exe...
rem --hidden-import=win32timezone works around a known pywin32 + PyInstaller bug where
rem the packaged exe fails at startup with ModuleNotFoundError: win32timezone.
pyinstaller --noconfirm --onedir --noconsole --name PersonalFocusGuard ^
    --hidden-import=win32timezone ^
    personal_focus_guard.py

echo [4/4] Copying config template next to the exe...
copy /Y config.example.json dist\PersonalFocusGuard\config.example.json >nul
copy /Y README.md dist\PersonalFocusGuard\README.md >nul

echo.
echo Done: dist\PersonalFocusGuard\PersonalFocusGuard.exe
echo Before first run: copy dist\PersonalFocusGuard\config.example.json to config.json
echo in that same folder and edit the blacklist/time windows as needed, then run the exe.
echo Logs: %%USERPROFILE%%\.timemanagement\logs\personal_focus_guard.log
pause
