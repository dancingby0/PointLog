"""本地账号 API：新建/登录/登出/注销/自动登录 + 账号 PIN。

账号是 v2.3 顶层；档案与资产挂账号下，账号间完全隔离。
账号锁为唯一总锁；解锁后 10 分钟（服务进程内存）免输账号 PIN。
"""

import time

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import config
import data

bp = Blueprint("accounts", __name__, url_prefix="/api/auth")

PIN_MIN_LEN = 4
PIN_MAX_LEN = 8
UNLOCK_WINDOW_SEC = 10 * 60  # 10 分钟免输窗口


def _validate_pin(pin: str):
    if not pin.isdigit():
        return "PIN 只能包含数字"
    if not (PIN_MIN_LEN <= len(pin) <= PIN_MAX_LEN):
        return f"PIN 长度需为 {PIN_MIN_LEN}~{PIN_MAX_LEN} 位"
    return None


def _has_account_pin(name: str) -> bool:
    return bool(data._load_account_settings(name).get("pin_hash"))


def _is_unlocked(name: str) -> bool:
    """该账号是否处于免输窗口内（窗口记所属账号，登出/切号不影响）。"""
    return config.UNLOCKED_ACCOUNT == name and time.time() < config.UNLOCKED_UNTIL


def ensure_auto_login() -> str:
    """服务启动后首次需要账号时补做自动登录（幂等）。

    为什么需要：自动登录原先只在 ``GET /api/auth``（浏览器打开页面）时才触发。
    但桌面计时器 / 导入脚本等客户端可能**先于浏览器**发请求，那时 CURRENT_ACCOUNT 为空、
    CURRENT_PROFILE 还是 "default"，数据就会写进 default 档案。这里把同一套判断抽出来，
    任何入口在拿不到当前账号时都可以调用它（不改变"用户主动登出后不再自动登录"的语义）。

    返回自动登录后的账号名（未登录返回空串）。
    """
    if config.CURRENT_ACCOUNT or config.AUTO_LOGIN_SUPPRESSED:
        return config.CURRENT_ACCOUNT
    meta = data.load_accounts_meta()
    remembered = meta.get("current")
    if not (meta.get("auto_login") and remembered and remembered in meta.get("accounts", [])):
        return ""
    # 有 PIN 的账号：仅当处于免输窗口内才自动登录
    if _has_account_pin(remembered) and not _is_unlocked(remembered):
        return ""
    config.CURRENT_ACCOUNT = remembered
    profs = data.account_profile_dirs(remembered)
    config.CURRENT_PROFILE = profs[0] if profs else "default"
    return config.CURRENT_ACCOUNT


@bp.get("")
def list_accounts_api():
    """账号列表 + 当前选中 + 自动登录标记。

    若进程内未登录，但开启自动登录且记忆账号无 PIN，则自动登录进入该账号。
    记忆账号有 PIN 时不做自动登录（前端会引导输入 PIN）。
    """
    meta = data.load_accounts_meta()
    ensure_auto_login()

    accounts = data.list_accounts()
    unlocked = config.UNLOCKED_ACCOUNT if time.time() < config.UNLOCKED_UNTIL else ""
    return jsonify({
        "accounts": accounts,
        "current": meta.get("current", ""),
        "auto_login": meta.get("auto_login", False),
        "logged_in": config.CURRENT_ACCOUNT,
        "unlocked": unlocked,  # 免输窗口内账号（空串 = 无）
    })


@bp.post("")
def create_account_api():
    """新建账号（可设账号 PIN）。body {name, pin?}。"""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    try:
        data.validate_account_name(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        data.create_account(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    pin = str(body.get("pin", ""))
    if pin:
        err = _validate_pin(pin)
        if err:
            return jsonify({"error": err}), 400
        s = data._load_account_settings(name)
        s["pin_hash"] = generate_password_hash(pin)
        data.save_account_settings(name, s)

    # 创建后自动登录进入（账号记忆为 current）
    config.CURRENT_ACCOUNT = name
    config.CURRENT_PROFILE = "默认"
    meta = data.load_accounts_meta()
    meta["current"] = name
    data.save_accounts_meta(meta)

    return jsonify({"name": name, "has_pin": _has_account_pin(name)}), 201


@bp.post("/login")
def login_account_api():
    """登录/进入账号：body {name, pin?}。

    账号有 PIN 时需要 PIN，除非当前账号正处于免输窗口。
    登录成功后刷新免输窗口（now + 10min，进程内存）。
    """
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", ""))
    meta = data.load_accounts_meta()
    if name not in meta["accounts"]:
        return jsonify({"error": "账号不存在"}), 404

    if _has_account_pin(name) and not _is_unlocked(name):
        pin = str(body.get("pin", ""))
        ph = data._load_account_settings(name).get("pin_hash")
        if not check_password_hash(ph, pin):
            return jsonify({"error": "PIN 不正确"}), 401

    config.CURRENT_ACCOUNT = name
    config.UNLOCKED_ACCOUNT = name
    config.UNLOCKED_UNTIL = time.time() + UNLOCK_WINDOW_SEC
    meta["current"] = name
    data.save_accounts_meta(meta)

    # 默认进入该账号首档案
    profs = data.account_profile_dirs(name)
    config.CURRENT_PROFILE = profs[0] if profs else "default"
    return jsonify({"account": name, "profile": config.CURRENT_PROFILE})


@bp.post("/logout")
def logout_account_api():
    """登出：清当前账号/档案，回到账号选择页。

    自动登录只在服务刚启动时触发；本次进程内主动登出后不再自动登录
    （否则开了自动登录会"登出即被拉回"）。免输窗口保留，窗口内重进免输。
    """
    config.CURRENT_ACCOUNT = ""
    config.CURRENT_PROFILE = "default"
    config.AUTO_LOGIN_SUPPRESSED = True
    return jsonify({"ok": True})


@bp.post("/set-auto-login")
def set_auto_login():
    """设置自动登录：body {enabled: bool}。开启时记到当前账号。"""
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", False))
    meta = data.load_accounts_meta()
    meta["auto_login"] = enabled
    if enabled and config.CURRENT_ACCOUNT:
        meta["current"] = config.CURRENT_ACCOUNT
    data.save_accounts_meta(meta)
    return jsonify({"auto_login": enabled, "current": meta.get("current", "")})


@bp.post("/lock")
def lock_account_api():
    """主动/闲置锁定：结束会话并清空免输窗口，须重新输账号 PIN 才可进入。

    返回锁定的账号名与其是否设 PIN，供前端直接显示解锁界面。
    """
    if not config.CURRENT_ACCOUNT:
        return jsonify({"error": "未登录"}), 401
    name = config.CURRENT_ACCOUNT
    has_pin = _has_account_pin(name)
    config.CURRENT_ACCOUNT = ""
    config.CURRENT_PROFILE = "default"
    config.UNLOCKED_ACCOUNT = ""   # 立即终止免输窗口 → 解锁必须输 PIN
    config.UNLOCKED_UNTIL = 0.0
    config.AUTO_LOGIN_SUPPRESSED = True
    return jsonify({"account": name, "has_pin": has_pin})


@bp.put("/rename")
def rename_account_api():
    """当前账号改名。body {name, pin?}；设了 PIN 的账号需验证 PIN。

    目录随之重命名（档案/资产跟随），免输窗口与当前会话同步到新名。
    """
    if not config.CURRENT_ACCOUNT:
        return jsonify({"error": "未登录"}), 401
    body = request.get_json(silent=True) or {}
    new_name = str(body.get("name", "")).strip()
    old_name = config.CURRENT_ACCOUNT
    if old_name == new_name:
        return jsonify({"account": old_name})
    try:
        data.validate_account_name(new_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    meta = data.load_accounts_meta()
    if new_name in meta["accounts"]:
        return jsonify({"error": "已存在同名账号"}), 400
    if _has_account_pin(old_name):
        pin = str(body.get("pin", ""))
        ph = data._load_account_settings(old_name).get("pin_hash")
        if not check_password_hash(ph, pin):
            return jsonify({"error": "PIN 不正确"}), 401

    try:
        data.rename_account(old_name, new_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    config.CURRENT_ACCOUNT = new_name
    if config.UNLOCKED_ACCOUNT == old_name:  # 免输窗口跟随新名
        config.UNLOCKED_ACCOUNT = new_name
    return jsonify({"account": new_name})


@bp.put("/pin")
def set_account_pin():
    """当前账号设置/清除 PIN。body {pin}（空串清除）。"""
    if not config.CURRENT_ACCOUNT:
        return jsonify({"error": "未登录"}), 401
    body = request.get_json(silent=True) or {}
    pin = str(body.get("pin", ""))
    s = data._load_account_settings(config.CURRENT_ACCOUNT)
    if pin:
        err = _validate_pin(pin)
        if err:
            return jsonify({"error": err}), 400
        s["pin_hash"] = generate_password_hash(pin)
    else:
        s.pop("pin_hash", None)
    data.save_account_settings(config.CURRENT_ACCOUNT, s)
    return jsonify({"has_pin": bool(s.get("pin_hash"))})


@bp.delete("/<name>")
def delete_account_api(name: str):
    """注销账号：删整个账号目录（需账号 PIN + 前端防误触确认）。"""
    meta = data.load_accounts_meta()
    if name not in meta["accounts"]:
        return jsonify({"error": "账号不存在"}), 404
    if len(meta["accounts"]) <= 1:
        return jsonify({"error": "至少保留一个账号"}), 400
    if _has_account_pin(name):
        body = request.get_json(silent=True) or {}
        pin = str(body.get("pin", ""))
        ph = data._load_account_settings(name).get("pin_hash")
        if not check_password_hash(ph, pin):
            return jsonify({"error": "PIN 不正确"}), 401

    data.delete_account(name)
    meta["accounts"] = [a for a in meta["accounts"] if a != name]
    if meta.get("current") == name:
        meta["current"] = meta["accounts"][0]
    data.save_accounts_meta(meta)
    if config.CURRENT_ACCOUNT == name:
        config.CURRENT_ACCOUNT = ""
    if config.UNLOCKED_ACCOUNT == name:  # 账号已删除，清其免输窗口
        config.UNLOCKED_ACCOUNT = ""
        config.UNLOCKED_UNTIL = 0.0
    if meta.get("auto_login"):
        # 注销后停在账号选择页，不自动登入剩余账号
        config.AUTO_LOGIN_SUPPRESSED = True
    return jsonify({"ok": True})