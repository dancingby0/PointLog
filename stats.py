"""点数线统计纯函数（无 Flask 依赖，可独立测试）。

点数线 = 40% 分位数，剔极值版：
1. 样本取最近窗口内"打过卡的天"的点数（0 分天不进样本）
2. 有效天数 ≤ 10 → 直接取 40% 分位数
3. 有效天数 > 10 → 各剔除点数最低/最高 10% 的天，剩余再取 40% 分位数
"""

import math


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