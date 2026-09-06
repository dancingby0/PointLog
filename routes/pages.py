"""页面路由。

页面本身由前端工程（frontend/）经 Vite 构建到 static/dist/ 后，由本路由托管。
开发前端时请先执行 npm run build（或 npm run dev 配合代理）。
"""

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory

bp = Blueprint("pages", __name__)

DIST_DIR = "dist"


@bp.get("/")
def index():
    dist_path = Path(current_app.static_folder) / DIST_DIR / "index.html"
    if not dist_path.exists():
        return (
            "前端尚未构建：请在 frontend/ 目录执行 <code>npm install && npm run build</code> 后刷新。",
            503,
        )
    return send_from_directory(current_app.static_folder, f"{DIST_DIR}/index.html")
