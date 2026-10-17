@echo off
rem Run this on Windows to package worktime_agent.py into a standalone .exe
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
rem --hidden-import=win32timezone works around a known pywin32 + PyInstaller bug.
rem --noconsole hides the console window; the consent dialog/tray icon still show
rem normally, logs go to a file instead.
pyinstaller --noconfirm --onedir --noconsole --name CorpWorktimeAgent ^
    --hidden-import=win32timezone ^
    worktime_agent.py

echo [4/4] Copying config/consent templates next to the exe...
copy /Y config.example.json dist\CorpWorktimeAgent\config.example.json >nul
copy /Y consent_notice.md dist\CorpWorktimeAgent\consent_notice.md >nul
copy /Y README.md dist\CorpWorktimeAgent\README.md >nul

echo.
echo Done: dist\CorpWorktimeAgent\CorpWorktimeAgent.exe
echo Before deployment:
echo   1. Replace consent_notice.md with the HR/legal-approved final text.
echo   2. Copy config.example.json to config.json and fill in employee_id / webhook URL.
echo   3. Run CorpWorktimeAgent.exe -- the consent dialog shows on first run.
echo Logs: %%USERPROFILE%%\.timemanagement\logs\worktime_agent.log
echo Transparency log: %%USERPROFILE%%\.timemanagement\corp_worktime\transparency_log.jsonl
pause
