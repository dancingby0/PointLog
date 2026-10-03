"""导出落盘 / 下载的公共工具（资产导出、打卡导出共用）。

约定（与 v2.1 资产导出一致）：
- 默认把导出内容写入 `config.EXPORTS_DIR`（项目根 `exports/`，已加入 .gitignore），
  返回落盘元信息（含 `rel_path`，供前端展示路径），不产生浏览器下载；
- 显式 `download=1/true/yes` 时才返回 JSON 附件（下载到浏览器，不在服务端落盘）。

文件操作采用"原子写"：先写 `.tmp` 再替换，避免中断留下半个文件。
"""

import os
from pathlib import Path
from urllib.parse import quote

from flask import Response

import config

# 视为"要求下载"的 download 参数值
DOWNLOAD_VALUES = ("1", "true", "yes")


def download_requested(args) -> bool:
    """查询参数 download 是否为真（1/true/yes，大小写不敏感）。"""
    return (args.get("download") or "").strip().lower() in DOWNLOAD_VALUES


def unique_path(directory: Path, filename: str) -> Path:
    """导出文件名去重：同名已存在时追加 -2/-3…（避免同一秒内多次导出互相覆盖）。"""
    path = directory / filename
    if not path.exists():
        return path
    i = 2
    while True:
        cand = directory / f"{path.stem}-{i}{path.suffix}"
        if not cand.exists():
            return cand
        i += 1


def write_text_atomic(path: Path, text: str) -> None:
    """原子写：先写 .tmp 再替换，避免中断留下半个文件。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def rel_to_root(path: Path) -> str:
    """相对项目根的展示路径（用 / 分隔，跨平台一致）。"""
    root = Path(__file__).resolve().parent
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def save_text(filename: str, text: str) -> dict:
    """把导出内容写入导出目录，返回落盘元信息（ok/filename/dir/rel_path/abs_path/bytes）。"""
    out_dir = Path(config.EXPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(out_dir, filename)
    write_text_atomic(target, text)
    return {
        "ok": True,
        "filename": target.name,
        "dir": str(out_dir),
        "rel_path": rel_to_root(target),
        "abs_path": str(target),
        "bytes": target.stat().st_size,
    }


def attachment(filename: str, text: str) -> Response:
    """以 JSON 附件返回（filename* 支持中文/特殊字符）。"""
    resp = Response(text, mimetype="application/json")
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return resp
