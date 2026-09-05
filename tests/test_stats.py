"""点数线统计纯函数测试：stats.py 的 percentile 与 calc_baseline。"""

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

    def test_few_days_direct(self):
        """有效天数 ≤10 → 直接 40% 分位，不剔除。"""
        # 5 个有效天：[1,2,3,4,5]，40% 分位线性插值
        r = stats.calc_baseline([0, 1, 0, 2, 3, 4, 5, 0])
        self.assertEqual(r["method"], "direct")
        self.assertEqual(r["active_days"], 5)
        self.assertEqual(r["trimmed_low"], 0)
        # 0,1,2,3,4 的 40%? —— 排好: 1,2,3,4,5 => k=(5-1)*.4=1.6 => 2+(3-2)*.6=2.6
        self.assertAlmostEqual(r["baseline"], 2.6, places=2)

    def test_many_days_trims_extremes(self):
        """有效天数 >10 → 各剔除最低/最高 10%，剩 40% 分位。"""
        # 15 个有效天：0~14 里最低1个、最高1个被剔（15*0.1=1.5→1）
        values = [i for i in range(1, 16)]  # 1..15，15个
        r = stats.calc_baseline(values)
        self.assertEqual(r["method"], "trimmed")
        self.assertEqual(r["trimmed_low"], 1)
        self.assertEqual(r["trimmed_high"], 1)
        self.assertEqual(r["used_days"], 13)
        # 剔掉 1 和 15，剩 2..14（13个），40% 分位：k=12*.4=4.8 → 2..14中 idx
        # sorted = 2,3,...,14；k=4.8 → 6+(7-6)*.8=6.8
        self.assertAlmostEqual(r["baseline"], 6.8, places=2)

    def test_zero_days_excluded_from_active(self):
        """0 分天不进样本。"""
        r = stats.calc_baseline([0, 0, 5, 0, 5, 0])
        self.assertEqual(r["active_days"], 2)
        self.assertEqual(r["method"], "direct")
        self.assertEqual(r["baseline"], 5.0)


if __name__ == "__main__":
    unittest.main()