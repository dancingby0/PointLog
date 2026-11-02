"""启动器：一键启动本地服务、自动打开浏览器，并（可选）拉起桌面专注计时器。

由 start.bat 调用；也可手动运行：

    .venv\\Scripts\\python launcher.py             # 服务 + 浏览器 + 悬浮计时器
    .venv\\Scripts\\python launcher.py --no-timer  # 只起服务（旧行为）

计时器是纯标准库 tkinter 小工具（focus_timer.py），以独立进程运行：
它退出或崩溃都不影响本服务，反之亦然；服务未就绪时不会强行拉起它。
"""

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import app as app_module

PORT = 5000
URL = f"http://127.0.0.1:{PORT}/"

ROOT = Path(__file__).resolve().parent
DIST_HTML = ROOT / "static" / "dist" / "index.html"
FRONTEND_DIR = ROOT / "frontend"
TIMER_SCRIPT = ROOT / "focus_timer.py"


def _ensure_frontend_built() -> None:
    """若前端构建产物缺失且源码工程在，则自动执行 npm run build。"""
    if DIST_HTML.exists():
        return
    if not (FRONTEND_DIR / "package.json").exists():
        print("[提示] 未找到前端构建产物与源码工程，将仅启动后端 API。")
        return
    print("[PointLog] 检测到前端尚未构建，正在自动构建（首次需稍候）……")
    try:
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True, capture_output=True)
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True, capture_output=True)
        print("[PointLog] 前端构建完成。")
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 自动构建失败（{exc}）。")
        print("        可在 frontend/ 目录手动执行: npm install && npm run build")


def _port_ready(timeout: float = 15.0) -> bool:
    """轮询等待端口可连接（比固定 sleep 稳，慢机器也不怕）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                return True
        time.sleep(0.2)
    return False


def _open_browser() -> None:
    """服务就绪后自动打开浏览器。"""
    if _port_ready():
        webbrowser.open(URL)


def _start_timer() -> None:
    """服务就绪后再拉起悬浮计时器（此刻自动登录已完成，档案已确定）。"""
    if not TIMER_SCRIPT.exists():
        print("[提示] 未找到 focus_timer.py，跳过专注计时器。")
        return
    if not _port_ready():
        print("[提示] 服务未就绪，跳过专注计时器（可稍后双击 start_focus.bat）。")
        return
    cmd = [sys.executable, str(TIMER_SCRIPT)]
    try:
        if os.name == "nt":
            # 独立进程组：关掉本窗口不会带走计时器；pythonw 启动则无控制台
            subprocess.Popen(cmd, cwd=str(ROOT),
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True)
        print("[PointLog] 专注计时器已启动（悬浮窗可拖动，Esc 关闭）。")
    except OSError as exc:
        print(f"[警告] 专注计时器启动失败（{exc}）。可手动运行: python focus_timer.py")


if __name__ == "__main__":
    start_timer = "--no-timer" not in sys.argv
    _ensure_frontend_built()
    print(f"PointLog 正在启动…… {URL}（关闭本窗口即停止服务）")
    if start_timer:
        threading.Thread(target=_start_timer, daemon=True).start()
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        # debug=False：避免调试重载器派生子进程 / 重复开浏览器
        app_module.app.run(host="127.0.0.1", port=PORT, debug=False)
    except OSError:
        print(f"\n启动失败：端口 {PORT} 可能已被占用。")
        print("请先关闭已运行的 PointLog 窗口，或检查是否已有程序占用该端口。")
        input("\n按回车键退出……")
