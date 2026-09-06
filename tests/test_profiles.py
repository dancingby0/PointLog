"""本地档案 API 测试（v2.3：档案锁已取消）。"""

import unittest

from base import ApiTestCase


class ProfilesApiTest(ApiTestCase):
    """档案创建、列举、切换、数据隔离 + 旧 PIN 逻辑忽略。"""

    def setUp(self):
        super().setUp()
        # 建一个干净档案 alpha 并切过去，作为每次测试的起点
        self.client.post("/api/profiles", json={"name": "alpha"})
        r = self.client.post("/api/profiles/switch", json={"name": "alpha"})
        assert r.status_code == 200, r.get_json()

    def _add_entry(self, content, points=1):
        return self.client.post("/api/entries", json={"content": content, "points": points})

    def test_list_profiles_contains_current(self):
        r = self.client.get("/api/profiles")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        names = [p["name"] for p in body["profiles"]]
        self.assertIn("alpha", names)
        self.assertEqual(body["current"], "alpha")

    def test_create_then_switch_to_empty_profile(self):
        r = self.client.post("/api/profiles", json={"name": "study"})
        self.assertEqual(r.status_code, 201)
        # 切到新档案：它是空的
        r = self.client.post("/api/profiles/switch", json={"name": "study"})
        self.assertEqual(r.status_code, 200)
        body = self.client.get("/api/entries").get_json()
        self.assertEqual(body["entries"], [])

    def test_invalid_profile_name_rejected(self):
        r = self.client.post("/api/profiles", json={"name": "../evil"})
        self.assertEqual(r.status_code, 400)

    def test_switch_to_nonexistent_profile(self):
        r = self.client.post("/api/profiles/switch", json={"name": "nope"})
        self.assertEqual(r.status_code, 404)

    def test_profile_data_isolation(self):
        """各档案数据完全隔离。"""
        self._add_entry("alpha数据", points=2)
        self.client.post("/api/profiles", json={"name": "beta"})
        self.client.post("/api/profiles/switch", json={"name": "beta"})
        # beta 看不到 alpha 的记录
        body = self.client.get("/api/entries").get_json()
        self.assertEqual(body["entries"], [])
        # 切回 alpha 数据还在
        self.client.post("/api/profiles/switch", json={"name": "alpha"})
        body = self.client.get("/api/entries").get_json()
        self.assertEqual(len(body["entries"]), 1)
        self.assertEqual(body["entries"][0]["content"], "alpha数据")

    def test_legacy_pin_endpoints_disabled(self):
        """v2.3：档案锁取消。/pin 与 /unlock 仅作兼容空壳。"""
        r = self.client.put("/api/pin", json={"pin": "1234"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["has_pin"])
        # 解锁旧端点恒成功（不再校验）
        self.assertEqual(self.client.post("/api/unlock", json={"pin": "0000"}).status_code, 200)

    def test_legacy_profile_pin_data_ignored(self):
        """旧 v1 数据若留有 pin_hash，切换/删除也不再用它拦截。"""
        import data
        settings = data.load_settings("alpha")
        settings["pin_hash"] = "stale-legacy-hash"  # 模拟旧版遗留
        data.save_settings("alpha", settings)
        self.client.post("/api/profiles", json={"name": "beta"})
        self.client.post("/api/profiles/switch", json={"name": "beta"})
        # 切回原档案无需 PIN
        r = self.client.post("/api/profiles/switch", json={"name": "alpha"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["current"], "alpha")
        # 删除无需 PIN
        r = self.client.delete("/api/profiles/beta")
        self.assertEqual(r.status_code, 200)

    def test_rename_current_profile(self):
        r = self.client.put("/api/profiles/rename", json={"name": "alpha2"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["current"], "alpha2")
        # 目录名已改，alpha 不再存在
        self.assertEqual(self.client.post("/api/profiles/switch", json={"name": "alpha"}).status_code, 404)

    def test_rename_to_existing_rejected(self):
        self.client.post("/api/profiles", json={"name": "taken"})
        r = self.client.put("/api/profiles/rename", json={"name": "taken"})
        self.assertEqual(r.status_code, 400)

    def test_delete_other_profile(self):
        self.client.post("/api/profiles", json={"name": "victim"})
        r = self.client.delete("/api/profiles/victim")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.client.post("/api/profiles/switch", json={"name": "victim"}).status_code, 404)

    def test_delete_only_profile_rejected(self):
        # 只允许一个档案存在的场景：把 alpha 删到只剩一个前先造两个
        self.client.post("/api/profiles", json={"name": "keep"})
        self.assertEqual(self.client.delete("/api/profiles/alpha").status_code, 200)
        # 现在只剩 keep（当前档案），不能再删
        self.assertEqual(self.client.delete("/api/profiles/keep").status_code, 400)


if __name__ == "__main__":
    unittest.main()