"""日期总览与贡献日历 API。"""

import datetime as dt

from flask import Blueprint, jsonify, request

import data
from config import CURRENT_PROFILE
from utils import date_of, parse_ts

bp = Blueprint("days", __name__, url_prefix="/api")


def _level_of(points: int) -> int:
    """把每日点数映射为贡献强度等级（0~4，GitHub 风格，简化分档）。"""
    if points <= 0:
        return 0
    if points == 1:
        return 1
    if points <= 3:
        return 2
    if points <= 5:
        return 3
    return 4


def _day_points_map(d: dict) -> dict:
    """把档案里的打卡记录归总为 {date: 总点数}。"""
    day_points = {}
    for e in d["entries"]:
        try:
            t = parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        k = date_of(t)
        day_points[k] = day_points.get(k, 0) + int(e.get("points", 0))
    return day_points


@bp.get("/days")
def list_days():
    """返回最近 N 天（默认 14）的 {date, points, is_today}，从新到旧；供日期切换器使用。"""
    d = data.load(CURRENT_PROFILE)
    n = request.args.get("days", default=14, type=int)
    n = max(1, min(n, 90))
    now = dt.datetime.now().astimezone()
    today = date_of(now)

    day_points = _day_points_map(d)

    days = []
    for i in range(n):
        day = today - dt.timedelta(days=i)
        days.append({
            "date": day.isoformat(),
            "points": day_points.get(day, 0),
            "is_today": i == 0,
        })
    return jsonify(days)


@bp.get("/calendar")
def calendar():
    """贡献日历：返回最近 N 天（默认 365）的 {date, points, level}，从最旧到最新。"""
    d = data.load(CURRENT_PROFILE)
    n = request.args.get("days", default=365, type=int)
    n = max(7, min(n, 3650))
    now = dt.datetime.now().astimezone()
    today = date_of(now)

    day_points = _day_points_map(d)

    out = []
    for i in range(n - 1, -1, -1):
        day = today - dt.timedelta(days=i)
        points = day_points.get(day, 0)
        out.append({
            "date": day.isoformat(),
            "points": points,
            "level": _level_of(points),
        })
    return jsonify(out)