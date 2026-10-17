@echo off
rem 在 Windows 上运行本脚本，把 worktime_agent.py 打包成免装 Python 的 .exe。
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
rem --hidden-import=win32timezone: pywin32 + PyInstaller 的已知坑。
rem --noconsole 会隐藏控制台窗口，但同意弹窗/托盘图标正常显示；日志改走文件。
pyinstaller --noconfirm --onedir --noconsole --name CorpWorktimeAgent ^
    --hidden-import=win32timezone ^
    worktime_agent.py

echo [4/4] 复制配置文件与同意书模板到输出目录...
copy /Y config.example.json dist\CorpWorktimeAgent\config.example.json >nul
copy /Y consent_notice.md dist\CorpWorktimeAgent\consent_notice.md >nul
copy /Y README.md dist\CorpWorktimeAgent\README.md >nul

echo.
echo 打包完成：dist\CorpWorktimeAgent\CorpWorktimeAgent.exe
echo 部署前：
echo   1. consent_notice.md 必须先替换成法务/HR 审核过的正式告知文本
echo   2. 把 config.example.json 复制一份改名为 config.json 并填好 employee_id / webhook 地址
echo   3. 双击 CorpWorktimeAgent.exe，首次运行会弹出同意书
echo 日志文件在 %%USERPROFILE%%\.timemanagement\logs\worktime_agent.log
echo 透明审计日志在 %%USERPROFILE%%\.timemanagement\corp_worktime\transparency_log.jsonl
pause
