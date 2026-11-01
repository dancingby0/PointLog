"""每日日常 + 备忘录时间匹配（纯函数：无 Flask、无文件读写，可独立测试）。

两个概念（都挂在档案上，属于"今天该干什么"的参考，不产生打卡记录）：

1. **日常（routine）**：时段 + 内容 + 建议点数，可指定星期（空＝每天）。用于「点数规定」——
   例如「08:00–09:00 晨读 2 点」「每天 刷牙 1 点」。只在界面上展示，**不会自动生成打卡**，
   否则会污染点数线与连续天数。

2. **备忘提醒**：备忘录可带一个"什么时候相关"的时间范围，粒度到天：
   - ``none``      不设定（纯备忘，不进日常）
   - ``daily``     每天
   - ``dates``     绝对日期段，可多段（如 10-08~10-09、10-11~10-12）
   - ``monthdays`` 每月几号到几号，可多段（如 8-9、11-12）
   某天的日常里，凡是"这天生效"的备忘会被自动插入提醒；结束日已过＝过期，界面标红但**不删除**。

时间范围一律用**闭区间**（含首尾两天），与导出的 from/to 语义一致。
"""

import datetime as dt

MODES = ("none", "daily", "dates", "monthdays")
WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")


def _parse_date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# ---------- 备忘录时间范围 ----------

def normalize_schedule(raw) -> dict:
    """把各种历史/手写写法规范化为 {mode, ranges, monthdays}（不合法部分丢弃）。"""
    data = raw if isinstance(raw, dict) else {}
    mode = str(data.get("mode") or "none").strip()
    if mode not in MODES:
        mode = "none"
    ranges, monthdays = [], []
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
    if mode == "dates" and not ranges:
        mode = "none"
    if mode == "monthdays" and not monthdays:
        mode = "none"
    return {"mode": mode, "ranges": ranges, "monthdays": monthdays}


def memo_active_on(schedule: dict, day: dt.date) -> bool:
    """这条备忘在 day 这天是否生效（mode=none 永远不生效）。"""
    sch = normalize_schedule(schedule)
    if sch["mode"] == "daily":
        return True
    if sch["mode"] == "dates":
        return any(_parse_date(r["from"]) <= day <= _parse_date(r["to"]) for r in sch["ranges"])
    if sch["mode"] == "monthdays":
        return any(r["from"] <= day.day <= r["to"] for r in sch["monthdays"])
    return False


def memo_end(schedule: dict):
    """这条备忘最后一次生效的日期（daily / monthdays 无终点 → None）。"""
    sch = normalize_schedule(schedule)
    if sch["mode"] == "dates":
        ends = [_parse_date(r["to"]) for r in sch["ranges"]]
        return max([e for e in ends if e], default=None)
    return None


def memo_expired(schedule: dict, today: dt.date) -> bool:
    """过期＝已过最后生效日（daily / monthdays 会循环，不算过期）。"""
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
    return "不设定"


# ---------- 日常 ----------

def _parse_hhmm(value):
    """'HH:MM' → time；兼容 '8:00' / '0800' / '8' 等写法。不合法返回 None。"""
    text = str(value or "").strip().replace("：", ":")
    if not text:
        return None
    if ":" in text:
        head, _, tail = text.partition(":")
        try:
            return dt.time(int(head) % 24, int(tail or 0) % 60)
        except ValueError:
            return None
    if text.isdigit():
        if len(text) <= 2:
            return dt.time(int(text) % 24, 0)
        return dt.time(int(text[:-2]) % 24, int(text[-2:]) % 60)
    return None


def normalize_routine_item(raw) -> dict:
    """规范化一条日常：时段 / 内容 / 建议点数 / 适用星期。非法抛 ValueError。"""
    if not isinstance(raw, dict):
        raise ValueError("日常项应为对象")
    text = str(raw.get("text") or "").strip()
    if not text:
        raise ValueError("日常内容不能为空")
    if len(text) > 60:
        raise ValueError("日常内容过长（最多 60 字）")
    start = _parse_hhmm(raw.get("start"))
    end = _parse_hhmm(raw.get("end"))
    if start is None or end is None:
        raise ValueError("时段格式应为 HH:MM（如 08:00）")
    if end <= start:
        raise ValueError("结束时间应晚于开始时间")
    try:
        points = float(raw.get("points") or 0)
    except (TypeError, ValueError):
        raise ValueError("建议点数应为数字")
    if points < 0:
        raise ValueError("建议点数不能为负")
    days = []
    for value in raw.get("days") or []:
        try:
            wd = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= wd <= 6 and wd not in days:
            days.append(wd)
    return {
        "id": str(raw.get("id") or ""),
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "text": text,
        "points": int(points) if points == int(points) else round(points, 1),
        "days": sorted(days),         # 空 = 每天
        "enabled": bool(raw.get("enabled", True)),
        "note": str(raw.get("note") or "").strip()[:120],
    }


def routine_for_day(routines: list, day: dt.date) -> list:
    """某天生效的日常（按开始时间升序）；days 为空的项＝每天生效。"""
    weekday = day.weekday()
    out = []
    for item in routines or []:
        try:
            norm = normalize_routine_item(item)
        except ValueError:
            continue                   # 坏数据不拖垮整页
        if not norm["enabled"]:
            continue
        if norm["days"] and weekday not in norm["days"]:
            continue
        out.append(norm)
    out.sort(key=lambda x: (x["start"], x["end"], x["text"]))
    return out


def day_schedule(routines: list, memos: list, day: dt.date, today: dt.date) -> dict:
    """某天的「日常 + 备忘提醒」合并视图（供 /api/schedule 与前端使用）。"""
    items = routine_for_day(routines, day)
    reminders = []
    for memo in memos or []:
        if not isinstance(memo, dict):
            continue
        sch = normalize_schedule(memo.get("schedule"))
        if not memo_active_on(sch, day):
            continue
        reminders.append({
            "id": str(memo.get("id") or ""),
            "text": str(memo.get("text") or ""),
            "schedule": sch,
            "when": schedule_text(sch),
            "expired": memo_expired(sch, today),
        })
    reminders.sort(key=lambda m: (m["expired"], m["text"]))   # 未过期在前，过期的集中到末尾
    return {
        "day": day.isoformat(),
        "weekday": day.weekday(),
        "weekday_label": WEEKDAY_LABELS[day.weekday()],
        "items": items,
        "reminders": reminders,
        "planned_points": round(sum(float(i["points"]) for i in items), 1),
    }

