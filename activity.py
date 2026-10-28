"""ActivityWatch 事件聚合（纯函数：无 Flask、无网络、无文件读写，可独立测试）。

输入：AW 的 window(``currentwindow``) / afk(``afkstatus``) / web(``web.tab.current``) 事件列表
输出：PointLog 的"每日活动摘要"（存 data/<账号>/<档案>/activity.json，见 docs §13）

口径（与项目既有约定保持一致）：

- **归属日按凌晨 4 点划分**（``utils.day_bounds``）：[D 04:00, D+1 04:00)，与打卡完全一致；
- **活跃时长** = 窗口事件 ∩ ``not-afk`` 区间 —— 人真的在电脑前的时间（不是"窗口存在"的时间）；
- 窗口事件 ``data.title == "excluded"`` 表示用户配置了标题排除：时间仍计入活跃，但不留标题；
- ``duration <= 0`` 的事件（纯心跳）没有时长，直接忽略；
- 网站时长同样要先与活跃区间求交，后台标签页不计。

类别规则：``rules`` 自上而下、首个命中生效；一条规则可同时给 ``app`` / ``title`` / ``url``
三个正则，**给出的字段必须全部命中**（AND，各字段内部用 ``re.search``，可写 ``a|b`` 多选）。
"同一域名下区分不同内容"就靠这个：``{"category": "学习", "url": "bilibili\\.com", "title": "课程|考研"}``
"""

import datetime as dt
import re
from urllib.parse import urlparse

import utils

# 默认类别规则：用户可在设置页改；顺序＝优先级
DEFAULT_RULES = [
    {"category": "AI辅助", "url": r"deepseek\.com|chat\.openai\.com|chatgpt\.com|claude\.ai"
                                 r"|gemini\.google\.com|copilot\.microsoft\.com"},
    {"category": "学习", "url": r"bilibili\.com|youtube\.com", "title": r"课程|教程|考研|lecture|讲座|真题"},
    {"category": "学习", "app": r"obsidian|anki|winword|wps|excel|powerpnt|acrobat|foxit|zotero"},
    {"category": "编程", "app": r"code|pycharm|idea|devenv|sublime|goland|webstorm|windowsterminal"
                               r"|powershell|pwsh|cmd|vim|emacs"},
    {"category": "娱乐", "url": r"bilibili\.com|youtube\.com|douyin\.com|weibo\.com|tieba\.baidu\.com"
                               r"|zhihu\.com|xiaohongshu\.com"},
    {"category": "娱乐", "app": r"steam|potplayer|vlc|netflix|bilibili|qqmusic|cloudmusic"},
    {"category": "通讯", "app": r"wechat|weixin|qq|telegram|discord|slack|feishu|lark|dingtalk"},
]

# 默认设置（可与用户配置逐键合并）
DEFAULT_SETTINGS = {
    "enabled": True,
    "base_url": "http://127.0.0.1:5600",
    "api_token": "",
    "host": "",              # 多机时只取某台的桶（留空＝优先本机名，其次任选）
    "gap_allow_sec": 120,    # 相邻活跃区间的空洞 ≤ 此值视为连续（秒）
    "ignored_apps": ["activitywatch", "pointlog"],   # 完全不统计的应用（小写子串匹配）
    "rules": DEFAULT_RULES,
}

UNCATEGORIZED = "未分类"


def merged_settings(settings: dict | None) -> dict:
    """把用户配置叠到默认值上（只补缺失键，不改变已有值语义）。"""
    out = dict(DEFAULT_SETTINGS)
    for k, v in (settings or {}).items():
        if v is not None:
            out[k] = v
    return out


# ---------- 区间代数 ----------

def span_of(event: dict):
    """AW 事件 → (start, end, data)；无时长 / 时间不可解析 → None。"""
    if not isinstance(event, dict):
        return None
    try:
        start = utils.parse_ts(event.get("timestamp"))
        duration = float(event.get("duration") or 0)
    except (ValueError, TypeError):
        return None
    if duration <= 0:
        return None                     # 纯心跳事件：没有时长
    return start, start + dt.timedelta(seconds=duration), (event.get("data") or {})


def clip(span, lo: dt.datetime, hi: dt.datetime):
    """把区间裁到 [lo, hi) 内；裁完为空（或本来就无效）返回 None。"""
    if not span:
        return None
    start, end, data = span
    s, e = max(start, lo), min(end, hi)
    return (s, e, data) if e > s else None


def non_overlapping(spans: list) -> list:
    """把可能重叠的区间裁成互不重叠（先到先得），避免同一段时间被重复累加。

    AW 正常不会给出重叠的窗口事件，但 heartbeat 合并边界偶尔会；这里用一次扫掠兜底，
    复杂度 O(n log n)，不会因为一天几千条事件而变慢。
    """
    out = []
    covered_until = None
    for s, e, data in sorted(spans, key=lambda x: (x[0], x[1])):
        if covered_until is not None and s < covered_until:
            s = covered_until
        if e > s:
            out.append((s, e, data))
            covered_until = e if covered_until is None else max(covered_until, e)
    return out



def merge_spans(spans: list, gap_sec: float = 0) -> list:
    """合并重叠/相邻区间（空洞 ≤ gap_sec 也算连续）；结果升序，data 置 None。"""
    items = sorted((s, e) for s, e, _d in spans)
    out: list[list] = []
    for s, e in items:
        if out and s <= out[-1][1] + dt.timedelta(seconds=gap_sec):
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e, None) for s, e in out]


def intersect(a_spans: list, b_spans: list) -> list:
    """两族区间的交集（保留 a 的 data，结果升序）。b 内部先合并，避免重复计算。"""
    b = merge_spans(b_spans)
    out = []
    j = 0
    for s, e, data in sorted(a_spans, key=lambda x: x[0]):
        while j < len(b) and b[j][1] <= s:
            j += 1
        k = j
        while k < len(b) and b[k][0] < e:
            lo, hi = max(s, b[k][0]), min(e, b[k][1])
            if hi > lo:
                out.append((lo, hi, data))
            if b[k][1] >= e:
                break
            k += 1
    return out


def active_spans(window_events: list, afk_events: list, day: dt.date,
                 settings: dict | None = None) -> list:
    """当天"真的在电脑前 + 有窗口"的区间：窗口事件 ∩ not-afk。"""
    lo, hi = utils.day_bounds(day)
    windows = [c for c in (clip(span_of(e), lo, hi) for e in (window_events or [])) if c]
    if not windows:
        return []
    not_afk = []
    for e in afk_events or []:
        sp = clip(span_of(e), lo, hi)
        if sp and str((sp[2].get("status") or "")).strip() == "not-afk":
            not_afk.append(sp)
    if not not_afk:
        return []                        # 没有 AFK 数据 → 无法判断"在不在"，宁可不计
    return intersect(non_overlapping(windows), not_afk)



def _match(rule: dict, app: str, title: str, url: str) -> bool:
    """一条规则是否命中：给出的字段必须全部命中（AND）。"""
    values = {"url": url or "", "title": title or "", "app": app or ""}
    given = [(key, rule.get(key)) for key in ("url", "title", "app") if rule.get(key)]
    if not given:
        return False
    for key, pattern in given:
        try:
            if not re.search(str(pattern), values[key], re.IGNORECASE):
                return False
        except re.error:
            return False                 # 规则写错不影响整体聚合，只是不命中
    return True


def categorize(app: str = "", title: str = "", url: str = "", rules: list | None = None) -> str:
    """按规则给一条活动定类别；第一个命中的规则生效，都没有 → 未分类。"""
    for rule in rules if rules is not None else DEFAULT_RULES:
        if not isinstance(rule, dict):
            continue
        category = str(rule.get("category") or "").strip()
        if category and _match(rule, app, title, url):
            return category
    return UNCATEGORIZED


def domain_of(url: str) -> str:
    """URL → 域名（小写、去掉 www.）；非 http(s)（chrome://、about:）返回空串。"""
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return ""
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _title_key(title: str) -> str:
    """标题归一：压缩空白并截断（避免把同一页面拆成几百个碎片）。"""
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    return text[:80]


def _minutes(seconds: float) -> float:
    return round(seconds / 60.0, 1)


def _top(mapping: dict, key: str, limit: int, extra=None) -> list:
    """{名称: 秒} → 按时长降序的列表（extra 回调可补充字段）。"""
    items = sorted(mapping.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    out = []
    for name, seconds in items:
        row = {key: name, "min": _minutes(seconds)}
        if extra:
            row.update(extra(name) or {})
        out.append(row)
    return out


def aggregate_day(day: dt.date, window_events: list, afk_events: list,
                  web_events: list | None = None, settings: dict | None = None) -> dict:
    """聚合某一天 → 每日摘要（结构见 docs §13.2）。"""
    st = merged_settings(settings)
    rules = st.get("rules")
    if rules is None:                    # 配置里没写 rules 才用默认；显式 [] = 不分类
        rules = DEFAULT_RULES
    ignored = [str(a).lower() for a in (st.get("ignored_apps") or []) if str(a).strip()]

    spans = active_spans(window_events, afk_events, day, st)

    app_sec: dict[str, float] = {}
    title_sec: dict[str, float] = {}
    cat_sec: dict[str, float] = {}
    total_sec = excluded_sec = 0.0
    first_ts = last_ts = None

    for start, end, data in spans:
        seconds = (end - start).total_seconds()
        app = str(data.get("app") or "").strip() or "(未知)"
        raw_title = str(data.get("title") or "").strip()
        title = "" if raw_title == "excluded" else _title_key(raw_title)
        if any(name and name in app.lower() for name in ignored):
            excluded_sec += seconds
            continue
        total_sec += seconds
        app_sec[app] = app_sec.get(app, 0.0) + seconds
        category = categorize(app=app, title=title, rules=rules)
        cat_sec[category] = cat_sec.get(category, 0.0) + seconds
        if title:
            title_sec[title] = title_sec.get(title, 0.0) + seconds
        if first_ts is None or start < first_ts:
            first_ts = start
        if last_ts is None or end > last_ts:
            last_ts = end

    # ---- 网站（web.tab.current）：与活跃区间求交，后台标签页不算 ----
    site_sec: dict[str, float] = {}
    site_cat: dict[str, dict[str, float]] = {}
    site_meta: dict[str, dict] = {}
    page_sec: dict[tuple, float] = {}
    if web_events:
        lo, hi = utils.day_bounds(day)
        web_spans = [c for c in (clip(span_of(e), lo, hi) for e in web_events) if c]
        for start, end, data in intersect(web_spans, [(s, e, None) for s, e, _ in spans]):
            url = str(data.get("url") or "")
            dom = domain_of(url)
            if not dom:
                continue
            seconds = (end - start).total_seconds()
            title = _title_key(data.get("title"))
            category = categorize(title=title, url=url, rules=rules)
            site_sec[dom] = site_sec.get(dom, 0.0) + seconds
            bucket = site_cat.setdefault(dom, {})
            bucket[category] = bucket.get(category, 0.0) + seconds
            meta = site_meta.setdefault(dom, {"audible": False, "title": ""})
            meta["audible"] = meta["audible"] or bool(data.get("audible"))
            if not meta["title"]:
                meta["title"] = title
            key = (dom, title or "(无标题)")
            page_sec[key] = page_sec.get(key, 0.0) + seconds

    # 域名类别取"占比最大的类别"，避免一条偶然命中的规则带偏整站归类
    site_categories = {dom: max(cats.items(), key=lambda kv: kv[1])[0]
                       for dom, cats in site_cat.items() if cats}

    return {
        "day": day.isoformat(),
        "active_min": _minutes(total_sec),
        "excluded_min": _minutes(excluded_sec),
        "first_ts": first_ts.astimezone().isoformat(timespec="seconds") if first_ts else None,
        "last_ts": last_ts.astimezone().isoformat(timespec="seconds") if last_ts else None,
        "apps": _top(app_sec, "app", 10,
                     lambda name: {"category": categorize(app=name, rules=rules)}),
        "categories": _top(cat_sec, "category", 20),
        "sites": [dict({"domain": dom, "min": _minutes(sec),
                        "category": site_categories.get(dom, UNCATEGORIZED)},
                       **site_meta[dom])
                  for dom, sec in sorted(site_sec.items(), key=lambda kv: kv[1],
                                         reverse=True)[:10]],
        "pages": [{"domain": dom, "title": title, "min": _minutes(sec)}
                  for (dom, title), sec in sorted(page_sec.items(), key=lambda kv: kv[1],
                                                  reverse=True)[:10]],
        "titles": _top(title_sec, "title", 10),
        "source": "activitywatch",
        "imported_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def pick_buckets(bucket_infos: list, host: str = "") -> dict:
    """从桶列表挑出 window / afk / web 三个桶 id（找不到为 None）。

    优先按 ``type`` 精确匹配，其次按 id 前缀；给了 host 则优先挑该主机的桶。
    """
    def choose(btype: str, prefix: str):
        cands = [b for b in (bucket_infos or [])
                 if b.get("type") == btype or str(b.get("id", "")).startswith(prefix)]
        if not cands:
            return None
        if host:
            for b in cands:
                if str(b.get("id", "")).endswith(f"_{host}"):
                    return str(b["id"])
        return str(sorted(cands, key=lambda b: str(b.get("id")))[0]["id"])

    return {
        "window": choose("currentwindow", "aw-watcher-window"),
        "afk": choose("afkstatus", "aw-watcher-afk"),
        "web": choose("web.tab.current", "aw-watcher-web"),
    }

