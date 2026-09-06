"""本地账号 API 测试。"""

import tempfile
import unittest
from pathlib import Path

import config
import data
from base import ApiTestCase


class AccountsApiTest(ApiTestCase):
    """账号创建、登录、隔离、PIN、登出、注销。"""

    def setUp(self):
        super().setUp()
        # 账号测试单独控制账号层状态
        self._old_acct = config.CURRENT_ACCOUNT
        config.CURRENT_ACCOUNT = ""

    def tearDown(self):
        config.CURRENT_ACCOUNT = self._old_acct
        super().tearDown()

    def _mk(self, name, pin=""):
        r = self.client.post("/api/auth", json={"name": name, "pin": pin})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def test_create_and_list(self):
        self._mk("账号A")
        self._mk("账号B", "1234")
        r = self.client.get("/api/auth")
        body = r.get_json()
        names = {a["name"]: a for a in body["accounts"]}
        self.assertIn("账号A", names)
        self.assertTrue(names["账号B"]["has_pin"])

    def test_login_enters_account(self):
        self._mk("账号A")
        r = self.client.post("/api/auth/login", json={"name": "账号A"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["account"], "账号A")
        self.assertEqual(config.CURRENT_ACCOUNT, "账号A")

    def test_accounts_are_isolated(self):
        """账号A 与账号B 资产/档案隔离。"""
        self._mk("账号A")
        self.client.post("/api/auth/login", json={"name": "账号A"})
        # A 内创建资产账户
        r = self.client.post("/api/accounts", json={"name": "wx", "kind": "asset", "balance": 0})
        self.assertEqual(r.status_code, 201, r.get_json())
        # 切账号 B 后资产为空
        self._mk("账号B")
        self.client.post("/api/auth/login", json={"name": "账号B"})
        body = self.client.get("/api/accounts").get_json()
        self.assertEqual(body["accounts"], [])

    def test_login_requires_pin(self):
        self._mk("锁A", "1234")
        r = self.client.post("/api/auth/login", json={"name": "锁A"})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/auth/login", json={"name": "锁A", "pin": "1234"})
        self.assertEqual(r.status_code, 200)

    def test_set_account_pin(self):
        self._mk("账号C")
        self.client.post("/api/auth/login", json={"name": "账号C"})
        r = self.client.put("/api/auth/pin", json={"pin": "5678"})
        self.assertTrue(r.get_json()["has_pin"])
        r = self.client.put("/api/auth/pin", json={"pin": ""})
        self.assertFalse(r.get_json()["has_pin"])

    def test_logout(self):
        self._mk("账号D")
        self.client.post("/api/auth/login", json={"name": "账号D"})
        r = self.client.post("/api/auth/logout", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(config.CURRENT_ACCOUNT, "")

    def test_delete_account(self):
        self._mk("账号E")
        self._mk("账号F")
        r = self.client.delete("/api/auth/账号E")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.delete("/api/auth/账号E").status_code, 404)

    def test_delete_only_account_rejected(self):
        self._mk("唯一账号")
        r = self.client.delete("/api/auth/唯一账号")
        self.assertEqual(r.status_code, 400)

    def test_auto_login_switch(self):
        self._mk("账号G")
        self.client.post("/api/auth/login", json={"name": "账号G"})
        r = self.client.post("/api/auth/set-auto-login", json={"enabled": True})
        body = r.get_json()
        self.assertTrue(body["auto_login"])
        self.assertEqual(body["current"], "账号G")


if __name__ == "__main__":
    unittest.main()