"""PointLog 数据读写层：管理 data/<档案>/data.json。

v1 约定：
- 每个档案一个文件夹，含一个 data.json，包含 entries / daily_notes / memos 三块。
- 文件操作采用"原子写"：先写临时文件再替换，避免中途断电损坏数据。
"""

import json
import os
import shutil
import time
from pathlib import Path

# data/<档案名>/data.json
DATA_DIR = Path(__file__).resolve().parent / "data"


def validate_profile_name(profile: str) -> None:
    """校验档案名合法性（安全字符、防路径穿越）；非法抛 ValueError。"""
    if not profile:
        raise ValueError("档案名不能为空")
    if any(c in profile for c in '\\/:*?"<>|') or profile in (".", ".."):
        raise ValueError(f"非法档案名: {profile!r}")


def profile_dir(profile: str) -> Path:
    """返回某个档案对应的目录（不存在则创建）。"""
    validate_profile_name(profile)
    d = DATA_DIR / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


def rename_profile(old: str, new: str) -> None:
    """重命名档案目录。若新名已存在抛 ValueError。"""
    validate_profile_name(old)
    validate_profile_name(new)
    old_dir = DATA_DIR / old
    new_dir = DATA_DIR / new
    if not old_dir.is_dir():
        raise ValueError(f"档案不存在: {old!r}")
    if new_dir.exists():
        raise ValueError(f"档案已存在: {new!r}")
    old_dir.rename(new_dir)


def delete_profile(profile: str) -> None:
    """删除档案（整个目录含所有数据）。"""
    validate_profile_name(profile)
    d = DATA_DIR / profile
    if not d.is_dir():
        raise ValueError(f"档案不存在: {profile!r}")
    shutil.rmtree(d)


def default_data() -> dict:
    """返回一份全新的数据结构。"""
    return {
        "entries": [],       # 打卡记录
        "daily_notes": {},   # 每日感想：{ "YYYY-MM-DD": "文本" }，一天一篇
        "memos": [],         # 备忘录：[{ "id": str, "text": str }]
        "main_goal": "",     # 置顶主目标（v1 仅展示用）
        "diary_tags": [],    # 日记标签池（档案级）：快捷填词库，存文本
    }


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


# ---------- 个人级（全局共享）数据：data/global.json ----------
# 与档案隔离的"个人级"存储：资产标签池、账户、收支等（不属于任何档案，切换档案不影响）。


def global_path() -> Path:
    return DATA_DIR / "global.json"


def default_global() -> dict:
    """个人级数据结构。"""
    return {
        "asset_tags": [],   # 资产标签池（个人级）：收支/平台等快捷词
        "accounts": [],     # 账户（v2.1 启用）：[{id, name, balance, kind}]
        "txs": [],          # 收支/转账流水（v2.1 启用）
    }


def load_global() -> dict:
    """读取个人级数据；不存在或损坏时返回空结构（损坏时备份原文件）。"""
    path = global_path()
    if not path.exists():
        return default_global()
    try:
        with path.open("r", encoding="utf-8") as f:
            g = json.load(f)
    except (json.JSONDecodeError, OSError):
        backup = path.with_suffix(".json.bak")
        try:
            path.replace(backup)
        except OSError:
            pass
        return default_global()
    base = default_global()
    for key in base:
        g.setdefault(key, base[key])
    return g


def save_global(g: dict) -> None:
    """原子写 data/global.json。"""
    path = global_path()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)