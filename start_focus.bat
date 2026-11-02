@echo off
REM PointLog 专注计时器（桌面悬浮窗）
REM 首次使用：直接双击即可；服务需先在跑（start.bat 或 .venv\Scripts\python app.py）
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" focus_timer.py %*
) else (
  start "" pythonw focus_timer.py %*
)
endlocal
