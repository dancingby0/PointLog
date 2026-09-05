"""每日感想 API（查 / 保存 / 删除）。"""

import datetime as dt

from flask import Blueprint, jsonify, request

import data
import config
from utils import date_of

bp = Blueprint("notes", __name__, url_prefix="/api")


def _validate_day(day_str: str) -> dt.date | None:
    """校验 YYYY-MM-DD，非法返回 None。"""
    try:
        return dt.datetime.strptime(day_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _require_day() -> dt.date:
    """从 ?day= 取日期；缺省按凌晨4点规则取"今天"。非法返回 None。"""
    day_str = request.args.get("day") or request.args.get("date")
    if day_str:
        return _validate_day(day_str)
    return date_of(dt.datetime.now().astimezone())


@bp.get("/notes")
def get_note():
    """返回某天的感想：?day=YYYY-MM-DD，缺省今天；没有则 note 为 null。"""
    day = _require_day()
    if day is None:
        return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    d = data.load(config.CURRENT_PROFILE)
    note = d["daily_notes"].get(day.isoformat())
    return jsonify({"date": day.isoformat(), "note": note if note else None})


@bp.put("/notes")
def save_note():
    """保存（覆盖）某天的整篇感想。body: {day, content}。"""
    body = request.get_json(silent=True) or {}
    day_str = body.get("day") or request.args.get("day")
    day = _validate_day(day_str) if day_str else date_of(dt.datetime.now().astimezone())
    if day is None:
        return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    content = str(body.get("content", "")).strip()
    if not content:
        return jsonify({"error": "感想不能为空"}), 400

    d = data.load(config.CURRENT_PROFILE)
    d["daily_notes"][day.isoformat()] = content
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"date": day.isoformat(), "note": content})


@bp.delete("/notes")
def delete_note():
    """删除某天的整篇感想：?day=YYYY-MM-DD。"""
    day = _require_day()
    if day is None:
        return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    d = data.load(config.CURRENT_PROFILE)
    iso = day.isoformat()
    if iso not in d["daily_notes"]:
        return jsonify({"error": "该天没有感想"}), 404
    del d["daily_notes"][iso]
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})