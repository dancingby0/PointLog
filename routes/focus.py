"""专注会话 API（v2.9）：桌面计时器上传会话 + 点数系统统计。

**存储：账号级** ``data/<账号>/focus.json``（不再是档案级 data.json）。
理由：专注时长是"我在这台电脑上花了多久"的个人数据，与日记档案无关；而且档案取决于
"当前账号 + 当前档案"的进程内状态，账号有 PIN 时服务启动不会自动登录，桌面计时器
就会找不到落点（曾导致写进看不见的 default 目录 + 上传 404）。账号级文件用
``accounts.json`` 里记住的账号名定位，**不需要登录、不需要 PIN**。

端点：

- ``POST /api/focus/sessions``          新建会话（开始计时）``{label, points}``
- ``POST /api/focus/sessions/<id>/pause|resume|stop``  暂停 / 继续 / 结束
- ``POST /api/focus/sessions/<id>/upload`` 上传为打卡记录（幂等）
- ``POST /api/focus/sync``              **自动同步**：把所有"已结束且未上传"的会话批量上传
- ``GET  /api/focus/current``           当前会话 + 实时时长（悬浮窗轮询用）
- ``GET  /api/focus/stats``             今日/累计时长、天数、按标签分布
- ``GET  /api/focus/sessions``          最近会话列表
- ``DELETE /api/focus/sessions/<id>``   删除会话（不影响已上传的打卡）
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import focus
import utils

bp = Blueprint("focus", __name__, url_prefix="/api/focus")

MAX_SESSIONS = 1000


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _account() -> str:
    """专注数据所属账号：优先当前登录账号，否则用 accounts.json 记住的账号。

    后者让桌面计时器**无需 PIN 登录**也能工作：账号目录本来就是本机可见的，
    PIN 保护的是浏览器界面，不是本地文件。
    """
    if config.CURRENT_ACCOUNT:
        return config.CURRENT_ACCOUNT
    meta = data.load_accounts_meta()
    remembered = meta.get("current") or ""
    if remembered and remembered in (meta.get("accounts") or []):
        return remembered
    return ""


def _migrate_legacy(account: str, store: dict) -> int:
    """把早期存在各档案 data.json 里的 focus_sessions 并进账号级 focus.json。

    一次性动作：并进去之后把旧字段清空（条目按 id 去重，已存在的跳过）。
    返回并入的条数。
    """
    if not account:
        return 0
    existing = {str(s.get("id")) for s in store["sessions"] if isinstance(s, dict)}
    stores = []
    for name in data.account_profile_dirs(account):
        stores.append(data.account_dir(account) / name / "data.json")
    stores.append(data.DATA_DIR / "default" / "data.json")   # 无账号归属的旧布局

    merged = 0
    for path in stores:
        if not path.exists():
            continue
        try:
            raw = data.load_path(path)
        except (ValueError, OSError):
            continue
        rows = raw.get("focus_sessions") or []
        if not isinstance(rows, list) or not rows:
            continue
        for sess in rows:
            if not isinstance(sess, dict):
                continue
            sid = str(sess.get("id"))
            if sid and sid not in existing:
                store["sessions"].append(sess)
                existing.add(sid)
                merged += 1
        raw["focus_sessions"] = []          # 旧字段清空，避免重复统计
        try:
            data.save_path(path, raw)
        except OSError:
            pass
    return merged


def _load() -> tuple[str, dict]:
    """读取专注数据（含一次性迁移）。返回 (account, store)。"""
    account = _account()
    store = data.load_focus(account)
    if _migrate_legacy(account, store):
        data.save_focus(account, store)
    return account, store


def _save(account: str, store: dict) -> None:
    rows = [s for s in store["sessions"] if isinstance(s, dict)]
    rows.sort(key=lambda s: str(s.get("created_at") or ""))
    store["sessions"] = rows[-MAX_SESSIONS:]
    data.save_focus(account, store)


def _find(store: dict, session_id: str):
    for raw in store["sessions"]:
        if str(raw.get("id")) == session_id:
            return raw
    return None


def _put(store: dict, sess: dict) -> None:
    """整条替换（幂等：同 id 覆盖）。"""
    store["sessions"] = [s for s in store["sessions"]
                         if str(s.get("id")) != str(sess["id"])] + [sess]



@bp.post("/sessions")
def create_session():
    body = request.get_json(silent=True) or {}
    label = str(body.get("label") or "").strip()
    if len(label) > 40:
        return jsonify({"error": "标签最多 40 字"}), 400
    points = body.get("points", 1)
    account, store = _load()
    # 已有运行中/暂停中的会话 → 先结束它，避免两个同时计时
    for raw in store["sessions"]:
        sess = focus.normalize_session(raw)
        if sess and sess["state"] in ("running", "paused"):
            _put(store, focus.stop(sess, _now()))
    sess = focus.start_session(label, points, _now(), new_id=data.new_id())
    _put(store, sess)
    _save(account, store)
    return jsonify(sess), 201


@bp.post("/sessions/<session_id>/<action>")
def change_state(session_id: str, action: str):
    """pause / resume / stop 三合一（幂等：状态不符就原样返回）。"""
    if action not in ("pause", "resume", "stop"):
        return jsonify({"error": "action 应为 pause/resume/stop"}), 400
    account, store = _load()
    raw = _find(store, session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    now = _now()
    updated = getattr(focus, action)(raw, now)
    if not updated:
        return jsonify({"error": "会话数据异常"}), 400
    _put(store, updated)
    _save(account, store)
    secs = focus.total_sec(updated, now)
    return jsonify({**updated, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs)})


def _upload_one(account: str, store: dict, sess: dict, points=None, label="") -> dict | None:
    """把一条会话写成打卡（幂等：已上传则更新那条）。返回 entry 或 None（不足 1 分钟）。"""
    now = _now()
    entry = focus.build_entry(sess, now, points=points, label=label)
    if not entry:
        return None
    tag = entry["category"][0] if entry["category"] else ""

    # 打卡记录写进"当前日记档案"（用户界面里看得到的地方）
    profile = config.CURRENT_PROFILE if config.CURRENT_ACCOUNT else "default"
    d = data.load(profile)
    existing = None
    if sess.get("entry_id"):
        existing = next((e for e in d["entries"] if str(e.get("id")) == sess["entry_id"]), None)
    if existing is not None:
        existing.update({k: entry[k] for k in ("content", "points", "category",
                                               "ts", "start_ts", "end_ts")})
        entry_id = str(existing["id"])
    else:
        entry_id = data.new_id()
        d["entries"].append({"id": entry_id, **entry})
    if tag and tag not in d["diary_tags"]:
        d["diary_tags"].append(tag)
    data.save(profile, d)

    sess["entry_id"] = entry_id
    sess["uploaded_at"] = now.isoformat(timespec="seconds")
    _put(store, sess)
    _save(account, store)
    return {**entry, "id": entry_id}


@bp.post("/sessions/<session_id>/upload")
def upload_session(session_id: str):
    """把会话写成一条打卡记录（幂等）。"""
    account, store = _load()
    raw = _find(store, session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    sess = focus.normalize_session(raw)
    if not sess:
        return jsonify({"error": "会话数据异常"}), 400
    if sess["state"] == "running":
        sess = focus.pause(sess, _now())      # 上传前先暂停，避免时长继续涨

    body = request.get_json(silent=True) or {}
    entry = _upload_one(account, store, sess, points=body.get("points"),
                        label=str(body.get("label") or ""))
    if entry is None:
        return jsonify({"error": "专注不足 1 分钟，暂不能上传"}), 400
    return jsonify({"session": sess, "entry": entry})


@bp.post("/sync")
def sync_sessions():
    """**自动同步**：把所有"已结束且未上传"的会话批量上传（幂等，可反复调用）。

    body 可选：``{"points": 1}`` 覆盖点数；``{"min_minutes": 1}`` 过滤过短的会话。
    """
    body = request.get_json(silent=True) or {}
    account, store = _load()
    now = _now()
    try:
        min_minutes = float(body.get("min_minutes") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "min_minutes 应为数字"}), 400
    points = body.get("points")

    uploaded, failed = [], []
    for raw in list(store["sessions"]):
        sess = focus.normalize_session(raw)
        if not sess or sess["state"] == "running" or sess.get("entry_id"):
            continue                          # 运行中 / 已上传的跳过
        if focus.total_sec(sess, now) < min_minutes * 60:
            continue
        try:
            entry = _upload_one(account, store, sess, points=points)
        except (ValueError, OSError) as exc:
            failed.append({"id": sess["id"], "error": str(exc)})
            continue
        if entry:
            uploaded.append({"id": sess["id"], "label": sess.get("label") or "",
                             "content": entry["content"], "points": entry["points"],
                             "entry_id": entry["id"]})
    return jsonify({"uploaded": uploaded, "count": len(uploaded), "failed": failed})


@bp.get("/current")
def current():
    """当前计时器状态（供悬浮窗轮询）：只返回运行/暂停中的会话 + 实时时长。"""
    _account_name, store = _load()
    now = _now()
    live = None
    for raw in store["sessions"]:
        sess = focus.normalize_session(raw)
        if sess and sess["state"] in ("running", "paused"):
            live = sess
    if not live:
        return jsonify({"session": None, "elapsed_sec": 0, "elapsed_text": "0m"})
    secs = focus.total_sec(live, now)
    return jsonify({"session": live, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs)})


@bp.get("/stats")
def stats_endpoint():
    """点数系统里的专注统计：今日 / 累计时长、累计天数、按标签分布。"""
    _account_name, store = _load()
    now = _now()
    today = utils.date_of(now)
    summary = focus.aggregate(store["sessions"], today, now)
    summary["day"] = today.isoformat()
    return jsonify(summary)


@bp.get("/sessions")
def list_sessions():
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 200))
    except ValueError:
        return jsonify({"error": "limit 应为整数"}), 400
    _account_name, store = _load()
    now = _now()
    rows = []
    for raw in store["sessions"]:
        sess = focus.normalize_session(raw)
        if not sess:
            continue
        secs = focus.total_sec(sess, now)
        rows.append({**sess, "elapsed_sec": int(secs),
                     "elapsed_text": focus.fmt_duration(secs),
                     "uploaded": bool(sess.get("entry_id"))})
    rows.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    return jsonify({"sessions": rows[:limit]})


@bp.delete("/sessions/<session_id>")
def delete_session(session_id: str):
    account, store = _load()
    before = len(store["sessions"])
    store["sessions"] = [s for s in store["sessions"]
                         if str(s.get("id")) != session_id]
    if len(store["sessions"]) == before:
        return jsonify({"error": "会话不存在"}), 404
    _save(account, store)
    return jsonify({"ok": True})


