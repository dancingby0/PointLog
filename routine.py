"""备忘时间范围匹配（纯函数：无 Flask、无文件读写，可独立测试）。

备忘可带一个"什么时候相关"的时间范围，粒度到天：

- ``none``      不设定（纯备忘，不进每日日常）
- ``daily``     每天
- ``weekdays``  每周周几（可多选，如每周六、周日）
- ``dates``     绝对日期段，可多段（如 10-08~10-09、10-11~10-12）
- ``monthdays`` 每月几号到几号，可多段（如 8-9、11-12）

某天的每日日常里，凡是"这天生效"的备忘会被自动列出来提醒；结束日已过＝过期，界面标红但**不删除**。

时间范围一律用**闭区间**（含首尾两天），与导出的 from/to 语义一致。
``weekdays`` 用 0-6 表示周一至周日（与 ``date.weekday()`` 一致）。
"""

import datetime as dt

MODES = ("none", "daily", "dates", "monthdays", "weekdays")
WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")


def _parse_date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def normalize_schedule(raw) -> dict:
    """把各种历史/手写写法规范化为 {mode, ranges, monthdays, weekdays}（不合法部分丢弃）。"""
    data = raw if isinstance(raw, dict) else {}
    mode = str(data.get("mode") or "none").strip()
    if mode not in MODES:
        mode = "none"
    ranges, monthdays, weekdays = [], [], []
    for item in data.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        start = _parse_date(item.get("from"))
        end = _parse_date(item.get("to")) or start
        if start and end:
            if end < start:                  # 起止写反 → 交换，别丢用户输入
                start, end = end, start
            ranges.append({"from": start.isoformat(), "to": end.isoformat()})
    for item in data.get("monthdays") or []:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item.get("from"))
            end = int(item.get("to") or start)
        except (TypeError, ValueError):
            continue
        if not (1 <= start <= 31):
            continue
        end = min(max(end, 1), 31)
        if end < start:
            start, end = end, start
        monthdays.append({"from": start, "to": end})
    for item in data.get("weekdays") or []:
        try:
            wd = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= wd <= 6 and wd not in weekdays:
            weekdays.append(wd)
    weekdays.sort()
    if mode == "dates" and not ranges:
        mode = "none"
    if mode == "monthdays" and not monthdays:
        mode = "none"
    if mode == "weekdays" and not weekdays:
        mode = "none"
    return {"mode": mode, "ranges": ranges, "monthdays": monthdays, "weekdays": weekdays}


def memo_active_on(schedule: dict, day: dt.date) -> bool:
    """这条备忘在 day 这天是否生效（mode=none 永远不生效）。"""
    sch = normalize_schedule(schedule)
    if sch["mode"] == "daily":
        return True
    if sch["mode"] == "dates":
        return any(_parse_date(r["from"]) <= day <= _parse_date(r["to"]) for r in sch["ranges"])
    if sch["mode"] == "monthdays":
        return any(r["from"] <= day.day <= r["to"] for r in sch["monthdays"])
    if sch["mode"] == "weekdays":
        return day.weekday() in sch["weekdays"]
    return False


def memo_end(schedule: dict):
    """这条备忘最后一次生效的日期（daily / monthdays / weekdays 会循环 → None）。"""
    sch = normalize_schedule(schedule)
    if sch["mode"] == "dates":
        ends = [_parse_date(r["to"]) for r in sch["ranges"]]
        return max([e for e in ends if e], default=None)
    return None


def memo_expired(schedule: dict, today: dt.date) -> bool:
    """过期＝已过最后生效日（daily / monthdays / weekdays 会循环，不算过期）。"""
    end = memo_end(schedule)
    return bool(end and today > end)


def schedule_text(schedule: dict) -> str:
    """人类可读的时间范围描述（界面与导出共用）。"""
    sch = normalize_schedule(schedule)
    if sch["mode"] == "daily":
        return "每天"
    if sch["mode"] == "dates":
        return "、".join(f"{r['from']}~{r['to']}" if r["from"] != r["to"] else r["from"]
                         for r in sch["ranges"])
    if sch["mode"] == "monthdays":
        return "每月 " + "、".join(
            f"{r['from']}–{r['to']} 号" if r["from"] != r["to"] else f"{r['from']} 号"
            for r in sch["monthdays"])
    if sch["mode"] == "weekdays":
        names = [WEEKDAY_LABELS[d] for d in sch["weekdays"]]
        if len(names) == 7:
            return "每天"
        return "每周" + "、".join(names)
    return "不设定"


def day_reminders(memos: list, day: dt.date, today: dt.date) -> list:
    """某天生效的备忘提醒（未过期在前，过期的排末尾）。"""
    out = []
    for memo in memos or []:
        if not isinstance(memo, dict):
            continue
        sch = normalize_schedule(memo.get("schedule"))
        if not memo_active_on(sch, day):
            continue
        out.append({
            "id": str(memo.get("id") or ""),
            "text": str(memo.get("text") or ""),
            "schedule": sch,
            "when": schedule_text(sch),
            "expired": memo_expired(sch, today),
        })
    out.sort(key=lambda m: (m["expired"], m["text"]))
    return out
