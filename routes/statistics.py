"""统计 API：坚持与概况汇总（子迭代1）。

GET /api/stats/summary?range=week|month|year|all
返回：打卡天数、期间总点数、当前/最长连续、感想天数。
"""

import datetime as dt

from flask import Blueprint, jsonify, request

import config
import data
import stats
from utils import clean_categories, date_of, day_points_of, parse_ts

bp = Blueprint("statistics", __name__, url_prefix="/api/stats")


def _parse_range(name: str, today: dt.date):
    """把 range 名称换算为 [start, end]。"""
    ranges = {
        "week": (today - dt.timedelta(days=6), today),   # 近 7 天
        "month": (today.replace(day=1), today),
        "year": (today.replace(month=1, day=1), today),
        "all": (dt.date(1970, 1, 1), today),
    }
    if name not in ranges:
        raise ValueError("range 应为 week/month/year/all")
    return ranges[name]


def _day_points_of(entries: list) -> dict:
    """把打卡 ts 按凌晨4点规则归到 {date: 点数}（0 点记录不计入打卡日）。"""
    return day_points_of(entries)


def _day_points_map_if_present(d: dict) -> dict:
    """统一入口：从档案 entries 汇总 daily {date: points}。"""
    return _day_points_of(d.get("entries", []))


@bp.get("/summary")
def summary():
    try:
        range_name = request.args.get("range", "month")
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        start, end = _parse_range(range_name, today)
    except ValueError:
        return jsonify({"error": "range 应为 week/month/year/all"}), 400

    d = data.load(config.CURRENT_PROFILE)
    day_points = _day_points_map_if_present(d)
    in_range = stats.filter_day_points(day_points, start, end)
    summarized = stats.summarize_day_points(in_range)

    # 感想天数：范围内写了感想的天数（YYYY-MM-DD 字典序即时间序，可直接比较字符串）
    notes = d.get("daily_notes", {})
    s_iso, e_iso = start.isoformat(), end.isoformat()
    notes_days = sum(1 for date_str in notes if s_iso <= str(date_str) <= e_iso)

    # 连续天数基于"全部打卡日"（不限定范围，因为 streak 是全局连续性）
    streaks = stats.calc_streaks(set(day_points.keys()))

    # 近 30 天每日点数（供前端"打卡格子"判断当天是否真打过卡）
    recent = []
    for i in range(29, -1, -1):
        day = today - dt.timedelta(days=i)
        recent.append({"date": day.isoformat(), "points": day_points.get(day, 0)})

    return jsonify({
        "range": range_name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_days": summarized["total_days"],
        "period_points": summarized["period_points"],
        "notes_days": notes_days,
        "current_streak": streaks["current_streak"],
        "longest_streak": streaks["longest_streak"],
        "recent": recent,
    })


@bp.get("/assets")
def asset_trend():
    """收支趋势：近 N 个月每月的 {收入, 支出}（元）。转账/校准不计。?months=12。"""
    try:
        months = int(request.args.get("months", 12))
        months = max(3, min(months, 24))
    except ValueError:
        return jsonify({"error": "months 应为整数"}), 400

    now = dt.datetime.now().astimezone()
    g = data.load_global()

    # 生成近 months 个月 (year, month) 序列（新→旧再反转）
    # 注：资产流水按"自然月"聚合（ts 直接取 %Y-%m），故桶上限用自然月
    buckets = []
    y, m = now.year, now.month
    for _ in range(months):
        buckets.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    buckets.reverse()
    keys = [f"{y:04d}-{m:02d}" for y, m in buckets]

    # 预聚合: month_prefix -> {"income": 分, "expense": 分}
    agg = {k: {"income": 0, "expense": 0} for k in keys}
    for t in g.get("txs", []):
        tx_type = t.get("type")
        if tx_type not in ("income", "expense"):
            continue
        try:
            ts = str(t.get("ts", ""))
            raw = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
            parsed = dt.datetime.fromisoformat(raw)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            month_prefix = parsed.strftime("%Y-%m")
        except (ValueError, TypeError):
            continue
        if month_prefix not in agg:
            continue
        try:
            fen = int(t.get("amount_fen", 0))
        except (ValueError, TypeError):
            continue
        agg[month_prefix][tx_type] += fen

    out = []
    for key in keys:
        y, m = int(key[:4]), int(key[5:7])
        out.append({
            "month": key,
            "label": f"{y}年{m}月",
            "income": round(agg[key]["income"] / 100, 2),
            "expense": round(agg[key]["expense"] / 100, 2),
        })
    return jsonify(out)


@bp.get("/trend")
def trend():
    """月度趋势：近 N 个月每月的 {点数, 打卡天数, 感想天数}。?months=12。"""
    try:
        months = int(request.args.get("months", 12))
        months = max(3, min(months, 24))
    except ValueError:
        return jsonify({"error": "months 应为整数"}), 400

    now = dt.datetime.now().astimezone()
    today = date_of(now)
    d = data.load(config.CURRENT_PROFILE)
    day_points = _day_points_map_if_present(d)
    notes = d.get("daily_notes", {})

    # 生成近 months 个月的 (year, month)
    buckets = []
    y, m = today.year, today.month
    for _ in range(months):
        buckets.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    buckets.reverse()

    out = []
    for y, m in buckets:
        start = dt.date(y, m, 1)
        # 当月最后一天
        if m == 12:
            end = dt.date(y + 1, 1, 1) - dt.timedelta(days=1)
        else:
            end = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
        # 未来月截断到今天
        if start > today:
            continue
        end = min(end, today)

        month_points = 0
        check_days = set()
        for day, pts in day_points.items():
            if start <= day <= end:
                month_points += pts
                check_days.add(day)
        # 感想天数：该月内 YYYY-MM- 前缀匹配
        prefix = f"{y:04d}-{m:02d}-"
        note_days = sum(1 for ds in notes if str(ds).startswith(prefix))

        out.append({
            "month": f"{y:04d}-{m:02d}",
            "label": f"{y}年{m}月",
            "points": month_points,
            "days": len(check_days),
            "notes_days": note_days,
        })
    return jsonify(out)


# 时段分桶（按打卡时刻的小时）
PERIOD_BUCKETS = [
    ("清晨", (5, 12)),     # 5:00–11:59
    ("下午", (12, 18)),    # 12:00–17:59
    ("晚上", (18, 23)),    # 18:00–22:59
    ("深夜", (23, 5)),     # 23:00–4:59（跨零点）
]


def _period_label(hour: int) -> str:
    for label, (lo, hi) in PERIOD_BUCKETS:
        if lo < hi:
            if lo <= hour < hi:
                return label
        else:  # 跨零点：23–5
            if hour >= lo or hour < hi:
                return label
    return "深夜"


WEEKDAY_ORDER = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _round_points(value: float):
    """均摊后的点数：整数值还原为 int（输出更干净），否则保留 2 位小数。"""
    return int(value) if float(value).is_integer() else round(value, 2)


@bp.get("/distribution")
def distribution():
    """结构与规律分布：类别占比 / 星期分布 / 时段分布。

    类别支持多选：一条记录命中多个类别时，其点数在这些类别间**均摊**，
    保证"类别维度合计 = 期间总点数"（与资产标签占比同一约定）。

    GET /api/stats/distribution?range=week|month|year|all
    """
    try:
        range_name = request.args.get("range", "month")
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        start, end = _parse_range(range_name, today)
    except ValueError:
        return jsonify({"error": "range 应为 week/month/year/all"}), 400

    d = data.load(config.CURRENT_PROFILE)

    # 统计范围内逐条打卡（保留时刻与类别）
    tag_points = {}       # tag -> {points, count}
    weekday_points = {}   # 周几 -> points
    period_points = {}    # period -> points

    entries = d.get("entries", [])
    for e in entries:
        try:
            t = parse_ts(e["ts"])
        except (ValueError, TypeError):
            continue
        day = date_of(t)
        if not (start <= day <= end):
            continue
        pts = int(e.get("points", 0))

        # 时段（按打卡时刻的小时分桶）
        period_points[_period_label(t.hour)] = period_points.get(_period_label(t.hour), 0) + pts

        # 星期分布：按点数累计（真实反映投入量）
        wd = WEEKDAY_ORDER[day.weekday()]
        weekday_points[wd] = weekday_points.get(wd, 0) + pts

        # 类别（可多选）：一条记录命中多个类别时，点数在这些类别间均摊
        cats = clean_categories(e.get("category"))
        if cats:
            share = pts / len(cats)
            for cat in cats:
                item = tag_points.setdefault(cat, {"points": 0.0, "count": 0})
                item["points"] += share
                item["count"] += 1

    tags = [{"tag": k, "points": _round_points(v["points"]), "count": v["count"]}
            for k, v in sorted(tag_points.items(),
                               key=lambda kv: kv[1]["points"], reverse=True)]
    weekdays = [{"label": w, "points": weekday_points.get(w, 0)} for w in WEEKDAY_ORDER]
    periods = [{"label": l, "points": period_points.get(l, 0)}
               for l, _ in PERIOD_BUCKETS]

    return jsonify({
        "range": range_name,
        "tags": tags,
        "weekdays": weekdays,
        "periods": periods,
    })


# ================= 资产统计分析（v2.4） =================

GRANULARITIES = ("day", "month", "year")
MAX_POINTS = 400          # 单次分析最多时间点数（防止按日跨多年导致图爆掉）


def _period_key(d: dt.date, gran: str) -> str:
    if gran == "day":
        return d.isoformat()
    if gran == "month":
        return f"{d.year:04d}-{d.month:02d}"
    return f"{d.year:04d}"


def _bucket_label(key: str, gran: str) -> str:
    if gran == "day":
        return key[5:]            # 09-15
    if gran == "month":
        return key                # 2026-09
    return f"{key}年"


def _period_steps(start: dt.date, end: dt.date, gran: str) -> list:
    """生成 [start, end] 内按粒度的完整时间点（用于补齐无流水的空档）。"""
    out = []
    if gran == "day":
        cur = start
        while cur <= end:
            out.append(cur)
            cur += dt.timedelta(days=1)
    elif gran == "month":
        cur = start.replace(day=1)
        while cur <= end:
            out.append(cur)
            cur = dt.date(cur.year + 1, 1, 1) if cur.month == 12 else dt.date(cur.year, cur.month + 1, 1)
    else:
        cur = start.replace(month=1, day=1)
        while cur <= end:
            out.append(cur)
            cur = dt.date(cur.year + 1, 1, 1)
    return out


def _csv(value) -> list:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


@bp.get("/asset-analysis")
def asset_analysis():
    """资产统计分析：时间序列（收入/支出）+ 标签占比。

    查询参数：
      from / to     日期区间 YYYY-MM-DD（含端点，按本地日期；缺省=近 365 天）
      granularity   day | month | year（默认 month）
      accounts      账户 id 多选（逗号分隔，空=不限）
      tags          标签多选（命中任一；空=不限）
      flow          income | expense | both（默认 both）
    说明：转账与校准不计入；一笔多标签按标签数量均摊，无标签计入"未分类"。
    """
    now = dt.datetime.now().astimezone()
    today = date_of(now)
    try:
        d_from = dt.date.fromisoformat(request.args.get("from")) if request.args.get("from") \
            else today - dt.timedelta(days=364)
        d_to = dt.date.fromisoformat(request.args.get("to")) if request.args.get("to") else today
    except ValueError:
        return jsonify({"error": "日期格式应为 YYYY-MM-DD"}), 400
    if d_from > d_to:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400

    gran = request.args.get("granularity") or "month"
    if gran not in GRANULARITIES:
        return jsonify({"error": "granularity 应为 day/month/year"}), 400
    flow = request.args.get("flow") or "both"
    if flow not in ("income", "expense", "both"):
        return jsonify({"error": "flow 应为 income/expense/both"}), 400

    accounts = _csv(request.args.get("accounts"))
    tags = _csv(request.args.get("tags"))

    steps = _period_steps(d_from, d_to, gran)
    if len(steps) > MAX_POINTS:
        return jsonify({
            "error": f"时间点过多（{len(steps)}），请缩小日期范围或改用更粗的粒度"
        }), 400

    buckets = {_period_key(p, gran): {"income": 0.0, "expense": 0.0} for p in steps}
    tag_income = {}
    tag_expense = {}

    g = data.load_global()
    for t in g["txs"]:
        ttype = t.get("type")
        if ttype not in ("income", "expense"):
            continue                      # 转账/校准不计入收支统计
        if flow != "both" and ttype != flow:
            continue
        if accounts and t.get("account_id") not in accounts:
            continue
        try:
            day = parse_ts(t.get("ts")).astimezone().date()
        except (ValueError, TypeError):
            continue
        if not (d_from <= day <= d_to):
            continue
        ttags = [str(x).strip() for x in (t.get("tags") or []) if str(x).strip()]
        if tags and not (set(ttags) & set(tags)):
            continue

        amount = int(t.get("amount_fen", 0)) / 100.0
        key = _period_key(day, gran)
        if key in buckets:
            buckets[key][ttype] += amount

        dist = tag_income if ttype == "income" else tag_expense
        if ttags:                          # 多标签均摊，保证标签维度合计=总额
            share = amount / len(ttags)
            for tg in ttags:
                dist[tg] = dist.get(tg, 0.0) + share
        else:
            dist["未分类"] = dist.get("未分类", 0.0) + amount

    def _dist(m: dict) -> list:
        return [{"tag": k, "amount": round(v, 2)}
                for k, v in sorted(m.items(), key=lambda kv: kv[1], reverse=True)]

    series = [{
        "period": k,
        "label": _bucket_label(k, gran),
        "income": round(v["income"], 2),
        "expense": round(v["expense"], 2),
    } for k, v in buckets.items()]

    total_income = round(sum(v["income"] for v in buckets.values()), 2)
    total_expense = round(sum(v["expense"] for v in buckets.values()), 2)
    return jsonify({
        "from": d_from.isoformat(),
        "to": d_to.isoformat(),
        "granularity": gran,
        "flow": flow,
        "series": series,
        "tag_income": _dist(tag_income),
        "tag_expense": _dist(tag_expense),
        "totals": {"income": total_income, "expense": total_expense,
                   "net": round(total_income - total_expense, 2)},
    })