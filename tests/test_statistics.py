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
        # recent：近 30 天，全部 0 点
        self.assertEqual(len(body["recent"]), 30)
        self.assertTrue(all(x["points"] == 0 for x in body["recent"]))

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
        # recent：今天与昨天 points>0，其余为 0
        by_date = {x["date"]: x for x in body["recent"]}
        self.assertEqual(by_date[today.isoformat()]["points"], 3)
        self.assertEqual(by_date[(today - dt.timedelta(days=1)).isoformat()]["points"], 2)
        zero_day = (today - dt.timedelta(days=5)).isoformat()
        self.assertEqual(by_date[zero_day]["points"], 0)

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

    def test_distribution(self):
        today = date_of(dt.datetime.now().astimezone())
        # 今天上午打 3 点（学习）、下午打 2 点（运动）
        self.client.post("/api/entries", json={
            "content": "学习", "points": 3, "category": "学习",
            "ts": dt.datetime.combine(today, dt.time(10, 0)).astimezone().isoformat(),
        })
        self.client.post("/api/entries", json={
            "content": "运动", "points": 2, "category": "运动",
            "ts": dt.datetime.combine(today, dt.time(15, 0)).astimezone().isoformat(),
        })
        r = self.client.get("/api/stats/distribution?range=month")
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        # 标签占比：学习 3 分排前
        tags = {t["tag"]: t for t in body["tags"]}
        self.assertEqual(tags["学习"]["points"], 3)
        self.assertEqual(tags["运动"]["points"], 2)
        # 星期：今天所在星期有 5 点
        wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.assertEqual(next(x for x in body["weekdays"] if x["label"] == wd)["points"], 5)
        # 时段：10点→清晨，15点→下午
        periods = {p["label"]: p["points"] for p in body["periods"]}
        self.assertEqual(periods.get("清晨"), 3)
        self.assertEqual(periods.get("下午"), 2)

    def test_distribution_bad_range(self):
        r = self.client.get("/api/stats/distribution?range=xx")
        self.assertEqual(r.status_code, 400)

    def test_asset_trend(self):
        """收支趋势：income/expense 按月聚合，转账不计。"""
        import data as data_mod
        now = dt.datetime.now().astimezone()
        g = data_mod.load_global()
        this_m = now.strftime("%Y-%m")
        # 本月：收入 10000 分(100元)，支出 2350 分(23.5元)；转账不计
        g["txs"].append({"id": "1", "type": "income", "amount_fen": 10000,
                         "ts": now.isoformat()})
        g["txs"].append({"id": "2", "type": "expense", "amount_fen": 2350,
                         "ts": now.isoformat()})
        g["txs"].append({"id": "3", "type": "transfer", "amount_fen": 5000,
                         "from_account": "a", "to_account": "b",
                         "ts": now.isoformat()})
        data_mod.save_global(g)

        r = self.client.get("/api/stats/assets?months=12")
        body = r.get_json()
        self.assertEqual(len(body), 12)
        cur = next(x for x in body if x["month"] == this_m)
        self.assertEqual(cur["income"], 100.0)
        self.assertEqual(cur["expense"], 23.5)


if __name__ == "__main__":
    unittest.main()