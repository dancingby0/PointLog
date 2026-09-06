"""统计 API：坚持与概况汇总（子迭代1）。

GET /api/stats/summary?range=week|month|year|all
返回：打卡天数、期间总点数、当前/最长连续、感想天数。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import stats
from utils import date_of, parse_ts

bp = Blueprint("statistics", __name__, url_prefix="/api/stats")


def _parse_range(name: str, today: dt.date):
    """把 range 名称换算为 [start, end]。"""
    ranges = {
        "week": (today - dt.timedelta(days=6), today),   # 近 7 天
        "month": (today.replace(day=1), today),
        "year": (today.replace(month=1, day=1), today),
        "all": (dt.date(1970, 1, 1), today),
    }
    if name not in ranges:
        raise ValueError("range 应为 week/month/year/all")
    return ranges[name]


def _day_points_of(entries: list) -> dict:
    """把打卡 ts 按凌晨4点规则归到 {date: 点数}。"""
    out = {}
    for e in entries:
        try:
            t = parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        k = date_of(t)
        out[k] = out.get(k, 0) + int(e.get("points", 0))
    return out


@bp.get("/summary")
def summary():
    try:
        range_name = request.args.get("range", "month")
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        start, end = _parse_range(range_name, today)
    except ValueError:
        return jsonify({"error": "range 应为 week/month/year/all"}), 400

    d = data.load(config.CURRENT_PROFILE)
    day_points = _day_points_map_if_present(d)
    in_range = stats.filter_day_points(day_points, start, end)
    summarized = stats.summarize_day_points(in_range)

    # 感想天数：范围内写了感想的天数（YYYY-MM-DD 字典序即时间序，可直接比较字符串）
    notes = d.get("daily_notes", {})
    s_iso, e_iso = start.isoformat(), end.isoformat()
    notes_days = sum(1 for date_str in notes if s_iso <= str(date_str) <= e_iso)

    # 连续天数基于"全部打卡日"（不限定范围，因为 streak 是全局连续性）
    streaks = stats.calc_streaks(set(day_points.keys()))

    return jsonify({
        "range": range_name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_days": summarized["total_days"],
        "period_points": summarized["period_points"],
        "notes_days": notes_days,
        "current_streak": streaks["current_streak"],
        "longest_streak": streaks["longest_streak"],
    })


def _day_points_map_if_present(d: dict) -> dict:
    """统一入口：从档案 entries 汇总 daily {date: points}。"""
    return _day_points_of(d.get("entries", []))