@echo off
rem PointLog 专注计时器（桌面悬浮窗）
rem 一般不需要单独运行：start.bat 会自动拉起它。
rem 如果服务已经在跑，想再开/重开一个悬浮窗，双击本文件即可。
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" focus_timer.py %*
) else (
  start "" pythonw focus_timer.py %*
)
endlocal

