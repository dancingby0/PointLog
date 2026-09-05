"""启动器：一键启动本地服务并自动打开浏览器。

由 start.bat 调用；也可手动运行：.venv\\Scripts\\python launcher.py
"""

import threading
import time
import webbrowser

import app as app_module

PORT = 5000
URL = f"http://127.0.0.1:{PORT}/"


def _open_browser():
    """稍等服务器就绪后自动打开浏览器。"""
    time.sleep(1.5)
    webbrowser.open(URL)


if __name__ == "__main__":
    print(f"PointLog 正在启动…… {URL}（关闭本窗口即停止服务）")
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        # debug=False：避免调试重载器派生子进程 / 重复开浏览器
        app_module.app.run(host="127.0.0.1", port=PORT, debug=False)
    except OSError:
        print(f"\n启动失败：端口 {PORT} 可能已被占用。")
        print("请先关闭已运行的 PointLog 窗口，或检查是否已有程序占用该端口。")
        input("\n按回车键退出……")
