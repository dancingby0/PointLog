"""打卡记录 API 测试：/api/entries 与 /api/entries/<id>。"""

import datetime as dt
import unittest

from base import ApiTestCase
from utils import date_of


class EntriesApiTest(ApiTestCase):
    """打卡记录：查询某天、新增、校验、编辑、删除。"""

    def test_empty_today(self):
        r = self.client.get("/api/entries")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["entries"], [])
        self.assertEqual(body["day_points"], 0)

    def test_create_and_list(self):
        r = self.client.post("/api/entries", json={
            "content": "背完《岳阳楼记》",
            "points": 2,
            "category": "语文",
        })
        self.assertEqual(r.status_code, 201)
        entry = r.get_json()
        self.assertTrue(entry["id"])
        self.assertEqual(entry["points"], 2)

        r = self.client.get("/api/entries")
        body = r.get_json()
        self.assertEqual(len(body["entries"]), 1)
        self.assertEqual(body["day_points"], 2)
        self.assertEqual(body["entries"][0]["content"], "背完《岳阳楼记》")

    def test_points_is_required_int(self):
        r = self.client.post("/api/entries", json={"content": "x", "points": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_content_required(self):
        r = self.client.post("/api/entries", json={"content": "  ", "points": 1})
        self.assertEqual(r.status_code, 400)

    def test_yesterday_2330_belongs_to_yesterday(self):
        """昨天 23:30（凌晨4点界之外的自然时间）不属于"今天"。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)               # "今天"（4点界日）
        yesterday = today - dt.timedelta(days=1)
        ts = dt.datetime.combine(yesterday, dt.time(23, 30)).astimezone()
        r = self.client.post("/api/entries", json={
            "content": "昨夜学习",
            "points": 1,
            "ts": ts.isoformat(),
        })
        self.assertEqual(r.status_code, 201)
        # 它属于昨天
        r_y = self.client.get(f"/api/entries?day={yesterday.isoformat()}")
        body_y = r_y.get_json()
        self.assertTrue(any(e["content"] == "昨夜学习" for e in body_y["entries"]))
        self.assertEqual(body_y["day_points"], 1)
        # 不属于今天
        r_t = self.client.get(f"/api/entries?day={today.isoformat()}")
        body_t = r_t.get_json()
        self.assertTrue(all(e["content"] != "昨夜学习" for e in body_t["entries"]))
        self.assertEqual(body_t["day_points"], 0)

    def test_early_morning_2am_belongs_to_previous_day(self):
        """凌晨 2 点（4 点界内）提交，应归属"昨天"。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)          # "今天"（4点界日）
        ts = dt.datetime.combine(today, dt.time(2, 0)).astimezone()
        r = self.client.post("/api/entries", json={
            "content": "凌晨学习",
            "points": 2,
            "ts": ts.isoformat(),
        })
        self.assertEqual(r.status_code, 201)
        # 今天列表不该有它
        r_today = self.client.get(f"/api/entries?day={today.isoformat()}")
        body = r_today.get_json()
        self.assertTrue(all(e["content"] != "凌晨学习" for e in body["entries"]))
        # 昨天列表应有它
        yesterday = today - dt.timedelta(days=1)
        r_y = self.client.get(f"/api/entries?day={yesterday.isoformat()}")
        body_y = r_y.get_json()
        self.assertTrue(any(e["content"] == "凌晨学习" for e in body_y["entries"]))
        self.assertEqual(body_y["day_points"], 2)

    def test_4am_boundary_belongs_today(self):
        """凌晨 4:00 整正好是"今天"的开端。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        ts = dt.datetime.combine(today, dt.time(4, 0)).astimezone()
        r = self.client.post("/api/entries", json={
            "content": "4点整学习",
            "points": 1,
            "ts": ts.isoformat(),
        })
        self.assertEqual(r.status_code, 201)
        r = self.client.get(f"/api/entries?day={today.isoformat()}")
        body = r.get_json()
        self.assertTrue(any(e["content"] == "4点整学习" for e in body["entries"]))
        self.assertEqual(body["day_points"], 1)

    def test_entries_by_day_param(self):
        """?day=YYYY-MM-DD 能精确查询某天。"""
        now = dt.datetime.now().astimezone()
        today = date_of(now)
        self.client.post("/api/entries", json={
            "content": "指定日期记录",
            "points": 4,
            "ts": dt.datetime.combine(today, dt.time(10, 0)).astimezone().isoformat(),
        })
        r = self.client.get(f"/api/entries?day={today.isoformat()}")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body["entries"]), 1)
        self.assertEqual(body["day_points"], 4)

    def test_bad_day_param(self):
        r = self.client.get("/api/entries?day=not-a-date")
        self.assertEqual(r.status_code, 400)

    def test_delete(self):
        r = self.client.post("/api/entries", json={"content": "要删掉", "points": 1})
        eid = r.get_json()["id"]
        r = self.client.delete(f"/api/entries/{eid}")
        self.assertEqual(r.status_code, 200)
        r = self.client.delete(f"/api/entries/{eid}")
        self.assertEqual(r.status_code, 404)

    def test_update_entry(self):
        r = self.client.post("/api/entries", json={"content": "原内容", "points": 1, "category": "语文"})
        eid = r.get_json()["id"]
        r = self.client.put(f"/api/entries/{eid}", json={
            "content": "改后的内容",
            "points": 3,
            "category": "运动",
        })
        self.assertEqual(r.status_code, 200)
        up = r.get_json()
        self.assertEqual(up["content"], "改后的内容")
        self.assertEqual(up["points"], 3)
        self.assertEqual(up["category"], "运动")

        # 只改点数：其余字段保持不变
        r = self.client.put(f"/api/entries/{eid}", json={"points": 5})
        up = r.get_json()
        self.assertEqual(up["content"], "改后的内容")
        self.assertEqual(up["points"], 5)

    def test_update_404(self):
        r = self.client.put("/api/entries/nonexistent", json={"points": 1})
        self.assertEqual(r.status_code, 404)

    def test_category_nullable(self):
        r = self.client.post("/api/entries", json={"content": "无类别", "points": 1})
        body = r.get_json()
        self.assertIsNone(body.get("category"))


if __name__ == "__main__":
    unittest.main()