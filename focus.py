"""专注会话（计时器）的纯逻辑：无 Flask、无文件读写，可独立测试。

数据模型（一个会话 = 一次"专注"）：

    {
      "id": "1793000000000",
      "label": "学习日语",                 # 标签（可空）
      "state": "running" | "paused" | "stopped",
      "segments": [{"start": iso, "end": iso|null}],   # 分段累计，running 时最后一段 end=null
      "points": 1,                        # 上传成打卡时用的点数
      "entry_id": null,                   # 已上传生成的打卡记录 id（幂等键）
      "created_at": iso, "uploaded_at": null
    }

为什么用 segments 而不是累计秒数：暂停/继续可以精确回放，按天切分也只需切区间。
总时长 = 各段时长之和（running 的最后一段算到"现在"）。

归属日与打卡一致：按凌晨 4 点划分，跨 4:00 的会话会被切到两天。
"""

import datetime as dt

import utils

MAX_SEGMENT_SEC = 24 * 3600      # 单段上限：防止忘关计时器后出现离谱时长
MAX_TOTAL_SEC = 12 * 3600        # 单会话总上限（12 小时），超出部分截断


def normalize_session(raw) -> dict | None:
    """规范化一条会话；结构不可恢复返回 None（坏数据不拖垮统计）。"""
    if not isinstance(raw, dict):
        return None
    state = str(raw.get("state") or "stopped").strip()
    if state not in ("running", "paused", "stopped"):
        state = "stopped"
    segments = []
    for seg in raw.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        try:
            start = utils.parse_ts(seg.get("start"))
        except (ValueError, TypeError):
            continue
        try:
            end = utils.parse_ts(seg["end"]) if seg.get("end") else None
        except (ValueError, TypeError):
            end = None
        if end and end < start:
            continue                     # 结束早于开始的脏数据丢弃；end == start（同一秒）保留
        segments.append({"start": start.isoformat(timespec="seconds"),
                         "end": end.isoformat(timespec="seconds") if end else None})
    if not segments:
        return None
    segments.sort(key=lambda s: s["start"])
    try:
        points = float(raw.get("points") if raw.get("points") is not None else 1)
    except (TypeError, ValueError):
        points = 1.0
    points = max(0.0, points)
    return {
        "id": str(raw.get("id") or ""),
        "label": str(raw.get("label") or "").strip()[:40],
        "state": state,
        "segments": segments,
        "points": int(points) if points == int(points) else round(points, 1),
        "entry_id": str(raw["entry_id"]) if raw.get("entry_id") else None,
        "created_at": str(raw.get("created_at") or segments[0]["start"]),
        "uploaded_at": raw.get("uploaded_at"),
    }


def open_segment(session: dict) -> bool:
    """是否存在"还开着"的段（running 状态应有且仅一条）。"""
    return bool(session.get("segments")) and session["segments"][-1].get("end") is None


def start_session(label: str = "", points=1, now: dt.datetime | None = None,
                  new_id: str = "") -> dict:
    """新建一个 running 会话。"""
    now = now or dt.datetime.now().astimezone()
    return normalize_session({
        "id": new_id or str(int(now.timestamp() * 1000)),
        "label": label,
        "state": "running",
        "segments": [{"start": now.isoformat(timespec="seconds"), "end": None}],
        "points": points,
        "created_at": now.isoformat(timespec="seconds"),
    })


def pause(session: dict, now: dt.datetime | None = None) -> dict:
    """暂停：把最后一段的 end 补上。已暂停/已结束则原样返回。"""
    now = now or dt.datetime.now().astimezone()
    sess = normalize_session(session)
    if not sess or sess["state"] != "running" or not open_segment(sess):
        return sess
    sess["segments"][-1]["end"] = now.isoformat(timespec="seconds")
    sess["state"] = "paused"
    return sess


def resume(session: dict, now: dt.datetime | None = None) -> dict:
    """继续：开一个新段。非 paused 状态原样返回。"""
    now = now or dt.datetime.now().astimezone()
    sess = normalize_session(session)
    if not sess or sess["state"] != "paused":
        return sess
    sess["segments"].append({"start": now.isoformat(timespec="seconds"), "end": None})
    sess["state"] = "running"
    return sess


def stop(session: dict, now: dt.datetime | None = None) -> dict:
    """结束：关掉还开着的段并置为 stopped（幂等）。"""
    now = now or dt.datetime.now().astimezone()
    sess = normalize_session(session)
    if not sess:
        return sess
    if open_segment(sess):
        sess["segments"][-1]["end"] = now.isoformat(timespec="seconds")
    sess["state"] = "stopped"
    return sess



def segments_of(session: dict, now: dt.datetime | None = None) -> list:
    """把 segments 展开成 (start, end) 列表；running 的最后一段算到 now，并做单段截断。"""
    now = now or dt.datetime.now().astimezone()
    out = []
    for seg in (session or {}).get("segments") or []:
        try:
            start = utils.parse_ts(seg.get("start"))
        except (ValueError, TypeError):
            continue
        end = utils.parse_ts(seg["end"]) if seg.get("end") else now
        if end <= start:
            continue
        if (end - start).total_seconds() > MAX_SEGMENT_SEC:
            end = start + dt.timedelta(seconds=MAX_SEGMENT_SEC)
        out.append((start, end))
    return out


def total_sec(session: dict, now: dt.datetime | None = None) -> float:
    """会话总时长（秒），封顶 MAX_TOTAL_SEC。"""
    total = sum((e - s).total_seconds() for s, e in segments_of(session, now))
    return min(total, MAX_TOTAL_SEC)


def split_by_day(session: dict, now: dt.datetime | None = None) -> list:
    """按凌晨 4 点规则把会话时长切到各天：[(date, seconds), ...]，升序。"""
    buckets: dict[dt.date, float] = {}
    for start, end in segments_of(session, now):
        cursor = start
        while cursor < end:
            day = utils.date_of(cursor)
            _, day_end = utils.day_bounds(day)
            piece_end = min(end, day_end)
            buckets[day] = buckets.get(day, 0.0) + (piece_end - cursor).total_seconds()
            cursor = piece_end
    return sorted(buckets.items())


def fmt_duration(seconds: float) -> str:
    """秒 → "1h23m" / "45m" / "0m"。"""
    total = int(round(seconds / 60.0))
    if total <= 0:
        return "0m"
    h, m = divmod(total, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def build_entry(session: dict, now: dt.datetime | None = None,
                points=None, label: str = "") -> dict | None:
    """把会话转成一条打卡记录（用于上传到点数系统）。

    - 归属时间取最后一段的结束时刻（按凌晨 4 点规则落到正确的一天）；
    - start_ts 由结束时刻回推实际专注时长，避免把暂停时间算进时长；
    - category 用标签，content 写"专注 1h23m · 学习日语"。
    """
    now = now or dt.datetime.now().astimezone()
    segs = segments_of(session, now)
    if not segs:
        return None
    label = (label or (session or {}).get("label") or "").strip()
    duration = total_sec(session, now)
    if duration < 60:
        return None                     # 不足 1 分钟不生成记录
    end = segs[-1][1]
    start = end - dt.timedelta(seconds=duration)
    used_points = (session or {}).get("points", 1) if points is None else points
    text = f"专注 {fmt_duration(duration)}" + (f" · {label}" if label else "")
    return {
        "content": text[:120],
        "points": used_points,
        "category": [label] if label else [],
        "ts": end.isoformat(timespec="seconds"),
        "start_ts": start.isoformat(timespec="seconds"),
        "end_ts": end.isoformat(timespec="seconds"),
    }


def aggregate(sessions: list, today: dt.date, now: dt.datetime | None = None) -> dict:
    """统计：今日 / 累计时长、累计天数、按标签分布、当前运行中的会话。"""
    now = now or dt.datetime.now().astimezone()
    total_sum = 0.0
    days: set = set()
    by_label: dict[str, float] = {}
    by_day: dict[dt.date, float] = {}
    running = None

    for raw in sessions or []:
        sess = normalize_session(raw)
        if not sess:
            continue
        secs = total_sec(sess, now)
        if secs <= 0:
            continue
        total_sum += secs
        label = sess["label"] or "未命名"
        by_label[label] = by_label.get(label, 0.0) + secs
        for day, part in split_by_day(sess, now):
            by_day[day] = by_day.get(day, 0.0) + part
            days.add(day)
        if sess["state"] == "running":
            running = sess

    today_sec = by_day.get(today, 0.0)
    return {
        "today_min": round(today_sec / 60.0, 1),
        "total_min": round(total_sum / 60.0, 1),
        "today_text": fmt_duration(today_sec),
        "total_text": fmt_duration(total_sum),
        "days": len(days),
        "sessions": len([s for s in (sessions or []) if normalize_session(s)]),
        "by_label": [{"label": k, "min": round(v / 60.0, 1), "text": fmt_duration(v)}
                     for k, v in sorted(by_label.items(), key=lambda kv: kv[1], reverse=True)],
        "by_day": [{"day": d.isoformat(), "min": round(v / 60.0, 1)}
                   for d, v in sorted(by_day.items())],
        "running": ({"id": running["id"], "label": running["label"],
                     "started_at": running["segments"][0]["start"],
                     "elapsed_sec": int(total_sec(running, now)),
                     "elapsed_text": fmt_duration(total_sec(running, now))}
                    if running else None),
    }
