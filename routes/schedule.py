"""每日日常 + 点数规定 API（v2.7，档案级）。

日常只是"今天该干什么 + 建议点数"的清单，**不会自动生成打卡记录**（否则会污染点数线与打卡天数）。

- ``GET  /api/schedule?day=YYYY-MM-DD``  某天的日常 + 当日生效的备忘提醒（默认今天）
- ``GET  /api/routines``                 全部日常项（编辑用，含停用的）
- ``POST /api/routines``                 新增一项
- ``PUT  /api/routines/<id>``            修改一项
- ``DELETE /api/routines/<id>``          删除一项
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import routine
import utils

bp = Blueprint("schedule", __name__, url_prefix="/api")

MAX_ROUTINES = 100


def _today() -> dt.date:
    return utils.date_of(dt.datetime.now().astimezone())


def _load():
    d = data.load(config.CURRENT_PROFILE)
    d.setdefault("routines", [])
    return d


@bp.get("/schedule")
def get_schedule():
    """某天的日常 + 备忘提醒；未指定 day 用今天。"""
    raw_day = request.args.get("day")
    try:
        day = dt.date.fromisoformat(raw_day) if raw_day else _today()
    except ValueError:
        return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400

    d = _load()
    view = routine.day_schedule(d.get("routines") or [], d.get("memos") or [], day, _today())
    return jsonify(view)


@bp.get("/routines")
def list_routines():
    d = _load()
    items = []
    for raw in d["routines"]:
        try:
            items.append(routine.normalize_routine_item(raw))
        except ValueError:
            continue
    items.sort(key=lambda x: (x["start"], x["end"], x["text"]))
    return jsonify({"routines": items})


@bp.post("/routines")
def create_routine():
    d = _load()
    if len(d["routines"]) >= MAX_ROUTINES:
        return jsonify({"error": f"日常最多 {MAX_ROUTINES} 条"}), 400
    try:
        item = routine.normalize_routine_item(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    item["id"] = data.new_id()
    d["routines"].append(item)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(item), 201


@bp.put("/routines/<routine_id>")
def update_routine(routine_id: str):
    d = _load()
    target = next((r for r in d["routines"] if str(r.get("id")) == routine_id), None)
    if target is None:
        return jsonify({"error": "日常不存在"}), 404
    body = request.get_json(silent=True) or {}
    merged = {**target, **body}
    merged["id"] = routine_id
    try:
        item = routine.normalize_routine_item(merged)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    target.update(item)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(item)


@bp.delete("/routines/<routine_id>")
def delete_routine(routine_id: str):
    d = _load()
    before = len(d["routines"])
    d["routines"] = [r for r in d["routines"] if str(r.get("id")) != routine_id]
    if len(d["routines"]) == before:
        return jsonify({"error": "日常不存在"}), 404
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})
