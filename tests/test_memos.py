"""备忘录 + 置顶主目标 API 测试：/api/memos 与 /api/main-goal。"""

import unittest

from base import ApiTestCase


class MemosApiTest(ApiTestCase):
    """备忘录：增删、主目标设置与清除。"""

    def test_empty_memos(self):
        r = self.client.get("/api/memos")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["memos"], [])
        self.assertEqual(body["main_goal"], "")

    def test_create_and_list(self):
        r = self.client.post("/api/memos", json={"text": "周四打扫寝室"})
        self.assertEqual(r.status_code, 201)
        memo = r.get_json()
        self.assertTrue(memo["id"])
        self.assertEqual(memo["text"], "周四打扫寝室")

        body = self.client.get("/api/memos").get_json()
        self.assertEqual(len(body["memos"]), 1)
        self.assertEqual(body["memos"][0]["text"], "周四打扫寝室")

    def test_empty_text_rejected(self):
        r = self.client.post("/api/memos", json={"text": "   "})
        self.assertEqual(r.status_code, 400)

    def test_delete(self):
        r = self.client.post("/api/memos", json={"text": "作业 deadline"})
        mid = r.get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/memos/{mid}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/memos/{mid}").status_code, 404)

    def test_main_goal_set_and_clear(self):
        r = self.client.put("/api/main-goal", json={"goal": "主攻物理"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["main_goal"], "主攻物理")
        # 合并到 /api/memos 返回
        self.assertEqual(self.client.get("/api/memos").get_json()["main_goal"], "主攻物理")
        # 清除
        r = self.client.put("/api/main-goal", json={"goal": ""})
        self.assertEqual(r.get_json()["main_goal"], "")
        self.assertEqual(self.client.get("/api/memos").get_json()["main_goal"], "")


if __name__ == "__main__":
    unittest.main()