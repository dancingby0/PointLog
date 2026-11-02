"""每日日常 + 点数标准 API（v2.7，档案级，两个独立功能）。

- ``daily_routine``：一段可换行文字 —— 每天大概怎么过（不精确到时段、不绑点数）
- ``point_rules``：另一段可换行文字 —— 什么事算多少点的标准

端点：

- ``GET /api/daily-routine`` / ``PUT``  读写每日日常文本
- ``GET /api/point-rules``  / ``PUT``  读写点数标准文本
- ``GET /api/today-view?day=``        某天要展示的内容（两段文本 + 当天生效的备忘提醒）

两者互不影响：改一个不会动另一个；都只是文本，不产生打卡记录。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import routine
import textblock
import utils

bp = Blueprint("schedule", __name__, url_prefix="/api")

FIELDS = {"daily-routine": "daily_routine", "point-rules": "point_rules"}


def _today() -> dt.date:
    return utils.date_of(dt.datetime.now().astimezone())


def _payload(field: str, text: str) -> dict:
    stats = textblock.text_stats(text)
    return {"text": text, "lines": stats["lines"], "chars": stats["chars"],
            "empty": stats["empty"]}


def _read(field: str):
    d = data.load(config.CURRENT_PROFILE)
    return _payload(FIELDS[field], textblock.normalize_text(d.get(FIELDS[field])))


def _write(field: str):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or "text" not in body:
        return jsonify({"error": "请求体应为 {text: 多行文本}"}), 400
    text = textblock.normalize_text(body.get("text"))
    d = data.load(config.CURRENT_PROFILE)
    d[FIELDS[field]] = text
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(_payload(field, text))


@bp.get("/daily-routine")
def get_daily_routine():
    return jsonify(_read("daily-routine"))


@bp.put("/daily-routine")
def put_daily_routine():
    return _write("daily-routine")


@bp.get("/point-rules")
def get_point_rules():
    return jsonify(_read("point-rules"))


@bp.put("/point-rules")
def put_point_rules():
    return _write("point-rules")


@bp.get("/today-view")
def today_view():
    """某天要展示的内容：每日日常 + 点数标准 + 当天生效的备忘提醒（默认今天）。"""
    raw_day = request.args.get("day")
    try:
        day = dt.date.fromisoformat(raw_day) if raw_day else _today()
    except ValueError:
        return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400

    d = data.load(config.CURRENT_PROFILE)
    today = _today()
    reminders = routine.day_reminders(d.get("memos") or [], day, today)
    return jsonify({
        "day": day.isoformat(),
        "weekday": day.weekday(),
        "weekday_label": routine.WEEKDAY_LABELS[day.weekday()],
        "daily_routine": _payload("daily-routine",
                                  textblock.normalize_text(d.get("daily_routine"))),
        "point_rules": _payload("point-rules",
                                textblock.normalize_text(d.get("point_rules"))),
        "reminders": reminders,
    })
