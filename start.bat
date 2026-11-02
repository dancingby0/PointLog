@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PointLog

rem 用法：start.bat            启动服务 + 浏览器 + 专注计时器
rem       start.bat --no-timer 只启动服务（旧行为）
rem       start.bat --no-wait  计时器等不到服务时也直接打开
set "ARGS=%*"

if not exist ".venv\Scripts\python.exe" (
    echo [PointLog] 首次运行：正在创建 Python 虚拟环境……
    py -3 -m venv .venv
    if errorlevel 1 (
        echo.
        echo [错误] 创建虚拟环境失败。
        echo 请确认已安装 Python 3.11+（安装时勾选 Add python.exe to PATH），
        echo 或在命令行用 py -m venv .venv 手动创建后重试。
        pause
        exit /b 1
    )
    echo [PointLog] 正在安装依赖（仅首次需要）……
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)

echo [PointLog] 正在启动…… 浏览器会打开，专注悬浮计时器也会自动出现。
echo [PointLog] 关闭本窗口即可停止服务（计时器不受影响，可单独关闭）。
echo.
".venv\Scripts\python.exe" launcher.py %ARGS%

pause

