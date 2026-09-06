"""启动器：一键启动本地服务并自动打开浏览器。

由 start.bat 调用；也可手动运行：.venv\\Scripts\\python launcher.py
"""

import subprocess
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


def _open_browser():
    """稍等服务器就绪后自动打开浏览器。"""
    time.sleep(1.5)
    webbrowser.open(URL)


if __name__ == "__main__":
    _ensure_frontend_built()
    print(f"PointLog 正在启动…… {URL}（关闭本窗口即停止服务）")
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        # debug=False：避免调试重载器派生子进程 / 重复开浏览器
        app_module.app.run(host="127.0.0.1", port=PORT, debug=False)
    except OSError:
        print(f"\n启动失败：端口 {PORT} 可能已被占用。")
        print("请先关闭已运行的 PointLog 窗口，或检查是否已有程序占用该端口。")
        input("\n按回车键退出……")
