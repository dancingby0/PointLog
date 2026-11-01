"""备忘录 + 置顶主目标 API。

备忘录可选时间范围（v2.7）：``schedule`` 字段，见 routine.normalize_schedule：
- mode=none 不设定 / daily 每天 / dates 绝对日期段（可多段）/ monthdays 每月几号到几号（可多段）
过期（已过最后生效日）只在界面上标红，**不会自动删除**。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import routine
import utils

bp = Blueprint("memos", __name__, url_prefix="/api")


def _decorate(memo: dict, today: dt.date) -> dict:
    """给备忘补上可读的时间描述与过期标记（不改磁盘数据）。"""
    item = dict(memo)
    sch = routine.normalize_schedule(item.get("schedule"))
    item["schedule"] = sch
    item["when"] = routine.schedule_text(sch)
    item["expired"] = routine.memo_expired(sch, today)
    return item


def _clean_memo(body: dict, memo_id: str | None = None) -> dict:
    """校验并规范化备忘内容；非法抛 ValueError。"""
    text = str(body.get("text", "")).strip()
    if not text:
        raise ValueError("内容不能为空")
    if len(text) > 200:
        raise ValueError("内容过长（最多200字）")
    return {
        "id": memo_id or data.new_id(),
        "text": text,
        "schedule": routine.normalize_schedule(body.get("schedule")),
    }


@bp.get("/memos")
def list_memos():
    """返回全部备忘 + 当前主目标（备忘附带可读的时间描述与过期标记）。"""
    d = data.load(config.CURRENT_PROFILE)
    today = utils.date_of(dt.datetime.now().astimezone())
    return jsonify({
        "memos": [_decorate(m, today) for m in d["memos"]],
        "main_goal": d.get("main_goal", ""),
    })


@bp.post("/memos")
def create_memo():
    try:
        memo = _clean_memo(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    d = data.load(config.CURRENT_PROFILE)
    d["memos"].append(memo)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(memo), 201


@bp.put("/memos/<memo_id>")
def update_memo(memo_id: str):
    """修改备忘内容与时间范围（只改传了的字段）。"""
    d = data.load(config.CURRENT_PROFILE)
    target = next((m for m in d["memos"] if m.get("id") == memo_id), None)
    if target is None:
        return jsonify({"error": "备忘不存在"}), 404
    body = request.get_json(silent=True) or {}
    merged = {"text": body.get("text", target.get("text", "")),
              "schedule": body["schedule"] if "schedule" in body
              else target.get("schedule")}
    try:
        updated = _clean_memo(merged, memo_id=memo_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    target.update(updated)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(updated)


@bp.delete("/memos/<memo_id>")
def delete_memo(memo_id: str):
    d = data.load(config.CURRENT_PROFILE)
    before = len(d["memos"])
    d["memos"] = [m for m in d["memos"] if m.get("id") != memo_id]
    if len(d["memos"]) == before:
        return jsonify({"error": "备忘不存在"}), 404
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})


@bp.put("/main-goal")
def update_main_goal():
    """设置/修改主目标；传空字符串表示清除。"""
    body = request.get_json(silent=True) or {}
    goal = str(body.get("goal", "")).strip()
    if len(goal) > 100:
        return jsonify({"error": "主目标过长（最多100字）"}), 400
    d = data.load(config.CURRENT_PROFILE)
    d["main_goal"] = goal
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"main_goal": goal})
