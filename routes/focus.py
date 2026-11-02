"""专注会话 API（v2.8）：桌面计时器上传会话 + 点数系统统计。

端点：

- ``POST /api/focus/sessions``          新建会话（开始计时）``{label, points}``
- ``POST /api/focus/sessions/<id>/pause|resume|stop``  暂停 / 继续 / 结束
- ``POST /api/focus/sessions/<id>/upload`` 上传为打卡记录（``{points?, label?}``，幂等）
- ``GET  /api/focus/current``           当前计时器状态 + 实时时长（悬浮窗轮询用）
- ``GET  /api/focus/stats``             今日/累计时长、天数、按标签分布（点数系统里展示）
- ``GET  /api/focus/sessions``          最近会话列表
- ``DELETE /api/focus/sessions/<id>``   删除会话（不影响已上传的打卡）

设计要点：

- **上传是显式动作**：计时只记时长，不自动生成打卡；点"上传"才写 entries，
  于是点数线 / 连续天数不会被计时器污染；
- **幂等**：会话里存 ``entry_id``，重复上传同一条会话只会更新那条打卡，不会翻倍；
- **本地优先**：计时器在桌面端自己跑（Python tkinter），服务挂了也不丢计时状态。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import focus
import utils

bp = Blueprint("focus", __name__, url_prefix="/api/focus")

MAX_SESSIONS = 500


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _load():
    d = data.load(config.CURRENT_PROFILE)
    d.setdefault("focus_sessions", [])
    return d


def _find(d: dict, session_id: str):
    for raw in d["focus_sessions"]:
        if str(raw.get("id")) == session_id:
            return raw
    return None


def _save_session(d: dict, sess: dict) -> None:
    """整条替换（normalize 后的结构），保持列表按创建时间升序、总量有上限。"""
    rows = [s for s in d["focus_sessions"] if str(s.get("id")) != sess["id"]]
    rows.append(sess)
    rows.sort(key=lambda s: str(s.get("created_at") or ""))
    d["focus_sessions"] = rows[-MAX_SESSIONS:]
    data.save(config.CURRENT_PROFILE, d)


@bp.post("/sessions")
def create_session():
    body = request.get_json(silent=True) or {}
    label = str(body.get("label") or "").strip()
    if len(label) > 40:
        return jsonify({"error": "标签最多 40 字"}), 400
    points = body.get("points", 1)
    d = _load()
    # 已有运行中/暂停中的会话 → 先结束它，避免两个同时计时
    for raw in d["focus_sessions"]:
        sess = focus.normalize_session(raw)
        if sess and sess["state"] in ("running", "paused"):
            _save_session(d, focus.stop(sess, _now()))
    now = _now()
    sess = focus.start_session(label, points, now, new_id=data.new_id())
    _save_session(d, sess)
    return jsonify(sess), 201


@bp.post("/sessions/<session_id>/<action>")
def change_state(session_id: str, action: str):
    """pause / resume / stop 三合一（幂等：状态不符就原样返回）。"""
    if action not in ("pause", "resume", "stop"):
        return jsonify({"error": "action 应为 pause/resume/stop"}), 400
    d = _load()
    raw = _find(d, session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    now = _now()
    updated = getattr(focus, action)(raw, now)
    if not updated:
        return jsonify({"error": "会话数据异常"}), 400
    _save_session(d, updated)
    secs = focus.total_sec(updated, now)
    return jsonify({**updated, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs)})



@bp.post("/sessions/<session_id>/upload")
def upload_session(session_id: str):
    """把会话写成一条打卡记录（幂等：已上传则更新那条）。"""
    d = _load()
    raw = _find(d, session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    sess = focus.normalize_session(raw)
    if not sess:
        return jsonify({"error": "会话数据异常"}), 400
    if sess["state"] == "running":
        sess = focus.pause(sess, _now())          # 上传前先暂停，避免时长继续涨

    body = request.get_json(silent=True) or {}
    now = _now()
    entry = focus.build_entry(sess, now, points=body.get("points"),
                              label=str(body.get("label") or ""))
    if not entry:
        return jsonify({"error": "专注不足 1 分钟，暂不能上传"}), 400

    label = entry["category"][0] if entry["category"] else ""
    d = data.load(config.CURRENT_PROFILE)
    existing = None
    if sess.get("entry_id"):
        existing = next((e for e in d["entries"] if str(e.get("id")) == sess["entry_id"]), None)
    if existing is not None:                       # 幂等更新
        existing.update({k: entry[k] for k in ("content", "points", "category",
                                               "ts", "start_ts", "end_ts")})
        entry_id = str(existing["id"])
    else:
        entry_id = data.new_id()
        d["entries"].append({"id": entry_id, **entry})
    if label and label not in d["diary_tags"]:     # 标签顺手入池，方便下次点选
        d["diary_tags"].append(label)
    data.save(config.CURRENT_PROFILE, d)

    sess["entry_id"] = entry_id
    sess["uploaded_at"] = now.isoformat(timespec="seconds")
    _save_session(_load(), sess)
    return jsonify({"session": sess, "entry": {**entry, "id": entry_id}})


@bp.get("/current")
def current():
    """当前计时器状态（供悬浮窗轮询）：只返回运行/暂停中的会话 + 实时时长。"""
    d = _load()
    live = None
    for raw in d["focus_sessions"]:
        sess = focus.normalize_session(raw)
        if sess and sess["state"] in ("running", "paused"):
            live = sess
    now = _now()
    if not live:
        return jsonify({"session": None, "elapsed_sec": 0, "elapsed_text": "0m"})
    secs = focus.total_sec(live, now)
    return jsonify({"session": live, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs)})


@bp.get("/stats")
def stats_endpoint():
    """点数系统里的专注统计：今日 / 累计时长、累计天数、按标签分布。"""
    d = _load()
    now = _now()
    today = utils.date_of(now)
    summary = focus.aggregate(d["focus_sessions"], today, now)
    summary["day"] = today.isoformat()
    return jsonify(summary)


@bp.get("/sessions")
def list_sessions():
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except ValueError:
        return jsonify({"error": "limit 应为整数"}), 400
    d = _load()
    now = _now()
    rows = []
    for raw in sorted(d["focus_sessions"], key=lambda s: str(s.get("created_at") or ""),
                      reverse=True)[:limit]:
        sess = focus.normalize_session(raw)
        if not sess:
            continue
        secs = focus.total_sec(sess, now)
        rows.append({**sess, "elapsed_sec": int(secs),
                     "elapsed_text": focus.fmt_duration(secs),
                     "uploaded": bool(sess.get("entry_id"))})
    return jsonify({"sessions": rows})


@bp.delete("/sessions/<session_id>")
def delete_session(session_id: str):
    d = _load()
    before = len(d["focus_sessions"])
    d["focus_sessions"] = [s for s in d["focus_sessions"] if str(s.get("id")) != session_id]
    if len(d["focus_sessions"]) == before:
        return jsonify({"error": "会话不存在"}), 404
    data.save(config.CURRENT_PROFILE, d)
    return jsonify({"ok": True})
