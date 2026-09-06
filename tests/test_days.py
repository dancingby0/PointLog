"""日期总览与贡献日历 API 测试：/api/days 与 /api/calendar。"""

import datetime as dt
import unittest

from base import ApiTestCase
from utils import date_of


class DaysApiTest(ApiTestCase):
    """日期列表（/api/days）与贡献日历（/api/calendar）。"""

    def test_days_overview(self):
        """/api/days 返回当月逐日数据：点数归总 + 感想标记。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        self.client.post("/api/entries", json={
            "content": "今天的活",
            "points": 3,
            "ts": dt.datetime.combine(today, dt.time(12, 0)).astimezone().isoformat(),
        })
        self.client.put("/api/notes", json={"day": today.isoformat(), "content": "今天的感想"})
        r = self.client.get("/api/days")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        days = body["days"]
        # 返回当月：第一天是 1 号
        self.assertEqual(days[0]["date"], f"{today.year}-{today.month:02d}-01")
        by_date = {d["date"]: d for d in days}
        self.assertEqual(by_date[today.isoformat()]["points"], 3)
        self.assertTrue(by_date[today.isoformat()]["has_note"])
        self.assertTrue(by_date[today.isoformat()]["is_today"])
        # 有未来标记
        self.assertIn("is_future", by_date[today.isoformat()])

    def test_days_by_month_param(self):
        """?month=YYYY-MM 能取指定历史月份。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        prev_month_end = today.replace(day=1) - dt.timedelta(days=1)  # 上月末
        r = self.client.get(f"/api/days?month={prev_month_end.strftime('%Y-%m')}")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        # 该月最后一天即是 prev_month_end
        self.assertEqual(body["days"][-1]["date"], prev_month_end.isoformat())

    def test_days_future_month_rejected(self):
        r = self.client.get("/api/days?month=2099-01")
        self.assertEqual(r.status_code, 400)

    def test_calendar_levels(self):
        """贡献日历：默认只返回"当年 1月1日→今天"，每日点数与五档强度正确。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        self.client.post("/api/entries", json={
            "content": "今天一条",
            "points": 1,
            "ts": dt.datetime.combine(today, dt.time(12, 0)).astimezone().isoformat(),
        })
        self.client.post("/api/entries", json={
            "content": "今天第二条",
            "points": 2,
            "ts": dt.datetime.combine(today, dt.time(13, 0)).astimezone().isoformat(),
        })
        r = self.client.get("/api/calendar")
        self.assertEqual(r.status_code, 200)
        arr = r.get_json()
        # 从当年 1月1日 到 今天
        self.assertEqual(arr[0]["date"], f"{today.year}-01-01")
        self.assertEqual(arr[-1]["date"], today.isoformat())
        by_date = {x["date"]: x for x in arr}
        today_info = by_date[today.isoformat()]
        self.assertEqual(today_info["points"], 3)   # 1 + 2
        self.assertEqual(today_info["level"], 2)    # 3 点 → 2 档

    def test_calendar_year_switch(self):
        """?year 指定历史年份时，返回该年完整窗口。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        prev_year = today.year - 1
        # 去年某天有记录
        past_day = dt.date(prev_year, 6, 15)
        self.client.post("/api/entries", json={
            "content": "去年的活",
            "points": 4,
            "ts": dt.datetime.combine(past_day, dt.time(10, 0)).astimezone().isoformat(),
        })
        r = self.client.get(f"/api/calendar?year={prev_year}")
        self.assertEqual(r.status_code, 200)
        arr = r.get_json()
        # 历史年：完整 1月1日 → 12月31日
        self.assertEqual(arr[0]["date"], f"{prev_year}-01-01")
        self.assertEqual(arr[-1]["date"], f"{prev_year}-12-31")
        by_date = {x["date"]: x for x in arr}
        self.assertEqual(by_date[past_day.isoformat()]["points"], 4)
        self.assertEqual(by_date[past_day.isoformat()]["level"], 3)  # 4 点 → 3 档

    def test_calendar_bad_year(self):
        """非法 year 应返回 400。"""
        self.assertEqual(self.client.get("/api/calendar?year=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/calendar?year=2100").status_code, 400)

    def test_points_line(self):
        """点数线：有效天 ≤10 直接 40% 分位；窗口固定最近60天。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        # 造 5 个有效打卡日（1..5 分），分布在近几天
        for i, pts in enumerate([1, 2, 3, 4, 5]):
            day = today - dt.timedelta(days=i)
            self.client.post("/api/entries", json={
                "content": f"line-{pts}",
                "points": pts,
                "ts": dt.datetime.combine(day, dt.time(12, 0)).astimezone().isoformat(),
            })
        r = self.client.get("/api/line")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["method"], "direct")
        self.assertEqual(body["active_days"], 5)
        self.assertEqual(body["window_days"], 60)
        # 1,2,3,4,5 → 40% 线性 = 2.6
        self.assertAlmostEqual(body["baseline"], 2.6, places=2)

    def test_points_line_trim_when_many_days(self):
        """有效天 >10 → 各剔最低/最高 10% 后取 40% 分位。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        # 造 15 个有效打卡日（1..15 分）
        for pts in range(1, 16):
            day = today - dt.timedelta(days=pts - 1)
            self.client.post("/api/entries", json={
                "content": f"line-{pts}",
                "points": pts,
                "ts": dt.datetime.combine(day, dt.time(12, 0)).astimezone().isoformat(),
            })
        r = self.client.get("/api/line")
        body = r.get_json()
        self.assertEqual(body["method"], "trimmed")
        self.assertEqual(body["trimmed_low"], 1)
        self.assertEqual(body["trimmed_high"], 1)
        self.assertEqual(body["used_days"], 13)
        # 剔 1 和 15，剩 2..14，40% 线性插值 = 6.8
        self.assertAlmostEqual(body["baseline"], 6.8, places=2)


if __name__ == "__main__":
    unittest.main()