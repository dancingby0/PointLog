"""本地档案 API（v2.3：档案锁已取消，档案 PIN 不再启用）。

账号锁是唯一总锁（见 routes/accounts.py）。档案切换/改名/删除不再校验 PIN。
"""

from flask import Blueprint, jsonify, request

import config
import data

bp = Blueprint("profiles", __name__, url_prefix="/api")


@bp.get("/profiles")
def list_profiles():
    """返回当前账号下的档案列表 + 当前档案。"""
    names = data.list_profiles()
    if not names:
        names = ["默认"]
    profiles = [{"name": n} for n in names]
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
    return jsonify({"name": name}), 201


@bp.post("/profiles/switch")
def switch_profile():
    """切换当前档案。"""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if name not in data.list_profiles():
        return jsonify({"error": "档案不存在"}), 404
    config.CURRENT_PROFILE = name
    return jsonify({"current": name})


@bp.put("/profiles/rename")
def rename_profile_api():
    """重命名当前档案。"""
    body = request.get_json(silent=True) or {}
    new_name = str(body.get("name", "")).strip()
    if not new_name:
        return jsonify({"error": "新档案名不能为空"}), 400
    old_name = config.CURRENT_PROFILE
    try:
        data.rename_profile(old_name, new_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    config.CURRENT_PROFILE = new_name
    return jsonify({"current": new_name})


@bp.delete("/profiles/<name>")
def delete_profile_api(name: str):
    """删除指定档案。不允许删除最后一个档案。"""
    profiles = data.list_profiles()
    if name not in profiles:
        return jsonify({"error": "档案不存在"}), 404
    if len(profiles) <= 1:
        return jsonify({"error": "至少保留一个档案"}), 400

    data.delete_profile(name)
    # 若删除的是当前档案，切到第一个剩余档案
    if config.CURRENT_PROFILE == name:
        remaining = [p for p in data.list_profiles() if p != name]
        config.CURRENT_PROFILE = remaining[0]
    return jsonify({"ok": True, "current": config.CURRENT_PROFILE})


# ---- 兼容空壳：旧档案 PIN 端点（v2.3 已废弃，不再有 UI 调用）----

@bp.post("/unlock")
def unlock():
    """（废弃）档案解锁——档案锁已取消，恒返回 ok。"""
    return jsonify({"ok": True})


@bp.put("/pin")
def set_pin():
    """（废弃）档案 PIN——已取消，恒返回未设锁。"""
    return jsonify({"has_pin": False})