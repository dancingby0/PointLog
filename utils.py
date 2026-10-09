"""通用小工具：时间（凌晨 4 点日期归属规则）与类别文本规范化。"""

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


def day_points_of(entries: list) -> dict:
    """把打卡记录按凌晨4点规则归总为 {date: 点数}。

    - 点数 > 0 的记录才计入（0 点＝单纯记录、不做激励，不算"打卡日"）；
    - 时间不可解析的记录跳过。
    """
    out: dict[dt.date, int] = {}
    for e in entries or []:
        try:
            points = int(e.get("points", 0) or 0)
        except (TypeError, ValueError):
            continue
        if points <= 0:
            continue
        try:
            t = parse_ts(e.get("ts"))
        except (ValueError, TypeError):
            continue
        k = date_of(t)
        out[k] = out.get(k, 0) + points
    return out


def clean_categories(raw) -> list[str]:
    """把"类别"的各种历史写法规范化为字符串列表（多选）。

    - 兼容 v1 单值：`"学习"` → `["学习"]`（老数据不用迁移，读时即转为多选）；
    - 也接受列表 / 元组 / 集合（任何类型元素统一转成字符串）；
    - 去首尾空白、丢掉空串、按首次出现顺序去重；
    - 无类别（None / 空串 / 空列表）→ `[]`。
    """
    if raw is None:
        items: list = []
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        items = [raw]
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out
