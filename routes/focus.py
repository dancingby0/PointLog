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
from routes import accounts

bp = Blueprint("focus", __name__, url_prefix="/api/focus")

MAX_SESSIONS = 500


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _load(profile: str | None = None):
    """读取会话所在档案；profile 为空时用当前档案。"""
    if profile is None:
        profile = config.CURRENT_PROFILE
    d = data.load(profile)
    d.setdefault("focus_sessions", [])
    return d


def _require_profile():
    """确保有可用的档案；未登录且账号有 PIN 时返回错误信息。

    为什么必须拦：账号带 PIN 时服务启动不会自动登录，此时 ``CURRENT_PROFILE`` 还是
    ``default``，数据会写进**无账号归属**的根目录 ``data/default``——
    用户在浏览器输 PIN 登录后看到的是 ``data/<账号>/<档案>``，两边不是同一个文件，
    于是出现"计时器显示已计时、界面里查不到/上传 404"。
    宁可让计时器明确提示"请先在浏览器登录"，也不要写进用户看不见的地方。
    """
    if config.CURRENT_ACCOUNT:
        return None
    auto = accounts.ensure_auto_login()
    if auto:
        return None
    meta = data.load_accounts_meta()
    if meta.get("accounts"):
        return "尚未登录 PointLog：请先在浏览器里打开并登录账号（账号有 PIN 时不会自动登录）"
    return None


def _legacy_default_path():
    """无账号归属的旧布局档案路径：<data>/default/data.json（可能不存在）。"""
    return data.DATA_DIR / "default" / "data.json"


def _candidate_stores() -> list[tuple[str, str, object]]:
    """可能存着会话的位置：[(kind, key, label)]，kind 为 "profile" 或 "path"。

    顺序＝优先级：当前档案 → 账号内其它档案 → 无账号的 default（旧布局）。
    后者的必要性：账号有 PIN 时服务启动不会自动登录，计时器先开始的会话会落在
    ``data/default/data.json``；而登录后 ``profile_dir("default")`` 指向的是
    ``data/<账号>/default``，两者不是同一个文件。
    """
    stores = []
    seen = []

    def add(kind, key):
        label = key if kind == "profile" else str(key)
        if label not in seen:
            seen.append(label)
            stores.append((kind, key, label))

    add("profile", config.CURRENT_PROFILE)
    if config.CURRENT_ACCOUNT:
        for name in data.account_profile_dirs(config.CURRENT_ACCOUNT):
            add("profile", name)
    legacy = _legacy_default_path()
    if legacy.exists():
        add("path", legacy)
    return stores


def _read_store(kind: str, key) -> dict:
    d = data.load(key) if kind == "profile" else data.load_path(key)
    d.setdefault("focus_sessions", [])
    return d


def _write_store(kind: str, key, payload: dict) -> None:
    if kind == "profile":
        data.save(key, payload)
    else:
        data.save_path(key, payload)


def _locate(session_id: str):
    """按 id 找会话：返回 (store, data, session) 或 (None, None, None)。"""
    for kind, key, _label in _candidate_stores():
        try:
            d = _read_store(kind, key)
        except (ValueError, OSError):
            continue
        for raw in d["focus_sessions"]:
            if str(raw.get("id")) == session_id:
                return (kind, key), d, raw
    return None, None, None


def _find(d: dict, session_id: str):
    for raw in d["focus_sessions"]:
        if str(raw.get("id")) == session_id:
            return raw
    return None


def _save_session(d: dict, sess: dict, store=None) -> str:
    """整条替换（normalize 后的结构），保持列表按创建时间升序、总量有上限。

    store 为空时写回"当前档案"；返回实际写入的位置描述（便于接口回报）。
    """
    rows = [s for s in d["focus_sessions"] if str(s.get("id")) != sess["id"]]
    rows.append(sess)
    rows.sort(key=lambda s: str(s.get("created_at") or ""))
    d["focus_sessions"] = rows[-MAX_SESSIONS:]
    if store is None:
        store = ("profile", config.CURRENT_PROFILE)
    kind, key = store
    _write_store(kind, key, d)
    return key if kind == "profile" else str(key)


@bp.post("/sessions")
def create_session():
    err = _require_profile()
    if err:
        return jsonify({"error": err, "need_login": True}), 409
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
    profile, d, raw = _locate(session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    now = _now()
    updated = getattr(focus, action)(raw, now)
    if not updated:
        return jsonify({"error": "会话数据异常"}), 400
    where = _save_session(d, updated, profile)
    secs = focus.total_sec(updated, now)
    return jsonify({**updated, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs),
                    "profile": where})



@bp.post("/sessions/<session_id>/upload")
def upload_session(session_id: str):
    """把会话写成一条打卡记录（幂等：已上传则更新那条）。

    打卡记录写进**会话所在的那个档案**（而不是"当前档案"），
    这样"未登录时先计时、之后登录再上传"也不会写错地方。
    """
    profile, d, raw = _locate(session_id)
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

    sess["entry_id"] = entry_id
    sess["uploaded_at"] = now.isoformat(timespec="seconds")
    where = _save_session(d, sess, profile)        # 与打卡记录写在同一处
    return jsonify({"session": sess, "entry": {**entry, "id": entry_id},
                    "profile": where})


@bp.get("/current")
def current():
    """当前计时器状态（供悬浮窗轮询）：只返回运行/暂停中的会话 + 实时时长。

    会遍历候选档案，所以"未登录时开始的计时"在登录后仍能被找到（响应里带 profile）。
    """
    now = _now()
    live = None
    live_store = None
    for kind, key, label in _candidate_stores():
        try:
            d = _read_store(kind, key)
        except (ValueError, OSError):
            continue
        for raw in d["focus_sessions"]:
            sess = focus.normalize_session(raw)
            if sess and sess["state"] in ("running", "paused"):
                live, live_store = sess, label
    if not live:
        return jsonify({"session": None, "elapsed_sec": 0, "elapsed_text": "0m",
                        "profile": config.CURRENT_PROFILE})
    secs = focus.total_sec(live, now)
    return jsonify({"session": live, "elapsed_sec": int(secs),
                    "elapsed_text": focus.fmt_duration(secs),
                    "profile": live_store})


@bp.get("/stats")
def stats_endpoint():
    """点数系统里的专注统计：今日 / 累计时长、累计天数、按标签分布。

    汇总"当前档案 + 账号内其它档案 + default"里的会话，覆盖"先计时、后登录"的情况。
    """
    now = _now()
    today = utils.date_of(now)
    rows = []
    for kind, key, _label in _candidate_stores():
        try:
            rows.extend(_read_store(kind, key)["focus_sessions"])
        except (ValueError, OSError):
            continue
    summary = focus.aggregate(rows, today, now)
    summary["day"] = today.isoformat()
    summary["profile"] = config.CURRENT_PROFILE
    return jsonify(summary)


@bp.get("/sessions")
def list_sessions():
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except ValueError:
        return jsonify({"error": "limit 应为整数"}), 400
    now = _now()
    rows = []
    for kind, key, label in _candidate_stores():
        try:
            sessions = _read_store(kind, key)["focus_sessions"]
        except (ValueError, OSError):
            continue
        for raw in sessions:
            sess = focus.normalize_session(raw)
            if not sess:
                continue
            secs = focus.total_sec(sess, now)
            rows.append({**sess, "profile": label, "elapsed_sec": int(secs),
                         "elapsed_text": focus.fmt_duration(secs),
                         "uploaded": bool(sess.get("entry_id"))})
    rows.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    return jsonify({"sessions": rows[:limit]})


@bp.delete("/sessions/<session_id>")
def delete_session(session_id: str):
    store, d, raw = _locate(session_id)
    if raw is None:
        return jsonify({"error": "会话不存在"}), 404
    d["focus_sessions"] = [s for s in d["focus_sessions"]
                           if str(s.get("id")) != session_id]
    kind, key = store
    _write_store(kind, key, d)
    return jsonify({"ok": True})
