"""日期总览与贡献日历 API。"""

import datetime as dt

from flask import Blueprint, jsonify, request

import data
import stats
import config
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
    d = data.load(config.CURRENT_PROFILE)
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


@bp.get("/line")
def points_line():
    """点数线：最近至多 60 天（凌晨4点界）内的每日点数做剔极值 40% 分位数。

    返回计算过程，便于前端展示与校验。
    """
    d = data.load(config.CURRENT_PROFILE)
    now = dt.datetime.now().astimezone()
    today = date_of(now)

    window_days = 60
    start_day = today - dt.timedelta(days=window_days - 1)
    day_points = _day_points_map(d)

    # 只取窗口内的每日点数（含 0）
    points_in_window = []
    for i in range(window_days):
        day = start_day + dt.timedelta(days=i)
        points_in_window.append(day_points.get(day, 0))

    result = stats.calc_baseline(points_in_window)
    return jsonify(result)


@bp.get("/calendar")
def calendar():
    """贡献日历：返回指定年份的每日数据，从 1月1日 到 min(12月31日, 今天)。

    ?year=YYYY（默认今年）。
    - 当年：显示 1月1日 → 今天（不显示未来）
    - 历史年：显示该年完整 1月1日 → 12月31日
    """
    d = data.load(config.CURRENT_PROFILE)
    now = dt.datetime.now().astimezone()
    today = date_of(now)

    year_str = request.args.get("year")
    if year_str:
        try:
            year = int(year_str)
        except ValueError:
            return jsonify({"error": "year 应为四位年份"}), 400
        if year > today.year or year < 1970:
            return jsonify({"error": "year 超出合理范围"}), 400
    else:
        year = today.year

    start = dt.date(year, 1, 1)
    end = min(dt.date(year, 12, 31), today)

    day_points = _day_points_map(d)

    out = []
    day = start
    while day <= end:
        points = day_points.get(day, 0)
        out.append({
            "date": day.isoformat(),
            "points": points,
            "level": _level_of(points),
        })
        day += dt.timedelta(days=1)
    return jsonify(out)