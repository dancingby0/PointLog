"""通用时间工具：凌晨 4 点日期归属规则相关的计算。"""

import datetime as dt


def parse_ts(s: str) -> dt.datetime:
    """解析 ISO 时间；无时区视为本地时区。"""
    if not s:
        raise ValueError("缺少时间")
    value = s
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """某"天"的边界：以凌晨 4 点为界，即 [day 04:00, day+1 04:00)。"""
    start = dt.datetime.combine(day, dt.time(4, 0, 0)).astimezone()
    end = start + dt.timedelta(days=1)
    return start, end


def date_of(t: dt.datetime) -> dt.date:
    """按凌晨4点规则，某时刻属于哪一天 = 时间减去4小时后取日历日。

    例：2026-09-06 02:00 → 减去4h → 2026-09-05 22:00 → 归属 2026-09-05。
    """
    return (t - dt.timedelta(hours=4)).date()