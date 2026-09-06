"""统计 API 测试：/api/stats/summary。"""

import datetime as dt
import unittest

from base import ApiTestCase
from utils import date_of


class SummaryApiTest(ApiTestCase):
    """坚持与概况汇总。"""

    def _add(self, day, points=1):
        self.client.post("/api/entries", json={
            "content": f"p{points}",
            "points": points,
            "ts": dt.datetime.combine(day, dt.time(12, 0)).astimezone().isoformat(),
        })

    def test_empty_summary(self):
        r = self.client.get("/api/stats/summary?range=month")
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(body["total_days"], 0)
        self.assertEqual(body["period_points"], 0)
        self.assertEqual(body["current_streak"], 0)
        self.assertEqual(body["notes_days"], 0)

    def test_month_summary(self):
        today = date_of(dt.datetime.now().astimezone())
        self._add(today, 3)
        self._add(today - dt.timedelta(days=1), 2)
        self.client.put("/api/notes", json={"day": today.isoformat(), "content": "感想"})
        r = self.client.get("/api/stats/summary?range=month")
        body = r.get_json()
        self.assertEqual(body["total_days"], 2)
        self.assertEqual(body["period_points"], 5)
        self.assertEqual(body["current_streak"], 2)  # 今天+昨天
        self.assertEqual(body["notes_days"], 1)

    def test_bad_range(self):
        r = self.client.get("/api/stats/summary?range=haha")
        self.assertEqual(r.status_code, 400)

    def test_trend_by_month(self):
        today = date_of(dt.datetime.now().astimezone())
        # 本月今天 + 上月同一天
        self._add(today, 3)
        last_month = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=min(today.day, 28))
        self._add(last_month, 5)
        r = self.client.get("/api/stats/trend?months=12")
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(body), 12)
        this_label = f"{today.year}年{today.month}月"
        cur = next(x for x in body if x["label"] == this_label)
        self.assertEqual(cur["points"], 3)
        # 找到上月那一项
        lm_label = f"{last_month.year}年{last_month.month}月"
        lm = next(x for x in body if x["label"] == lm_label)
        self.assertEqual(lm["points"], 5)

    def test_trend_clamp(self):
        r = self.client.get("/api/stats/trend?months=999")
        self.assertEqual(len(r.get_json()), 24)


if __name__ == "__main__":
    unittest.main()