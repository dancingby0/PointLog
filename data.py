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

# ---- v2.3 账号层 ----
ACCOUNTS_FILE = "accounts.json"        # data/accounts.json 账号元数据
DEFAULT_ACCOUNT = "我的账号"           # 旧数据迁移目标账号
# 旧布局：data/global.json（资产）与 data/<档案>/（档案）
_LEGACY_GLOBAL_FILE = "global.json"


def validate_profile_name(profile: str) -> None:
    """校验档案名合法性（安全字符、防路径穿越）；非法抛 ValueError。"""
    if not profile:
        raise ValueError("档案名不能为空")
    if any(c in profile for c in '\\/:*?"<>|') or profile in (".", ".."):
        raise ValueError(f"非法档案名: {profile!r}")


def profile_dir(profile: str) -> Path:
    """返回某个档案对应的目录（不存在则创建）。

    有当前账号时 → data/<当前账号>/<档案>/；无账号时 → data/<档案>/（兼容旧布局）。
    """
    validate_profile_name(profile)
    import config
    if config.CURRENT_ACCOUNT:
        d = account_dir(config.CURRENT_ACCOUNT) / profile
    else:
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
    """列出档案（有当前账号 → 账号内档案；无账号 → 根目录旧档案），按名称排序。"""
    import config
    if config.CURRENT_ACCOUNT:
        return account_profile_dirs(config.CURRENT_ACCOUNT)
    if not DATA_DIR.exists():
        return []
    names = [p.name for p in DATA_DIR.iterdir()
             if p.is_dir() and not p.name.startswith(".") and not p.name == "__pycache__"
             and p.name != _LEGACY_GLOBAL_FILE]  # 无账号时排除非档案目录
    return sorted(names)


def settings_path(profile: str) -> Path:
    """档案级设置文件（PIN 等），独立于 data.json，随档案所在层。"""
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


# ---------- 资产数据：账号级（v2.3） ----------
# 有当前账号时存 data/<账号>/assets.json；无当前账号时用旧 data/global.json（兼容/迁移期）。


def global_path() -> Path:
    import config
    if config.CURRENT_ACCOUNT:
        return account_dir(config.CURRENT_ACCOUNT) / "assets.json"
    return DATA_DIR / _LEGACY_GLOBAL_FILE


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
# ---------- v2.3 本地账号层 ----------

def validate_account_name(name: str) -> None:
    """校验账号名合法性（同档案名规则，分隔符等禁止）。"""
    if not name:
        raise ValueError("账号名不能为空")
    if any(c in name for c in '\\/:*?"<>|') or name in (".", ".."):
        raise ValueError(f"非法账号名: {name!r}")


def accounts_path() -> Path:
    return DATA_DIR / ACCOUNTS_FILE


def default_accounts_metadata() -> dict:
    return {"accounts": [], "current": "", "auto_login": False}


def load_accounts_meta() -> dict:
    """读取账号元数据；缺失返回默认 + 触发一次性旧数据迁移。"""
    path = accounts_path()
    if not path.exists():
        meta = default_accounts_metadata()
        _migrate_legacy(meta)   # 首次启动：把旧 v1/v2 数据并入首个账号
        return meta
    try:
        with path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        meta = default_accounts_metadata()
    meta.setdefault("accounts", [])
    meta.setdefault("current", "")
    meta.setdefault("auto_login", False)
    return meta


def save_accounts_meta(meta: dict) -> None:
    path = accounts_path()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def account_dir(name: str) -> Path:
    validate_account_name(name)
    d = DATA_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_accounts() -> list:
    """返回账号列表 [{name, has_pin, auto_login(bool = 当前账号)}]。"""
    meta = load_accounts_meta()
    out = []
    for name in meta["accounts"]:
        out.append({
            "name": name,
            "has_pin": bool(_load_account_settings(name).get("pin_hash")),
            "auto_login": meta.get("auto_login", False) and name == meta.get("current"),
        })
    return out


def _load_account_settings(name: str) -> dict:
    path = account_dir(name) / "settings.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_account_settings(name: str, settings: dict) -> None:
    path = account_dir(name) / "settings.json"
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def create_account(name: str) -> None:
    """新建账号（内置一个默认档案，保证有日记可写）。"""
    validate_account_name(name)
    meta = load_accounts_meta()
    if name in meta["accounts"]:
        raise ValueError("账号已存在")
    account_dir(name)                     # 建目录
    ensure_profile(name, "默认")          # 建默认档案
    meta["accounts"].append(name)
    if not meta.get("current"):
        meta["current"] = name
    save_accounts_meta(meta)


def ensure_profile(account: str, profile: str) -> Path:
    """在账号下建档案目录。"""
    validate_profile_name(profile)
    d = account_dir(account) / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


def account_profile_dirs(account: str) -> list:
    """某账号下的档案名列表。"""
    base = account_dir(account)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and p.name != "assets" and not p.name.startswith("."))


def account_assets_path(account: str) -> Path:
    return account_dir(account) / "assets.json"


def load_account_assets(account: str) -> dict:
    """读取某账号的资产；缺失返回空结构。"""
    path = account_assets_path(account)
    if not path.exists():
        return default_global()   # 复用 default_global 结构
    try:
        with path.open("r", encoding="utf-8") as f:
            g = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_global()
    base = default_global()
    for k in base:
        g.setdefault(k, base[k])
    return g


def save_account_assets(account: str, g: dict) -> None:
    path = account_assets_path(account)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def rename_account(old_name: str, new_name: str) -> None:
    """账号改名：账号目录 + meta 同步。old_name 必须是现有账号。"""
    validate_account_name(new_name)
    if old_name == new_name:
        return
    meta = load_accounts_meta()
    if old_name not in meta["accounts"]:
        raise ValueError("账号不存在")
    if new_name in meta["accounts"]:
        raise ValueError("已存在同名账号")
    src = DATA_DIR / old_name
    dst = DATA_DIR / new_name
    if not src.is_dir():
        raise ValueError("账号目录缺失")
    src.rename(dst)
    meta["accounts"] = [new_name if a == old_name else a for a in meta["accounts"]]
    if meta.get("current") == old_name:
        meta["current"] = new_name
    save_accounts_meta(meta)


def delete_account(name: str) -> None:
    """注销账号：删除账号目录。"""
    validate_account_name(name)
    d = DATA_DIR / name
    if d.is_dir():
        shutil.rmtree(d)


def _migrate_legacy(meta: dict) -> None:
    """旧布局迁移：data/<档案>/* 与 data/global.json → 首个账号（我的账号）。

    仅在没有任何账号数据时执行一次。
    """
    # 已存在账号则跳过
    if meta["accounts"]:
        return
    # 检测旧默认档案或旧 global.json 是否存在于根 data/
    legacy_profiles = [p.name for p in DATA_DIR.iterdir()
                       if p.is_dir() and p.name != DEFAULT_ACCOUNT
                       and not p.name.startswith(".") and p.name != "__pycache__"]
    legacy_global = (DATA_DIR / _LEGACY_GLOBAL_FILE).exists()

    if not legacy_profiles and not legacy_global:
        return

    # 建账号
    account_dir(DEFAULT_ACCOUNT)

    # 迁移档案：旧 data/<档案> → data/<账号>/<档案>
    for p in legacy_profiles:
        src = DATA_DIR / p
        if (DATA_DIR / DEFAULT_ACCOUNT / p).exists():
            continue
        src.rename(DATA_DIR / DEFAULT_ACCOUNT / p)

    # 迁移资产：数据/global.json → data/<账号>/assets.json
    if legacy_global:
        g = (DATA_DIR / _LEGACY_GLOBAL_FILE)
        try:
            with g.open("r", encoding="utf-8") as f:
                data_g = json.load(f)
        except (json.JSONDecodeError, OSError):
            data_g = default_global()
        base = default_global()
        for k in base:
            data_g.setdefault(k, base[k])
        save_account_assets(DEFAULT_ACCOUNT, data_g)
        try:
            g.unlink()
        except OSError:
            pass

    meta["accounts"] = [DEFAULT_ACCOUNT]
    meta["current"] = DEFAULT_ACCOUNT
    save_accounts_meta(meta)