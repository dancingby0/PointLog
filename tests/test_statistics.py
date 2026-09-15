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


class AssetAnalysisApiTest(ApiTestCase):
    """资产统计分析：时间序列（收入/支出）+ 标签占比 + 筛选/粒度。"""

    def _seed(self):
        import data as data_mod
        g = data_mod.load_global()
        g["txs"] = [
            # 2026-08
            {"id": "1", "type": "income", "amount_fen": 5000, "account_id": "A",
             "tags": ["工资"], "ts": "2026-08-10T09:00"},
            {"id": "2", "type": "transfer", "amount_fen": 99900, "from_account": "A",
             "to_account": "B", "tags": [], "ts": "2026-08-11T09:00"},   # 转账不计
            # 2026-09
            {"id": "3", "type": "income", "amount_fen": 10000, "account_id": "A",
             "tags": ["工资"], "ts": "2026-09-15T09:00"},
            {"id": "4", "type": "expense", "amount_fen": 3000, "account_id": "A",
             "tags": ["餐饮"], "ts": "2026-09-15T12:00"},
            {"id": "5", "type": "expense", "amount_fen": 2000, "account_id": "B",
             "tags": ["餐饮", "交通"], "ts": "2026-09-16T19:00"},
            {"id": "6", "type": "expense", "amount_fen": 500, "account_id": "B",
             "tags": [], "ts": "2026-09-16T20:00"},                      # 无标签
            {"id": "7", "type": "adjust", "amount_fen": 12300, "account_id": "B",
             "tags": [], "ts": "2026-09-17T10:00"},                      # 校准不计
        ]
        data_mod.save_global(g)

    def _get(self, query):
        r = self.client.get(f"/api/stats/asset-analysis?{query}")
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def test_series_by_month(self):
        self._seed()
        body = self._get("from=2026-08-01&to=2026-09-30&granularity=month")
        self.assertEqual([s["period"] for s in body["series"]], ["2026-08", "2026-09"])
        aug, sep = body["series"]
        self.assertEqual((aug["income"], aug["expense"]), (50.0, 0.0))
        self.assertEqual((sep["income"], sep["expense"]), (100.0, 55.0))
        self.assertEqual(body["totals"], {"income": 150.0, "expense": 55.0, "net": 95.0})
        # 标签占比（多标签均摊：20 元 → 餐饮 10 + 交通 10；无标签→未分类）
        self.assertEqual(body["tag_income"], [{"tag": "工资", "amount": 150.0}])
        by_tag = {d["tag"]: d["amount"] for d in body["tag_expense"]}
        self.assertEqual(by_tag, {"餐饮": 40.0, "未分类": 5.0, "交通": 10.0})

    def test_series_by_day_fills_gaps(self):
        self._seed()
        body = self._get("from=2026-09-14&to=2026-09-17&granularity=day")
        periods = [s["period"] for s in body["series"]]
        self.assertEqual(periods, ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"])
        self.assertEqual(body["series"][0], {"period": "2026-09-14", "label": "09-14",
                                            "income": 0, "expense": 0})
        self.assertEqual(body["series"][2]["expense"], 25.0)   # 20 + 5

    def test_series_by_year(self):
        self._seed()
        body = self._get("from=2026-01-01&to=2026-12-31&granularity=year")
        self.assertEqual(len(body["series"]), 1)
        self.assertEqual(body["series"][0]["label"], "2026年")
        self.assertEqual(body["series"][0]["income"], 150.0)

    def test_filters(self):
        self._seed()
        base = "from=2026-08-01&to=2026-09-30&granularity=month"
        # 账户筛选：只看 B 账户
        body = self._get(f"{base}&accounts=B")
        self.assertEqual(body["totals"], {"income": 0.0, "expense": 25.0, "net": -25.0})
        # 标签筛选：只含"交通"的那笔（整笔计入）
        body = self._get(f"{base}&tags=交通")
        self.assertEqual(body["totals"]["expense"], 20.0)
        self.assertEqual(body["totals"]["income"], 0.0)
        # flow=expense 只统计支出
        body = self._get(f"{base}&flow=expense")
        self.assertEqual(body["totals"]["income"], 0.0)
        self.assertEqual(body["tag_income"], [])
        self.assertEqual(body["series"][1]["income"], 0)
        # flow=income 只统计收入
        body = self._get(f"{base}&flow=income")
        self.assertEqual(body["totals"]["expense"], 0.0)
        self.assertEqual(body["tag_expense"], [])

    def test_validation(self):
        self.assertEqual(self.client.get("/api/stats/asset-analysis?from=2026/01/01").status_code, 400)
        self.assertEqual(
            self.client.get("/api/stats/asset-analysis?from=2026-09-30&to=2026-09-01").status_code, 400)
        self.assertEqual(
            self.client.get("/api/stats/asset-analysis?granularity=week").status_code, 400)
        self.assertEqual(self.client.get("/api/stats/asset-analysis?flow=bad").status_code, 400)
        # 按日跨多年 → 时间点过多被拒
        self.assertEqual(
            self.client.get("/api/stats/asset-analysis?from=2020-01-01&to=2026-12-31&granularity=day").status_code,
            400)

    def test_default_range_is_ok(self):
        self._seed()
        body = self._get("")
        self.assertEqual(body["granularity"], "month")
        self.assertEqual(body["flow"], "both")
        self.assertTrue(1 <= len(body["series"]) <= 13)


if __name__ == "__main__":
    unittest.main()