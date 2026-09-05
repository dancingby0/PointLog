"""备忘录 + 置顶主目标 API。"""

from flask import Blueprint, jsonify, request

import data
from config import CURRENT_PROFILE

bp = Blueprint("memos", __name__, url_prefix="/api")


@bp.get("/memos")
def list_memos():
    """返回全部备忘 + 当前主目标。"""
    d = data.load(CURRENT_PROFILE)
    return jsonify({
        "memos": d["memos"],
        "main_goal": d.get("main_goal", ""),
    })


@bp.post("/memos")
def create_memo():
    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    if not text:
        return jsonify({"error": "内容不能为空"}), 400
    if len(text) > 200:
        return jsonify({"error": "内容过长（最多200字）"}), 400

    memo = {"id": data.new_id(), "text": text}
    d = data.load(CURRENT_PROFILE)
    d["memos"].append(memo)
    data.save(CURRENT_PROFILE, d)
    return jsonify(memo), 201


@bp.delete("/memos/<memo_id>")
def delete_memo(memo_id: str):
    d = data.load(CURRENT_PROFILE)
    before = len(d["memos"])
    d["memos"] = [m for m in d["memos"] if m.get("id") != memo_id]
    if len(d["memos"]) == before:
        return jsonify({"error": "备忘不存在"}), 404
    data.save(CURRENT_PROFILE, d)
    return jsonify({"ok": True})


@bp.put("/main-goal")
def update_main_goal():
    """设置/修改主目标；传空字符串表示清除。"""
    body = request.get_json(silent=True) or {}
    goal = str(body.get("goal", "")).strip()
    if len(goal) > 100:
        return jsonify({"error": "主目标过长（最多100字）"}), 400
    d = data.load(CURRENT_PROFILE)
    d["main_goal"] = goal
    data.save(CURRENT_PROFILE, d)
    return jsonify({"main_goal": goal})