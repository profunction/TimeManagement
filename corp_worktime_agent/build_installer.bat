@echo off
rem Builds a one-click installer (Setup.exe) for Corp Worktime Agent using Inno Setup.
rem Requires Inno Setup to be installed first (free): https://jrsoftware.org/isdl.php
rem Run build_windows_exe.bat first if dist\CorpWorktimeAgent\ doesn't exist yet --
rem this script will offer to do that for you if it's missing.

setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist dist\CorpWorktimeAgent\CorpWorktimeAgent.exe (
    echo dist\CorpWorktimeAgent\CorpWorktimeAgent.exe not found yet.
    echo Running build_windows_exe.bat first...
    call build_windows_exe.bat
    if not exist dist\CorpWorktimeAgent\CorpWorktimeAgent.exe (
        echo [ERROR] Still no exe after build_windows_exe.bat -- fix that first, then re-run this script.
        pause
        exit /b 1
    )
)

rem Locate the Inno Setup compiler (ISCC.exe). Check PATH first, then the two common
rem install locations (64-bit and 32-bit Program Files).
set ISCC=
where iscc >nul 2>nul
if %errorlevel%==0 set ISCC=iscc
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo [ERROR] Inno Setup not found.
    echo   1. Download and install it (free) from https://jrsoftware.org/isdl.php
    echo      ^(just click through the installer with default options^)
    echo   2. Re-run this script.
    pause
    exit /b 1
)

echo Using Inno Setup compiler: %ISCC%
%ISCC% installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed -- see the messages above.
    pause
    exit /b 1
)

echo.
echo Done: installer_output\CorpWorktimeAgent-Setup.exe
echo That single file is what you hand to a machine for deployment -- running it
echo installs the app under the current user's own profile (no admin rights needed),
echo with a Start Menu entry, an optional desktop shortcut, and a normal uninstaller
echo entry. Remember: consent_notice.md and config.json are only seeded from the
echo template on first install and are never overwritten by a later upgrade.
pause
