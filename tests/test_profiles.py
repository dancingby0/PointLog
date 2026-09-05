"""本地档案 + PIN 锁 API 测试。"""

import unittest

from base import ApiTestCase


class ProfilesApiTest(ApiTestCase):
    """档案创建、列举、切换、PIN 设置与解锁、数据隔离。"""

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

    def test_set_pin_and_unlock(self):
        r = self.client.put("/api/pin", json={"pin": "1234"})
        self.assertTrue(r.get_json()["has_pin"])
        # 解锁正确
        self.assertEqual(self.client.post("/api/unlock", json={"pin": "1234"}).status_code, 200)
        # 解锁错误
        self.assertEqual(self.client.post("/api/unlock", json={"pin": "0000"}).status_code, 401)
        # PIN 规则：过短 / 非数字
        self.assertEqual(self.client.put("/api/pin", json={"pin": "12"}).status_code, 400)
        self.assertEqual(self.client.put("/api/pin", json={"pin": "abcd"}).status_code, 400)

    def test_pin_is_hashed_not_plaintext(self):
        import data
        self.client.put("/api/pin", json={"pin": "1234"})
        settings = data.load_settings("alpha")
        self.assertIn("pin_hash", settings)
        self.assertNotIn("1234", settings["pin_hash"])

    def test_switch_to_pin_protected_profile(self):
        """给 alpha 设 PIN 后，从 beta 切回 alpha 必须输 PIN。"""
        self.client.put("/api/pin", json={"pin": "5678"})
        self._add_entry("alpha数据")
        # 建 beta 并切过去
        self.client.post("/api/profiles", json={"name": "beta"})
        self.client.post("/api/profiles/switch", json={"name": "beta"})
        # 无 PIN 切回 → 401
        self.assertEqual(
            self.client.post("/api/profiles/switch", json={"name": "alpha"}).status_code, 401)
        # 错误 PIN → 401
        self.assertEqual(
            self.client.post("/api/profiles/switch", json={"name": "alpha", "pin": "0000"}).status_code, 401)
        # 正确 PIN → 成功
        r = self.client.post("/api/profiles/switch", json={"name": "alpha", "pin": "5678"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["current"], "alpha")
        body = self.client.get("/api/entries").get_json()
        self.assertEqual(len(body["entries"]), 1)

    def test_clear_pin(self):
        self.client.put("/api/pin", json={"pin": "1234"})
        self.assertFalse(self.client.put("/api/pin", json={"pin": ""}).get_json()["has_pin"])
        # 清除后解锁不再需要 PIN
        self.assertEqual(self.client.post("/api/unlock", json={"pin": ""}).status_code, 200)


if __name__ == "__main__":
    unittest.main()