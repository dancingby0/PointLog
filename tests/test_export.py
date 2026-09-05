"""数据导出 API 测试：/api/export。"""

import json
import unittest

from base import ApiTestCase


class ExportApiTest(ApiTestCase):
    """导出应为 JSON 附件，内容与当前档案数据一致，且随档案隔离。"""

    def test_export_matches_current_data(self):
        self.client.post("/api/entries", json={"content": "跑个步", "points": 2})
        self.client.put("/api/notes", json={"day": "2026-09-05", "content": "今天的感想"})
        self.client.post("/api/memos", json={"text": "备忘一条"})
        self.client.put("/api/main-goal", json={"goal": "主攻物理"})

        r = self.client.get("/api/export")
        self.assertEqual(r.status_code, 200)
        # 附件下载头
        cd = r.headers.get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn("pointlog-", cd)
        self.assertIn(".json", cd)
        # 内容与 data.json 同构
        payload = json.loads(r.data.decode("utf-8"))
        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["entries"][0]["content"], "跑个步")
        self.assertEqual(payload["daily_notes"]["2026-09-05"], "今天的感想")
        self.assertEqual(payload["memos"][0]["text"], "备忘一条")
        self.assertEqual(payload["main_goal"], "主攻物理")

    def test_export_is_profile_scoped(self):
        self.client.post("/api/entries", json={"content": "档案A数据", "points": 1})
        # 新建并切到空档案 B
        self.client.post("/api/profiles", json={"name": "bprofile"})
        self.client.post("/api/profiles/switch", json={"name": "bprofile"})

        r = self.client.get("/api/export")
        payload = json.loads(r.data.decode("utf-8"))
        self.assertEqual(payload["entries"], [])   # B 是空的


if __name__ == "__main__":
    unittest.main()