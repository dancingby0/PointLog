"""PointLog 数据读写层：管理 data/<档案>/data.json。

v1 约定：
- 每个档案一个文件夹，含一个 data.json，包含 entries / daily_notes / memos 三块。
- 文件操作采用"原子写"：先写临时文件再替换，避免中途断电损坏数据。
"""

import json
import os
import time
from pathlib import Path

# data/<档案名>/data.json
DATA_DIR = Path(__file__).resolve().parent / "data"


def default_data() -> dict:
    """返回一份全新的数据结构。"""
    return {
        "entries": [],       # 打卡记录
        "daily_notes": {},   # 每日感想：{ "YYYY-MM-DD": "文本" }，一天一篇
        "memos": [],         # 备忘录：[{ "id": str, "text": str }]
        "main_goal": "",     # 置顶主目标（v1 仅展示用）
    }


def profile_dir(profile: str) -> Path:
    """返回某个档案对应的目录（不存在则创建）。"""
    # 档案名仅允许安全字符，防止路径穿越
    if not profile or any(c in profile for c in '\\/:*?"<>|') or profile in (".", ".."):
        raise ValueError(f"非法档案名: {profile!r}")
    d = DATA_DIR / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_profiles() -> list[str]:
    """列出 data/ 下的档案名（按名称排序）。"""
    if not DATA_DIR.exists():
        return []
    names = [p.name for p in DATA_DIR.iterdir()
             if p.is_dir() and not p.name.startswith(".") and not p.name == "__pycache__"]
    return sorted(names)


def settings_path(profile: str) -> Path:
    """档案级设置文件（PIN 等），独立于 data.json。"""
    return profile_dir(profile) / "settings.json"


def load_settings(profile: str) -> dict:
    """读取档案设置；不存在或损坏时返回空 dict。"""
    path = settings_path(profile)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(profile: str, settings: dict) -> None:
    """原子写 settings.json（复用临时文件替换策略）。"""
    path = settings_path(profile)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def data_path(profile: str) -> Path:
    return profile_dir(profile) / "data.json"


def load(profile: str) -> dict:
    """读取档案数据；文件不存在或损坏时，返回空结构（损坏时备份原文件）。"""
    path = data_path(profile)
    if not path.exists():
        return default_data()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        backup = path.with_suffix(".json.bak")
        try:
            path.replace(backup)  # 别覆盖已有备份
        except OSError:
            pass
        return default_data()
    # 容错：缺字段补默认
    base = default_data()
    for key in base:
        data.setdefault(key, base[key])
    # 迁移：早期版本的 daily_notes 是数组占位，现改为 {日期: 文本} 字典
    if not isinstance(data["daily_notes"], dict):
        data["daily_notes"] = {}
    return data


def save(profile: str, data: dict) -> None:
    """原子写：先写 data.json.tmp，再替换 data.json。"""
    path = data_path(profile)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def new_id() -> str:
    """生成记录 ID：毫秒时间戳（本机单用户足够唯一）。"""
    return str(int(time.time() * 1000))