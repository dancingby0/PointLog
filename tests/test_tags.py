"""标签池 API 测试：日记标签（档案级）与资产标签（个人级）。"""

import unittest

from base import ApiTestCase


class TagsApiTest(ApiTestCase):
    """双标签池：日记随档案走，资产全局共享。"""

    def test_empty_pools(self):
        r = self.client.get("/api/tags/diary")
        self.assertEqual(r.get_json()["tags"], [])
        r = self.client.get("/api/tags/asset")
        self.assertEqual(r.get_json()["tags"], [])

    def test_diary_add_list_delete(self):
        self.assertEqual(self.client.post("/api/tags/diary", json={"tag": "运动"}).status_code, 200)
        body = self.client.get("/api/tags/diary").get_json()
        self.assertIn("运动", body["tags"])
        self.assertEqual(body["scope"], "diary")
        # 删除
        r = self.client.delete("/api/tags/diary?tag=运动")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/tags/diary").get_json()["tags"], [])
        # 重复添加不去重会重复
        self.client.post("/api/tags/diary", json={"tag": "学习"})
        self.client.post("/api/tags/diary", json={"tag": "学习"})
        tags = self.client.get("/api/tags/diary").get_json()["tags"]
        self.assertEqual(tags.count("学习"), 1)

    def test_diary_tags_are_profile_scoped(self):
        """日记标签随档案走：切档案后是另一套。"""
        self.client.post("/api/tags/diary", json={"tag": "学习"})
        self.client.post("/api/profiles", json={"name": "other"})
        self.client.post("/api/profiles/switch", json={"name": "other"})
        tags = self.client.get("/api/tags/diary").get_json()["tags"]
        self.assertEqual(tags, [])
        # 切回原档案仍能看到
        self.client.post("/api/profiles/switch", json={"name": self.profile})
        tags = self.client.get("/api/tags/diary").get_json()["tags"]
        self.assertIn("学习", tags)

    def test_asset_tags_are_global(self):
        """资产标签是个人级：切档案后仍是同一套。"""
        self.client.post("/api/tags/asset", json={"tag": "餐饮"})
        self.client.post("/api/profiles", json={"name": "other2"})
        self.client.post("/api/profiles/switch", json={"name": "other2"})
        tags = self.client.get("/api/tags/asset").get_json()["tags"]
        self.assertIn("餐饮", tags)

    def test_tags_validation(self):
        self.assertEqual(self.client.post("/api/tags/diary", json={"tag": "  "}).status_code, 400)
        self.assertEqual(self.client.post("/api/tags/asset", json={"tag": "  "}).status_code, 400)
        self.assertEqual(self.client.delete("/api/tags/diary?tag=nope").status_code, 404)
        self.assertEqual(self.client.delete("/api/tags/asset?tag=nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()