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
    """某"自然日"边界（M2 前按 0 点；M2 细化为凌晨 4 点）。"""
    start = dt.datetime.combine(day, dt.time(0, 0, 0)).astimezone()
    end = start + dt.timedelta(days=1)
    return start, end


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


@app.get("/api/entries")
def list_entries():
    """返回：今日记录（含今日点数）。"""
    d = data.load(CURRENT_PROFILE)
    now = dt.datetime.now().astimezone()
    start, end = _day_bounds(now.date())
    today = []
    for e in d["entries"]:
        try:
            t = _parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        if start <= t < end:
            today.append(e)
    today_points = sum(int(e.get("points", 0)) for e in today)
    return jsonify({
        "entries": sorted(today, key=lambda e: e["ts"], reverse=True),
        "today_points": today_points,
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
