"""点数线统计纯函数测试：stats.py 的 percentile 与 calc_baseline。"""

import datetime as dt
import unittest

import stats


class PercentileTest(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(stats.percentile([5], 0.4), 5.0)

    def test_even_linear(self):
        # 0,10 的 40% → 0 + (10-0)*0.4 = 4.0
        self.assertEqual(stats.percentile([0, 10], 0.4), 4.0)

    def test_sorted_equivalent(self):
        self.assertEqual(stats.percentile([3, 1, 2], 0.5), stats.percentile([1, 2, 3], 0.5))


class BaselineTest(unittest.TestCase):
    def test_no_data(self):
        r = stats.calc_baseline([0, 0, 0])
        self.assertEqual(r["baseline"], 0.0)
        self.assertEqual(r["method"], "no_data")
        self.assertEqual(r["percentile"], 0.8)

    def test_default_percentile_is_80(self):
        """v2.7 起点数线取 80% 分位（不是 40%）。"""
        self.assertEqual(stats.BASELINE_PERCENTILE, 0.8)
        self.assertEqual(stats.calc_baseline([1, 2, 3])["percentile"], 0.8)

    def test_few_days_direct(self):
        """有效天数 ≤10 → 直接 80% 分位，不剔除。"""
        # 5 个有效天：[1,2,3,4,5]，80% 分位线性插值
        r = stats.calc_baseline([0, 1, 0, 2, 3, 4, 5, 0])
        self.assertEqual(r["method"], "direct")
        self.assertEqual(r["active_days"], 5)
        self.assertEqual(r["trimmed_low"], 0)
        # 排好 1,2,3,4,5 => k=(5-1)*.8=3.2 => 4+(5-4)*.2=4.2
        self.assertAlmostEqual(r["baseline"], 4.2, places=2)

    def test_many_days_trims_extremes(self):
        """有效天数 >10 → 各剔除最低/最高 10%，剩 80% 分位。"""
        # 15 个有效天：0~14 里最低1个、最高1个被剔（15*0.1=1.5→1）
        values = [i for i in range(1, 16)]  # 1..15，15个
        r = stats.calc_baseline(values)
        self.assertEqual(r["method"], "trimmed")
        self.assertEqual(r["trimmed_low"], 1)
        self.assertEqual(r["trimmed_high"], 1)
        self.assertEqual(r["used_days"], 13)
        # 剔掉 1 和 15，剩 2..14（13个），80% 分位：k=12*.8=9.6
        # sorted = 2,3,...,14；idx9=11, idx10=12 → 11+(12-11)*.6=11.6
        self.assertAlmostEqual(r["baseline"], 11.6, places=2)

    def test_zero_days_excluded_from_active(self):
        """0 分天不进样本。"""
        r = stats.calc_baseline([0, 0, 5, 0, 5, 0])
        self.assertEqual(r["active_days"], 2)
        self.assertEqual(r["method"], "direct")
        self.assertEqual(r["baseline"], 5.0)


class StreakTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(stats.calc_streaks(set()), {"current_streak": 0, "longest_streak": 0})

    def test_current_extends_from_today(self):
        today = dt.date.today()
        days = {today, today - dt.timedelta(days=1), today - dt.timedelta(days=2)}
        r = stats.calc_streaks(days)
        self.assertEqual(r["current_streak"], 3)
        self.assertEqual(r["longest_streak"], 3)

    def test_today_missing_counts_from_yesterday(self):
        """今天还没打卡不算断：从昨天往前数。"""
        today = dt.date.today()
        yesterday = today - dt.timedelta(days=1)
        days = {yesterday, yesterday - dt.timedelta(days=1), yesterday - dt.timedelta(days=2)}
        r = stats.calc_streaks(days)
        self.assertEqual(r["current_streak"], 3)

    def test_broken_streak(self):
        """昨天没打 → current 归 0；longest 记录历史最长。"""
        today = dt.date.today()
        d1, d2 = today - dt.timedelta(days=4), today - dt.timedelta(days=3)
        d3, d4 = today - dt.timedelta(days=2), today - dt.timedelta(days=1)
        # 昨天(d1? 不)——构造：前天没打，今天打了(只1)
        days = {d1, d2, d3, today}   # 前天 d3? 不，明确：{今天, 4天前,5天前}
        # 简化：今天单独 + 更早两连
        days2 = {today, today - dt.timedelta(days=5), today - dt.timedelta(days=6)}
        r = stats.calc_streaks(days2)
        self.assertEqual(r["current_streak"], 1)
        self.assertEqual(r["longest_streak"], 2)

    def test_filter_and_summarize(self):
        day_points = {dt.date(2026, 9, 1): 3, dt.date(2026, 9, 5): 2, dt.date(2026, 8, 20): 5}
        cut = stats.filter_day_points(day_points, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        self.assertEqual(set(cut.keys()), {dt.date(2026, 9, 1), dt.date(2026, 9, 5)})
        s = stats.summarize_day_points(cut)
        self.assertEqual(s["total_days"], 2)
        self.assertEqual(s["period_points"], 5)


if __name__ == "__main__":
    unittest.main()