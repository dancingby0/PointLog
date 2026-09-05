"""打卡记录 API（增 / 删 / 查 / 改）。"""

import datetime as dt

from flask import Blueprint, jsonify, request

import data
import config
from utils import date_of, day_bounds, parse_ts

bp = Blueprint("entries", __name__, url_prefix="/api")


@bp.get("/entries")
def list_entries():
    """返回某天的记录与点数；?day=YYYY-MM-DD，缺省为"今天"（凌晨4点界）。"""
    d = data.load(config.CURRENT_PROFILE)
    day_str = request.args.get("day")
    if day_str:
        try:
            day = dt.datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    else:
        day = date_of(dt.datetime.now().astimezone())
    start, end = day_bounds(day)

    entries = []
    for e in d["entries"]:
        try:
            t = parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        if start <= t < end:
            entries.append(e)
    total = sum(int(e.get("points", 0)) for e in entries)
    return jsonify({
        "entries": sorted(entries, key=lambda e: e["ts"], reverse=True),
        "day_points": total,
    })


@bp.post("/entries")
def create_entry():
    body = request.get_json(silent=True) or {}
    content = str(body.get("content", "")).strip()
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    try:
        points = int(body.get("points", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "点数必须是整数"}), 400
    if points < 0:
        return jsonify({"error": "点数不能为负"}), 400

    ts_str = body.get("ts")
    try:
        ts_iso = ts_str if ts_str else dt.datetime.now().astimezone().isoformat()
        parse_ts(ts_iso)  # 校验格式
    except (ValueError, TypeError):
        return jsonify({"error": "时间格式不正确"}), 400

    entry = {
        "id": data.new_id(),
        "ts": ts_iso,
        "points": points,
        "content": content,
        "category": (str(body.get("category") or "")).strip() or None,
    }
    d = data.load(config.CURRENT_PROFILE)
    d["entries"].append(entry)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(entry), 201


@bp.delete("/entries/<entry_id>")
def delete_entry(entry_id: str):
    d = data.load(config.CURRENT_PROFILE)
    before = len(d["entries"])
    d["entries"] = [e for e in d["entries"] if e.get("id") != entry_id]
    if len(d["entries"]) == before:
        return jsonify({"error": "记录不存在"}), 404
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})


@bp.put("/entries/<entry_id>")
def update_entry(entry_id: str):
    d = data.load(config.CURRENT_PROFILE)
    entry = next((e for e in d["entries"] if e.get("id") == entry_id), None)
    if entry is None:
        return jsonify({"error": "记录不存在"}), 404

    body = request.get_json(silent=True) or {}

    if "content" in body:
        content = str(body.get("content", "")).strip()
        if not content:
            return jsonify({"error": "内容不能为空"}), 400
        entry["content"] = content

    if "points" in body:
        try:
            points = int(body.get("points"))
        except (TypeError, ValueError):
            return jsonify({"error": "点数必须是整数"}), 400
        if points < 0:
            return jsonify({"error": "点数不能为负"}), 400
        entry["points"] = points

    if "category" in body:
        entry["category"] = str(body.get("category") or "").strip() or None

    if "ts" in body:
        try:
            parse_ts(body.get("ts"))
        except (ValueError, TypeError):
            return jsonify({"error": "时间格式不正确"}), 400
        entry["ts"] = body["ts"]

    data.save(config.CURRENT_PROFILE, d)
    return jsonify(entry)