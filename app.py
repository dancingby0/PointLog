"""PointLog 本地服务入口。

运行方式：.venv\\Scripts\\python app.py  →  http://127.0.0.1:5000/
"""

import datetime as dt

from flask import Flask, jsonify, render_template, request

import data

app = Flask(__name__)

# 默认档案（多档案切换在 M6 实现）
CURRENT_PROFILE = "default"


@app.route("/")
def index():
    return render_template("index.html")


# ---------- 打卡记录 ----------

def _day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """某"天"的边界：以凌晨 4 点为界，即 [day 04:00, day+1 04:00)。"""
    start = dt.datetime.combine(day, dt.time(4, 0, 0)).astimezone()
    end = start + dt.timedelta(days=1)
    return start, end


def _date_of(t: dt.datetime) -> dt.date:
    """按凌晨4点规则，某时刻属于哪一天 = 时间减去4小时后取日历日。

    例：2026-09-06 02:00 → 减去4h → 2026-09-05 22:00 → 归属 2026-09-05。
    """
    return (t - dt.timedelta(hours=4)).date()


def _parse_ts(s: str) -> dt.datetime:
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


@app.get("/api/days")
def list_days():
    """返回最近 N 天（默认 14）的 {date, points, is_today}，从新到旧；供日期切换器使用。"""
    d = data.load(CURRENT_PROFILE)
    n = request.args.get("days", default=14, type=int)
    n = max(1, min(n, 90))
    now = dt.datetime.now().astimezone()
    today = _date_of(now)

    day_points = {}
    for e in d["entries"]:
        try:
            t = _parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        k = _date_of(t)
        day_points[k] = day_points.get(k, 0) + int(e.get("points", 0))

    days = []
    for i in range(n):
        day = today - dt.timedelta(days=i)
        days.append({
            "date": day.isoformat(),
            "points": day_points.get(day, 0),
            "is_today": i == 0,
        })
    return jsonify(days)


@app.get("/api/entries")
def list_entries():
    """返回某天的记录与点数；?day=YYYY-MM-DD，缺省为"今天"（凌晨4点界）。"""
    d = data.load(CURRENT_PROFILE)
    day_str = request.args.get("day")
    if day_str:
        try:
            day = dt.datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "day 格式应为 YYYY-MM-DD"}), 400
    else:
        day = _date_of(dt.datetime.now().astimezone())
    start, end = _day_bounds(day)
    entries = []
    for e in d["entries"]:
        try:
            t = _parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        if start <= t < end:
            entries.append(e)
    total = sum(int(e.get("points", 0)) for e in entries)
    return jsonify({
        "entries": sorted(entries, key=lambda e: e["ts"], reverse=True),
        "day_points": total,
    })


@app.post("/api/entries")
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

    ts_str = body.get("ts")
    try:
        ts_iso = ts_str if ts_str else dt.datetime.now().astimezone().isoformat()
        _parse_ts(ts_iso)  # 校验格式
    except (ValueError, TypeError):
        return jsonify({"error": "时间格式不正确"}), 400

    entry = {
        "id": data.new_id(),
        "ts": ts_iso,
        "points": points,
        "content": content,
        "category": (str(body.get("category") or "")).strip() or None,
    }
    d = data.load(CURRENT_PROFILE)
    d["entries"].append(entry)
    data.save(CURRENT_PROFILE, d)
    return jsonify(entry), 201


@app.delete("/api/entries/<entry_id>")
def delete_entry(entry_id: str):
    d = data.load(CURRENT_PROFILE)
    before = len(d["entries"])
    d["entries"] = [e for e in d["entries"] if e.get("id") != entry_id]
    if len(d["entries"]) == before:
        return jsonify({"error": "记录不存在"}), 404
    data.save(CURRENT_PROFILE, d)
    return jsonify({"ok": True})


@app.put("/api/entries/<entry_id>")
def update_entry(entry_id: str):
    d = data.load(CURRENT_PROFILE)
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
            _parse_ts(body.get("ts"))
        except (ValueError, TypeError):
            return jsonify({"error": "时间格式不正确"}), 400
        entry["ts"] = body["ts"]

    data.save(CURRENT_PROFILE, d)
    return jsonify(entry)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
