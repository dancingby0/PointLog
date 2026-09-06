"""点数线统计纯函数（无 Flask 依赖，可独立测试）。

点数线 = 40% 分位数，剔极值版：
1. 样本取最近窗口内"打过卡的天"的点数（0 分天不进样本）
2. 有效天数 ≤ 10 → 直接取 40% 分位数
3. 有效天数 > 10 → 各剔除点数最低/最高 10% 的天，剩余再取 40% 分位数
"""

import math
import datetime as dt


def percentile(values: list, p: float) -> float:
    """线性插值分位数（numpy.percentile 的 linear 方式），p 取值 [0, 1]。"""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p
    low = math.floor(k)
    high = math.ceil(k)
    if low == high:
        return float(s[low])
    frac = k - low
    return s[low] + (s[high] - s[low]) * frac


def calc_baseline(
    points_in_window: list,
    trim_ratio: float = 0.10,
    p: float = 0.40,
    small_n: int = 10,
) -> dict:
    """计算点数线。

    参数：
        points_in_window: 最近窗口内"每天的点数"列表（可能含 0），顺序不限。
        trim_ratio: 各端剔除比例（0.10 = 各 10%）。
        p: 分位数（0.40 = 40%）。
        small_n: 有效天数小于等于该值时不做剔除。

    返回：含 baseline 与计算过程（便于前端展示/调试）。
    """
    active = [x for x in points_in_window if x > 0]
    n = len(active)

    if n == 0:
        return {
            "baseline": 0.0,
            "method": "no_data",
            "window_days": len(points_in_window),
            "active_days": 0,
            "trimmed_low": 0,
            "trimmed_high": 0,
            "used_days": 0,
        }

    if n <= small_n:
        values = active
        method = "direct"
        trimmed_low = trimmed_high = 0
    else:
        k = int(n * trim_ratio)  # 向下取整，保守剔除
        s = sorted(active)
        values = s[k: n - k] if k > 0 else s
        method = "trimmed"
        trimmed_low = trimmed_high = k
        if not values:  # 防御：剔过头时退化为直接用中段（实际 k<n/2 不会发生）
            values = active

    return {
        "baseline": round(percentile(values, p), 2),
        "method": method,
        "window_days": len(points_in_window),
        "active_days": n,
        "trimmed_low": trimmed_low,
        "trimmed_high": trimmed_high,
        "used_days": len(values),
    }


# ---------- 坚持度（streak） ----------

def calc_streaks(active_dates: set) -> dict:
    """根据"打过卡的日期集合"计算连续情况。

    参数：active_dates —— 全部打卡日（datetime.date 集合）。
    返回 {current_streak, longest_streak}。
    连续以"今天"为基准：今天有打则从今天连，否则从昨天往前数（今天还没打不算断）。
    """
    if not active_dates:
        return {"current_streak": 0, "longest_streak": 0}

    today = dt.date.today()

    # 最长连续：遍历所有日期计算
    dates = sorted(active_dates)
    longest = 1
    run = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    # 当前连续：从今天（若没打则昨天）往前数
    anchor = today if today in active_dates else today - dt.timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in active_dates:
        current += 1
        cursor -= dt.timedelta(days=1)
    return {"current_streak": current, "longest_streak": longest}


def filter_day_points(
    day_points: dict,
    range_start: dt.date,
    range_end: dt.date,
) -> dict:
    """从 {date: 总点数} 中截取 [range_start, range_end] 内的部分。

    调用方负责把打卡 ts 按凌晨4点规则归到 date。
    """
    return {d: p for d, p in day_points.items() if range_start <= d <= range_end}


def summarize_day_points(day_points: dict) -> dict:
    """对 {date: 点数} 汇总：打卡天数 + 总点数。"""
    return {
        "total_days": len(day_points),
        "period_points": sum(day_points.values()),
    }