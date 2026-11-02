"""标签池 API 测试：增 / 改名（可选级联）/ 删。"""

import unittest

import config
import data
from tests.base import ApiTestCase


class DiaryTagTest(ApiTestCase):
    def _tags(self):
        return self.client.get("/api/tags/diary").get_json()["tags"]

    def test_empty_by_default(self):
        """不再预置任何标签：池子完全由用户维护。"""
        self.assertEqual(self._tags(), [])

    def test_add_and_delete(self):
        self.client.post("/api/tags/diary", json={"tag": "画画"})
        self.assertEqual(self._tags(), ["画画"])
        res = self.client.delete("/api/tags/diary?tag=画画")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._tags(), [])

    def test_add_duplicate_is_idempotent(self):
        self.client.post("/api/tags/diary", json={"tag": "画画"})
        self.client.post("/api/tags/diary", json={"tag": "画画"})
        self.assertEqual(self._tags(), ["画画"])

    def test_add_validates(self):
        self.assertEqual(self.client.post("/api/tags/diary", json={"tag": "  "}).status_code, 400)
        self.assertEqual(self.client.post("/api/tags/diary",
                                          json={"tag": "x" * 21}).status_code, 400)

    def test_rename_without_cascade_keeps_records(self):
        self.client.post("/api/tags/diary", json={"tag": "学数学"})
        d = data.load(config.CURRENT_PROFILE)
        d["entries"].append({"id": "e1", "ts": "2026-11-02T10:00:00+08:00", "points": 1,
                             "content": "x", "category": ["学数学"]})
        data.save(config.CURRENT_PROFILE, d)

        res = self.client.put("/api/tags/diary", json={"from": "学数学", "to": "数学"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["tags"], ["数学"])
        self.assertEqual(res.get_json()["entries_changed"], 0)
        # 历史记录不动（删/改名只影响词库）
        self.assertEqual(data.load(config.CURRENT_PROFILE)["entries"][0]["category"], ["学数学"])

    def test_rename_with_cascade_rewrites_records(self):
        self.client.post("/api/tags/diary", json={"tag": "学数学"})
        d = data.load(config.CURRENT_PROFILE)
        d["entries"].extend([
            {"id": "e1", "ts": "2026-11-02T10:00:00+08:00", "points": 1,
             "content": "a", "category": ["学数学"]},
            {"id": "e2", "ts": "2026-11-01T10:00:00+08:00", "points": 1,
             "content": "b", "category": ["学数学", "画画"]},
            {"id": "e3", "ts": "2026-11-01T11:00:00+08:00", "points": 1,
             "content": "c", "category": "学数学"},          # v1 单值写法
            {"id": "e4", "ts": "2026-11-01T12:00:00+08:00", "points": 1,
             "content": "d", "category": ["物理"]},
        ])
        data.save(config.CURRENT_PROFILE, d)

        res = self.client.put("/api/tags/diary",
                              json={"from": "学数学", "to": "数学分析", "cascade": True})
        self.assertEqual(res.get_json()["entries_changed"], 3)
        by_id = {e["id"]: e["category"]
                 for e in data.load(config.CURRENT_PROFILE)["entries"]}
        self.assertEqual(by_id["e1"], ["数学分析"])
        self.assertEqual(by_id["e2"], ["数学分析", "画画"])   # 多类别只替换命中的那项
        self.assertEqual(by_id["e3"], ["数学分析"])           # 单值被规范成数组
        self.assertEqual(by_id["e4"], ["物理"])               # 不相关的不动

    def test_rename_into_existing_tag_merges(self):
        for tag in ("学数学", "物理"):
            self.client.post("/api/tags/diary", json={"tag": tag})
        res = self.client.put("/api/tags/diary", json={"from": "学数学", "to": "物理"})
        self.assertEqual(res.get_json()["tags"], ["物理"])    # 合并去重，不留重复项

    def test_rename_validations(self):
        self.client.post("/api/tags/diary", json={"tag": "画画"})
        self.assertEqual(self.client.put("/api/tags/diary",
                                         json={"from": "不存在", "to": "x"}).status_code, 404)
        self.assertEqual(self.client.put("/api/tags/diary",
                                         json={"from": "画画", "to": ""}).status_code, 400)
        self.assertEqual(self.client.put("/api/tags/diary",
                                         json={"from": "画画", "to": "y" * 21}).status_code, 400)

    def test_delete_missing_tag_404(self):
        self.assertEqual(self.client.delete("/api/tags/diary?tag=nope").status_code, 404)


class AssetTagTest(ApiTestCase):
    def test_rename_with_cascade_updates_txs(self):
        self.client.post("/api/tags/asset", json={"tag": "吃饭"})
        g = data.load_global()
        g["txs"].append({"id": "t1", "type": "expense", "amount_fen": 1000,
                         "ts": "2026-11-02T10:00:00+08:00", "tags": ["吃饭"]})
        g["txs"].append({"id": "t2", "type": "expense", "amount_fen": 500,
                         "ts": "2026-11-02T11:00:00+08:00", "tags": ["其他"]})
        data.save_global(g)

        res = self.client.put("/api/tags/asset",
                              json={"from": "吃饭", "to": "餐饮", "cascade": True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["tags"], ["餐饮"])
        self.assertEqual(res.get_json()["txs_changed"], 1)
        tags_by_id = {t["id"]: t["tags"] for t in data.load_global()["txs"]}
        self.assertEqual(tags_by_id["t1"], ["餐饮"])
        self.assertEqual(tags_by_id["t2"], ["其他"])


if __name__ == "__main__":
    unittest.main()
