"""PointLog 后端测试。

运行方式（项目根目录）：
    .venv\\Scripts\\python -m unittest discover -s tests -v
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import app as app_module
import data


class DataLayerTest(unittest.TestCase):
    """测试 data.py 的读写、归档、损坏恢复。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = data.DATA_DIR
        data.DATA_DIR = Path(self._tmp.name)
        self.profile = "tmp_test"

    def tearDown(self):
        data.DATA_DIR = self._old_dir
        self._tmp.cleanup()

    def test_new_profile_returns_default(self):
        d = data.load(self.profile)
        self.assertEqual(d["entries"], [])
        self.assertEqual(d["daily_notes"], [])
        self.assertEqual(d["memos"], [])

    def test_save_then_load_roundtrip(self):
        d = data.default_data()
        d["entries"].append({"id": "1", "ts": "2026-09-05T10:00:00", "points": 1, "content": "hi", "category": None})
        data.save(self.profile, d)
        loaded = data.load(self.profile)
        self.assertEqual(loaded, d)
        self.assertTrue(data.data_path(self.profile).exists())

    def test_corrupt_file_is_backed_up_and_reset(self):
        path = data.data_path(self.profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        d = data.load(self.profile)
        self.assertEqual(d, data.default_data())
        self.assertTrue(path.with_suffix(".json.bak").exists())


class ApiTest(unittest.TestCase):
    """通过 Flask 测试客户端走完整 HTTP 流程。"""

    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = app_module.data.DATA_DIR
        app_module.data.DATA_DIR = Path(self._tmp.name)
        # 每次测试用独立档案，避免相互影响
        self.profile = "api_test"
        app_module.CURRENT_PROFILE = self.profile

    def tearDown(self):
        app_module.data.DATA_DIR = self._old_dir
        self._tmp.cleanup()

    def test_empty_today(self):
        r = self.client.get("/api/entries")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["entries"], [])
        self.assertEqual(body["today_points"], 0)

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
        self.assertEqual(body["today_points"], 2)
        self.assertEqual(body["entries"][0]["content"], "背完《岳阳楼记》")

    def test_points_is_required_int(self):
        r = self.client.post("/api/entries", json={"content": "x", "points": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_content_required(self):
        r = self.client.post("/api/entries", json={"content": "  ", "points": 1})
        self.assertEqual(r.status_code, 400)

    def test_4am_belongs_to_yesterday(self):
        """凌晨 4 点前提交，应归属到"昨日"（当前实现按自然日，该条不算今日）。"""
        now = dt.datetime.now()
        # 构造"昨天 23:30"这一时刻（距今不超过 4 小时）
        yesterday_2330 = (now - dt.timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
        r = self.client.post("/api/entries", json={
            "content": "昨夜学习",
            "points": 1,
            "ts": yesterday_2330.isoformat(),
        })
        self.assertEqual(r.status_code, 201)
        # 该记录时间在"昨天"，不属于今日
        r = self.client.get("/api/entries")
        body = r.get_json()
        self.assertTrue(all(e["content"] != "昨夜学习" for e in body["entries"]))
        self.assertEqual(body["today_points"], 0)

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