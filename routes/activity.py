"""活动数据 API（v2.6）：从本机 ActivityWatch 拉桌面活动 → 每日摘要。

端点：

- ``GET  /api/activity/status``        连接状态 + 桶列表 + 已同步天数
- ``GET/PUT /api/activity/config``     活动数据设置（地址 / 主机 / 类别规则 / 忽略应用）
- ``POST /api/activity/sync``          ``{days:N}`` 或 ``{from,to}`` → 逐日拉取并聚合（幂等覆盖）
- ``GET  /api/activity/days``          每日摘要列表（图表用，轻量）
- ``GET  /api/activity/day/<date>``    单日明细
- ``DELETE /api/activity/day/<date>``  删除某天摘要（想重算时先清）

约定：

- ActivityWatch 连不上 → 503 + 明确提示；不抛 500，也不影响打卡等既有功能；
- 归属日沿用凌晨 4 点规则（``utils.day_bounds``），与 entries 完全一致；
- 同步幂等：同一天重复同步 = 覆盖写，结果只取决于 AW 里的事实数据。
"""

import datetime as dt
import re

from flask import Blueprint, jsonify, request

import activity
import aw_client
import config
import data
import utils

bp = Blueprint("activity", __name__, url_prefix="/api/activity")

MAX_SYNC_DAYS = 120          # 单次请求最多补多少天，防止误操作把服务拖死
RULE_FIELDS = ("app", "title", "url")


# ---------- 设置 ----------

def _settings(store: dict) -> dict:
    return activity.merged_settings(store.get("settings"))


def _validate_settings(payload: dict) -> tuple[dict, str | None]:
    """校验并规范化 PUT /config 的 body；返回 (新设置, 错误信息)。"""
    if not isinstance(payload, dict):
        return {}, "请求体应为 JSON 对象"
    st = activity.merged_settings({})

    if "enabled" in payload:
        st["enabled"] = bool(payload["enabled"])

    if "base_url" in payload:
        url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not re.match(r"^https?://[^\s]+$", url):
            return {}, "base_url 需形如 http://127.0.0.1:5600"
        st["base_url"] = url

    if "api_token" in payload:
        st["api_token"] = str(payload.get("api_token") or "").strip()

    if "host" in payload:
        st["host"] = str(payload.get("host") or "").strip()

    if "gap_allow_sec" in payload:
        try:
            gap = int(payload.get("gap_allow_sec"))
        except (TypeError, ValueError):
            return {}, "gap_allow_sec 应为整数（秒）"
        st["gap_allow_sec"] = max(0, min(gap, 3600))

    if "ignored_apps" in payload:
        raw = payload.get("ignored_apps")
        if not isinstance(raw, list):
            return {}, "ignored_apps 应为字符串数组"
        st["ignored_apps"] = [str(x).strip().lower() for x in raw if str(x).strip()]

    if "rules" in payload:
        raw = payload.get("rules")
        if not isinstance(raw, list):
            return {}, "rules 应为数组"
        rules = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                return {}, f"第 {i + 1} 条规则不是对象"
            category = str(item.get("category") or "").strip()
            if not category:
                return {}, f"第 {i + 1} 条规则缺少 category"
            rule = {"category": category[:30]}
            for field in RULE_FIELDS:
                pattern = str(item.get(field) or "").strip()
                if not pattern:
                    continue
                try:
                    re.compile(pattern)
                except re.error as exc:
                    return {}, f"第 {i + 1} 条规则的 {field} 正则无效：{exc}"
                rule[field] = pattern
            if not any(f in rule for f in RULE_FIELDS):
                return {}, f"第 {i + 1} 条规则至少要给 app / title / url 之一"
            rules.append(rule)
        st["rules"] = rules

    return st, None


def _connect(st: dict) -> tuple:
    """建客户端并列出桶（所有连接类错误统一抛 AwUnavailable）。"""
    client = aw_client.AwClient(st.get("base_url"), st.get("api_token") or None)
    return client, client.bucket_summaries()


def _day_list(days: int) -> list[dt.date]:
    today = utils.date_of(dt.datetime.now().astimezone())
    return [today - dt.timedelta(days=i) for i in range(max(1, days) - 1, -1, -1)]


def _sync_one(client: aw_client.AwClient, buckets: dict, day: dt.date, st: dict) -> dict:
    """拉一天的三类事件并聚合（跨 4 点边界由 activity.py 切片）。"""
    lo, hi = utils.day_bounds(day)
    window = client.events(buckets["window"], lo, hi)
    afk = client.events(buckets["afk"], lo, hi)
    web = client.events(buckets["web"], lo, hi) if buckets.get("web") else []
    return activity.aggregate_day(day, window, afk, web, st)


# ---------- 状态 / 设置 ----------

@bp.get("/status")
def status():
    store = data.load_activity(config.CURRENT_PROFILE)
    st = _settings(store)
    last = max((str(d.get("imported_at") or "") for d in store["days"].values()), default="")
    info = {
        "enabled": st["enabled"],
        "base_url": st["base_url"],
        "connected": False,
        "error": None,
        "hint": None,
        "buckets": [],
        "picked": {"window": None, "afk": None, "web": None},
        "synced_days": len(store["days"]),
        "last_imported_at": last or None,
        "has_web_watcher": False,
    }
    try:
        _, infos = _connect(st)
    except aw_client.AwUnavailable as exc:
        info["error"] = str(exc)
        info["hint"] = "ActivityWatch 未安装或未启动（默认地址 http://127.0.0.1:5600）"
        return jsonify(info)

    info["connected"] = True
    info["buckets"] = infos
    info["picked"] = activity.pick_buckets(infos, st.get("host") or "")
    info["has_web_watcher"] = bool(info["picked"]["web"])
    if not (info["picked"]["window"] and info["picked"]["afk"]):
        info["hint"] = "未发现窗口/AFK 桶：请确认 ActivityWatch 与 aw-watcher-window、aw-watcher-afk 正在运行"
    elif not info["picked"]["web"]:
        info["hint"] = "未发现浏览器 Web 桶：装 aw-watcher-web 扩展才能区分具体网页（如 DeepSeek / B 站）"
    return jsonify(info)


@bp.get("/config")
def get_config():
    store = data.load_activity(config.CURRENT_PROFILE)
    return jsonify({"settings": _settings(store)})


@bp.put("/config")
def put_config():
    store = data.load_activity(config.CURRENT_PROFILE)
    st, err = _validate_settings(request.get_json(silent=True) or {})
    if err:
        return jsonify({"error": err}), 400
    store["settings"] = st
    data.save_activity(config.CURRENT_PROFILE, store)
    return jsonify({"settings": st})


# ---------- 同步 ----------

@bp.post("/sync")
def sync():
    store = data.load_activity(config.CURRENT_PROFILE)
    st = _settings(store)
    if not st.get("enabled", True):
        return jsonify({"error": "活动数据同步已关闭（可在设置里重新打开）"}), 400

    body = request.get_json(silent=True) or {}
    try:
        if body.get("from") or body.get("to"):
            today = utils.date_of(dt.datetime.now().astimezone())
            start = dt.date.fromisoformat(str(body.get("from"))) if body.get("from") else today
            end = dt.date.fromisoformat(str(body.get("to"))) if body.get("to") else today
        else:
            days = int(body.get("days") or 1)
            start, end = _day_list(days)[0], _day_list(days)[-1]
    except ValueError:
        return jsonify({"error": "days 应为整数；from/to 应为 YYYY-MM-DD"}), 400

    if start > end:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400
    targets = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    if len(targets) > MAX_SYNC_DAYS:
        return jsonify({"error": f"一次最多补 {MAX_SYNC_DAYS} 天，请分批同步"}), 400

    try:
        client, infos = _connect(st)
    except aw_client.AwUnavailable as exc:
        return jsonify({"error": f"连不上 ActivityWatch：{exc}", "connected": False}), 503

    buckets = activity.pick_buckets(infos, st.get("host") or "")
    if not (buckets["window"] and buckets["afk"]):
        return jsonify({
            "error": "未找到窗口/AFK 桶，无法统计活跃时长",
            "picked": buckets,
            "buckets": infos,
        }), 409

    synced, failed = [], []
    for day in targets:
        try:
            summary = _sync_one(client, buckets, day, st)
        except aw_client.AwUnavailable as exc:
            failed.append({"day": day.isoformat(), "error": str(exc)})
            continue
        store["days"][day.isoformat()] = summary
        synced.append(summary)

    if synced:
        data.save_activity(config.CURRENT_PROFILE, store)
    if not synced:
        return jsonify({"error": "同步失败", "failed": failed}), 503

    return jsonify({
        "synced": len(synced),
        "failed": failed,
        "picked": buckets,
        "has_web_watcher": bool(buckets.get("web")),
        "days": [{k: d.get(k) for k in ("day", "active_min", "excluded_min",
                                        "first_ts", "last_ts")} for d in synced],
    })


# ---------- 查询 ----------

@bp.get("/days")
def list_days():
    today = utils.date_of(dt.datetime.now().astimezone())
    try:
        start = dt.date.fromisoformat(request.args["from"]) if request.args.get("from") \
            else today - dt.timedelta(days=29)
        end = dt.date.fromisoformat(request.args["to"]) if request.args.get("to") else today
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if start > end:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400

    store = data.load_activity(config.CURRENT_PROFILE)
    out = []
    for key in sorted(store["days"]):
        try:
            day = dt.date.fromisoformat(key)
        except ValueError:
            continue
        if not (start <= day <= end):
            continue
        item = store["days"][key]
        apps = item.get("apps") or []
        sites = item.get("sites") or []
        out.append({
            "day": key,
            "active_min": item.get("active_min", 0),
            "excluded_min": item.get("excluded_min", 0),
            "top_app": apps[0]["app"] if apps else None,
            "top_site": sites[0]["domain"] if sites else None,
            "imported_at": item.get("imported_at"),
        })
    return jsonify({
        "from": start.isoformat(), "to": end.isoformat(),
        "days": out,
        "synced_days": len(store["days"]),
        "has_web_watcher": any(bool((d.get("sites") or [])) for d in store["days"].values()),
    })


@bp.get("/day/<day>")
def get_day(day: str):
    try:
        key = dt.date.fromisoformat(day).isoformat()
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    store = data.load_activity(config.CURRENT_PROFILE)
    item = store["days"].get(key)
    if not item:
        return jsonify({"error": f"{key} 还没有活动数据（先同步这一天）", "day": key}), 404
    return jsonify(item)


@bp.delete("/day/<day>")
def delete_day(day: str):
    try:
        key = dt.date.fromisoformat(day).isoformat()
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    store = data.load_activity(config.CURRENT_PROFILE)
    if key not in store["days"]:
        return jsonify({"error": f"{key} 没有活动数据", "day": key}), 404
    del store["days"][key]
    data.save_activity(config.CURRENT_PROFILE, store)
    return jsonify({"deleted": key, "synced_days": len(store["days"])})

