"""日期总览与贡献日历 API 测试：/api/days 与 /api/calendar。"""

import datetime as dt
import unittest

from base import ApiTestCase
from utils import date_of


class DaysApiTest(ApiTestCase):
    """日期列表（/api/days）与贡献日历（/api/calendar）。"""

    def test_days_overview(self):
        """/api/days 返回最近若干天的每日点数归总。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        yesterday = today - dt.timedelta(days=1)
        self.client.post("/api/entries", json={
            "content": "今天的活",
            "points": 3,
            "ts": dt.datetime.combine(today, dt.time(12, 0)).astimezone().isoformat(),
        })
        self.client.post("/api/entries", json={
            "content": "昨天的活",
            "points": 5,
            "ts": dt.datetime.combine(yesterday, dt.time(12, 0)).astimezone().isoformat(),
        })
        r = self.client.get("/api/days")
        self.assertEqual(r.status_code, 200)
        days = r.get_json()
        by_date = {d["date"]: d for d in days}
        self.assertEqual(by_date[today.isoformat()]["points"], 3)
        self.assertEqual(by_date[yesterday.isoformat()]["points"], 5)
        self.assertTrue(by_date[today.isoformat()]["is_today"])

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


if __name__ == "__main__":
    unittest.main()