@echo off
rem 在 Windows 上运行本脚本，把 personal_focus_guard.py 打包成免装 Python 的 .exe。
rem PyInstaller 不支持跨平台编译，必须在 Windows 机器上执行，不能在 Linux/Mac 上跑出 Windows exe。

setlocal
cd /d "%~dp0"

if not exist .venv (
    echo [1/4] 创建虚拟环境...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] 安装依赖（含 PyInstaller）...
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] 打包中...
rem --hidden-import=win32timezone: pywin32 + PyInstaller 的已知坑，不加这个某些环境下打包出来的
rem exe 启动会报 ModuleNotFoundError: win32timezone。
pyinstaller --noconfirm --onedir --noconsole --name PersonalFocusGuard ^
    --hidden-import=win32timezone ^
    personal_focus_guard.py

echo [4/4] 复制配置文件模板到输出目录...
copy /Y config.example.json dist\PersonalFocusGuard\config.example.json >nul
copy /Y README.md dist\PersonalFocusGuard\README.md >nul

echo.
echo 打包完成：dist\PersonalFocusGuard\PersonalFocusGuard.exe
echo 首次运行前，先把 dist\PersonalFocusGuard\config.example.json 复制一份改名为 config.json，
echo 按需修改黑名单关键词/时间段，再双击 PersonalFocusGuard.exe。
echo 日志文件在 %%USERPROFILE%%\.timemanagement\logs\personal_focus_guard.log
pause
