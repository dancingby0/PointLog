"""打卡记录 API（增 / 删 / 查 / 改 / 导出）。

时间机制（v2.4）：
- `ts` 是记录的内部归属时刻（按凌晨 4 点规则决定属于哪一天），由后端/前端自动给出，
  界面不再让用户填写；
- `start_ts` / `end_ts` 是**可选的时段**（从 xx 起到 xx 结束）：两端要么都填、要么都留空，
  都填时按 `end - start` 派生 `duration_min`（消耗时长，分钟）；
- 留空 = 本条不记时长（仍按点数计入当天）；点数允许 0（单纯记录、不做激励）。
"""

import datetime as dt
import json

from flask import Blueprint, jsonify, request

import config
import data
import export_io
from utils import date_of, day_bounds, parse_ts

bp = Blueprint("entries", __name__, url_prefix="/api")


def _clean_span_value(value):
    """校验并规范化可选时段端点：空 → None；非法格式抛 ValueError。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    parse_ts(str(value))
    return str(value)


def _resolve_span(body: dict, current: dict | None = None):
    """解析并校验 start_ts / end_ts（支持局部更新；缺省沿用 current）。

    规则：两端要么都填、要么都留空；都填时结束必须晚于开始。
    """
    current = current or {}
    if "start_ts" in body:
        start = _clean_span_value(body.get("start_ts"))
    else:
        start = _clean_span_value(current.get("start_ts"))
    if "end_ts" in body:
        end = _clean_span_value(body.get("end_ts"))
    else:
        end = _clean_span_value(current.get("end_ts"))
    if (start is None) != (end is None):
        raise ValueError("开始与结束时间要同时填写，或都留空")
    if start and end and parse_ts(end) <= parse_ts(start):
        raise ValueError("结束时间要晚于开始时间")
    return start, end


def _duration_min(start, end):
    """时段消耗时长（分钟，四舍五入到整分）；无时段返回 None。"""
    if not start or not end:
        return None
    try:
        delta = parse_ts(end) - parse_ts(start)
    except (ValueError, TypeError):
        return None
    return int(round(delta.total_seconds() / 60))


def _serialize(e: dict) -> dict:
    """输出给前端的记录：补全可选时段字段并派生消耗时长。"""
    out = dict(e)
    start = e.get("start_ts")
    end = e.get("end_ts")
    out["start_ts"] = start
    out["end_ts"] = end
    out["duration_min"] = _duration_min(start, end)
    return out


def _ts_key(e: dict):
    """排序键：归属时刻（时间戳）+ 记录 id；时间不可解析的排最前。"""
    try:
        return (parse_ts(e.get("ts")).timestamp(), str(e.get("id") or ""))
    except (ValueError, TypeError):
        return (float("-inf"), str(e.get("id") or ""))


@bp.get("/entries")
def list_entries():
    """返回某天的记录与点数；?day=YYYY-MM-DD，缺省为"今天"（凌晨4点界）。

    每条记录附带 `duration_min`：填了时段则为消耗时长（分钟），未填为 null。
    """
    d = data.load(config.CURRENT_PROFILE)
    day_str = request.args.get("day")
    if day_str:
        try:
            day = dt.datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    else:
        day = date_of(dt.datetime.now().astimezone())
    start, end = day_bounds(day)

    entries = []
    for e in d.get("entries", []):
        try:
            t = parse_ts(e.get("ts"))
        except (ValueError, TypeError):
            continue
        if start <= t < end:
            entries.append(_serialize(e))
    total = sum(int(e.get("points", 0) or 0) for e in entries)
    entries.sort(key=_ts_key, reverse=True)          # 时间降序（新→旧）
    return jsonify({"entries": entries, "day_points": total})


@bp.post("/entries")
def create_entry():
    body = request.get_json(silent=True) or {}
    content = str(body.get("content", "")).strip()
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    try:
        points = int(body.get("points", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "点数必须是整数"}), 400
    if points < 0:
        return jsonify({"error": "点数不能为负"}), 400

    # 归属时刻（内部用，决定属于哪一天）；不传则由后端取当前时刻
    ts_str = body.get("ts")
    try:
        ts_iso = str(ts_str) if ts_str else dt.datetime.now().astimezone().isoformat()
        parse_ts(ts_iso)  # 校验格式
    except (ValueError, TypeError):
        return jsonify({"error": "时间格式不正确"}), 400

    # 可选时段：从 xx 起到 xx 结束
    try:
        start_ts, end_ts = _resolve_span(body)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc) or "时段格式不正确"}), 400

    entry = {
        "id": data.new_id(),
        "ts": ts_iso,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "points": points,
        "content": content,
        "category": (str(body.get("category") or "")).strip() or None,
    }
    d = data.load(config.CURRENT_PROFILE)
    d["entries"].append(entry)
    data.save(config.CURRENT_PROFILE, d)
    return jsonify(_serialize(entry)), 201


@bp.delete("/entries/<entry_id>")
def delete_entry(entry_id: str):
    d = data.load(config.CURRENT_PROFILE)
    before = len(d["entries"])
    d["entries"] = [e for e in d["entries"] if e.get("id") != entry_id]
    if len(d["entries"]) == before:
        return jsonify({"error": "记录不存在"}), 404
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})


@bp.put("/entries/<entry_id>")
def update_entry(entry_id: str):
    d = data.load(config.CURRENT_PROFILE)
    entry = next((e for e in d["entries"] if e.get("id") == entry_id), None)
    if entry is None:
        return jsonify({"error": "记录不存在"}), 404

    body = request.get_json(silent=True) or {}

    if "content" in body:
        content = str(body.get("content", "")).strip()
        if not content:
            return jsonify({"error": "内容不能为空"}), 400
        entry["content"] = content

    if "points" in body:
        try:
            points = int(body.get("points"))
        except (TypeError, ValueError):
            return jsonify({"error": "点数必须是整数"}), 400
        if points < 0:
            return jsonify({"error": "点数不能为负"}), 400
        entry["points"] = points

    if "category" in body:
        entry["category"] = str(body.get("category") or "").strip() or None

    if "ts" in body:
        try:
            parse_ts(body.get("ts"))
        except (ValueError, TypeError):
            return jsonify({"error": "时间格式不正确"}), 400
        entry["ts"] = body["ts"]

    # 可选时段（start_ts / end_ts）：两端都传、都传 null 清空（＝不记时长）
    if "start_ts" in body or "end_ts" in body:
        try:
            start_ts, end_ts = _resolve_span(body, entry)
        except (ValueError, TypeError) as exc:
            return jsonify({"error": str(exc) or "时段格式不正确"}), 400
        entry["start_ts"] = start_ts
        entry["end_ts"] = end_ts

    data.save(config.CURRENT_PROFILE, d)
    return jsonify(_serialize(entry))


@bp.get("/entries/export")
def export_entries():
    """打卡记录导出为 JSON 文件。

    查询参数：
      from / to   归属日期区间 YYYY-MM-DD（含端点，按凌晨 4 点归属日；可省略＝不限）
      download    1/true/yes → 返回附件下载；默认（不传）→ 写入导出目录并返回落盘信息

    导出内容：`meta`（导出时间、档案、区间、条数、天数、总点数、总时长）+ `entries`。
    entries 按归属日、再按记录时刻**升序**（早→晚）；每条含
    `day` / `ts` / `start_ts` / `end_ts` / `duration_min` / `points` / `content` / `category`。
    """
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    try:
        d_from = dt.date.fromisoformat(date_from) if date_from else None
        d_to = dt.date.fromisoformat(date_to) if date_to else None
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if d_from and d_to and d_from > d_to:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400

    d = data.load(config.CURRENT_PROFILE)
    rows = []
    for e in d.get("entries", []):
        try:
            day = date_of(parse_ts(e.get("ts")))
        except (ValueError, TypeError):
            continue
        if d_from and day < d_from:
            continue
        if d_to and day > d_to:
            continue
        item = _serialize(e)
        item["day"] = day.isoformat()
        rows.append((day, item))
    rows.sort(key=lambda r: (r[0], _ts_key(r[1])))
    entries = [item for _, item in rows]

    total_points = sum(int(e.get("points", 0) or 0) for e in entries)
    total_duration = sum(e["duration_min"] or 0 for e in entries)
    f_iso = d_from.isoformat() if d_from else None
    t_iso = d_to.isoformat() if d_to else None

    now = dt.datetime.now().astimezone()
    payload = {
        "meta": {
            "exported_at": now.isoformat(timespec="seconds"),
            "profile": config.CURRENT_PROFILE,
            "range": {"from": f_iso, "to": t_iso},
            "entry_count": len(entries),
            "day_count": len({item["day"] for item in entries}),
            "total_points": total_points,
            "total_duration_min": total_duration,   # 仅统计填了时段的记录
        },
        "entries": entries,
    }

    if f_iso and t_iso:
        span = f"{f_iso}_{t_iso}"
    else:
        span = f_iso or t_iso or "all"
    filename = f"entries-{span}-{now.strftime('%Y%m%d-%H%M%S')}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2)

    # 显式要求下载时：直接以附件返回（不落盘）
    if export_io.download_requested(request.args):
        return export_io.attachment(filename, body)

    # 默认：写入导出目录 exports/，返回落盘信息
    info = export_io.save_text(filename, body)
    info["range"] = {"from": f_iso, "to": t_iso}
    info["entry_count"] = len(entries)
    info["day_count"] = payload["meta"]["day_count"]
    info["total_points"] = total_points
    info["total_duration_min"] = total_duration
    return jsonify(info)