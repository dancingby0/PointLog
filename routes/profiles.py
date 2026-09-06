"""本地档案 + PIN 锁 API。

说明：这是"防君子不防小人"的便捷级防护（需求定位）；PIN 哈希存储，
真正想读磁盘文件的人无法被 UI 阻止。
"""

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import config
import data

bp = Blueprint("profiles", __name__, url_prefix="/api")

# PIN 规则
PIN_MIN_LEN = 4
PIN_MAX_LEN = 8


def _has_pin(profile: str) -> bool:
    return bool(data.load_settings(profile).get("pin_hash"))


def _validate_pin(pin: str):
    if not pin.isdigit():
        return "PIN 只能包含数字"
    if not (PIN_MIN_LEN <= len(pin) <= PIN_MAX_LEN):
        return f"PIN 长度需为 {PIN_MIN_LEN}~{PIN_MAX_LEN} 位"
    return None


@bp.get("/profiles")
def list_profiles():
    """返回全部档案（含是否设 PIN）+ 当前档案。"""
    names = data.list_profiles()
    # 保证至少存在一个档案（默认 default 也在其列）
    if not names:
        names = ["default"]
    profiles = [{"name": n, "has_pin": _has_pin(n)} for n in names]
    return jsonify({"profiles": profiles, "current": config.CURRENT_PROFILE})


@bp.post("/profiles")
def create_profile():
    """新建档案（空档案，立即切换过去）。"""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    try:
        data.profile_dir(name)  # 顺带校验名字合法性
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data.save(name, data.default_data())  # 生成 data.json
    return jsonify({"name": name, "has_pin": False}), 201


@bp.post("/profiles/switch")
def switch_profile():
    """切换当前档案；若目标档案设了 PIN 需先解锁。"""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if name not in data.list_profiles():
        return jsonify({"error": "档案不存在"}), 404

    if _has_pin(name):
        pin = str(body.get("pin", ""))
        ph = data.load_settings(name).get("pin_hash")
        if not check_password_hash(ph, pin):
            return jsonify({"error": "PIN 不正确"}), 401

    config.CURRENT_PROFILE = name
    return jsonify({"current": name, "has_pin": _has_pin(name)})


@bp.post("/unlock")
def unlock():
    """解锁当前档案（锁屏用）。"""
    body = request.get_json(silent=True) or {}
    pin = str(body.get("pin", ""))
    ph = data.load_settings(config.CURRENT_PROFILE).get("pin_hash")
    if not ph:  # 没设 PIN 的档案无需解锁
        return jsonify({"ok": True})
    if not check_password_hash(ph, pin):
        return jsonify({"error": "PIN 不正确"}), 401
    return jsonify({"ok": True})


@bp.put("/pin")
def set_pin():
    """为当前档案设置 PIN（传空串则清除）。返回当前状态。"""
    body = request.get_json(silent=True) or {}
    pin = str(body.get("pin", ""))

    settings = data.load_settings(config.CURRENT_PROFILE)
    if pin:
        err = _validate_pin(pin)
        if err:
            return jsonify({"error": err}), 400
        settings["pin_hash"] = generate_password_hash(pin)
    else:
        settings.pop("pin_hash", None)
    data.save_settings(config.CURRENT_PROFILE, settings)
    return jsonify({"has_pin": bool(settings.get("pin_hash"))})


def _require_pin(profile: str) -> tuple[bool, str]:
    """校验目标档案 PIN（若设置了 PIN）。返回 (是否通过, 错误信息)。"""
    if not _has_pin(profile):
        return True, ""
    body = request.get_json(silent=True) or {}
    pin = str(body.get("pin", ""))
    ph = data.load_settings(profile).get("pin_hash")
    if not check_password_hash(ph, pin):
        return False, "PIN 不正确"
    return True, ""


@bp.put("/profiles/rename")
def rename_profile_api():
    """重命名当前档案：body {name, pin}。改名后当前档案跟随新名。"""
    body = request.get_json(silent=True) or {}
    new_name = str(body.get("name", "")).strip()
    if not new_name:
        return jsonify({"error": "新档案名不能为空"}), 400

    ok, err = _require_pin(config.CURRENT_PROFILE)
    if not ok:
        return jsonify({"error": err}), 401

    old_name = config.CURRENT_PROFILE
    try:
        data.rename_profile(old_name, new_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    config.CURRENT_PROFILE = new_name
    return jsonify({"current": new_name, "has_pin": _has_pin(new_name)})


@bp.delete("/profiles/<name>")
def delete_profile_api(name: str):
    """删除指定档案：需 PIN 确认。不允许删除最后一个档案。"""
    profiles = data.list_profiles()
    if name not in profiles:
        return jsonify({"error": "档案不存在"}), 404
    if len(profiles) <= 1:
        return jsonify({"error": "至少保留一个档案"}), 400

    ok, err = _require_pin(name)
    if not ok:
        return jsonify({"error": err}), 401

    data.delete_profile(name)
    # 若删除的是当前档案，切到第一个剩余档案
    if config.CURRENT_PROFILE == name:
        remaining = [p for p in data.list_profiles() if p != name]
        config.CURRENT_PROFILE = remaining[0]
    return jsonify({"ok": True, "current": config.CURRENT_PROFILE})