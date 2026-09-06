"""本地账号 API 测试。"""

import time
import unittest

import config
import data
from base import ApiTestCase


class AccountsApiTest(ApiTestCase):
    """账号创建、登录、隔离、PIN、免输窗口、登出、注销。"""

    def setUp(self):
        super().setUp()
        # 账号测试单独控制账号层状态
        self._old_acct = config.CURRENT_ACCOUNT
        config.CURRENT_ACCOUNT = ""
        self._old_unlocked_acct = config.UNLOCKED_ACCOUNT
        self._old_unlocked_until = config.UNLOCKED_UNTIL
        config.UNLOCKED_ACCOUNT = ""
        config.UNLOCKED_UNTIL = 0.0
        self._old_auto_login_suppressed = config.AUTO_LOGIN_SUPPRESSED
        config.AUTO_LOGIN_SUPPRESSED = False

    def tearDown(self):
        config.CURRENT_ACCOUNT = self._old_acct
        config.UNLOCKED_ACCOUNT = self._old_unlocked_acct
        config.UNLOCKED_UNTIL = self._old_unlocked_until
        config.AUTO_LOGIN_SUPPRESSED = self._old_auto_login_suppressed
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

    def test_relogin_within_window_skips_pin(self):
        """解锁后 10 分钟窗口内（进程内）登出再进免输。"""
        self._mk("锁X", "1234")
        r = self.client.post("/api/auth/login", json={"name": "锁X", "pin": "1234"})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(config.UNLOCKED_UNTIL, time.time())
        self.assertEqual(config.UNLOCKED_ACCOUNT, "锁X")
        # 登出保留窗口 → 再进不带 PIN 也成功
        self.client.post("/api/auth/logout")
        r = self.client.post("/api/auth/login", json={"name": "锁X"})
        self.assertEqual(r.status_code, 200)

    def test_window_expired_requires_pin_again(self):
        """窗口失效（如服务重启，内存清零）后需重新输 PIN。"""
        self._mk("锁Y", "1234")
        self.client.post("/api/auth/login", json={"name": "锁Y", "pin": "1234"})
        self.client.post("/api/auth/logout")
        config.UNLOCKED_ACCOUNT = ""  # 模拟服务重启：内存态丢失
        config.UNLOCKED_UNTIL = 0.0
        r = self.client.post("/api/auth/login", json={"name": "锁Y"})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/auth/login", json={"name": "锁Y", "pin": "1234"})
        self.assertEqual(r.status_code, 200)

    def test_get_auth_reports_unlocked_account(self):
        """GET /api/auth 返回当前免输窗口所属账号，供前端免输直进。"""
        self._mk("锁Z", "1234")
        self.client.post("/api/auth/login", json={"name": "锁Z", "pin": "1234"})
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["unlocked"], "锁Z")
        # 登出后窗口仍在
        self.client.post("/api/auth/logout")
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["unlocked"], "锁Z")
        # 窗口过期后为空
        config.UNLOCKED_UNTIL = 0.0
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["unlocked"], "")

    def test_auto_login_at_startup(self):
        """无锁账号：模拟服务刚启动 → GET 自动登录进入上次账号。"""
        self._mk("乙")
        self.client.post("/api/auth/set-auto-login", json={"enabled": True})
        config.CURRENT_ACCOUNT = ""          # 模拟启动：进程内存未登录
        config.AUTO_LOGIN_SUPPRESSED = False
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["logged_in"], "乙")

    def test_auto_login_with_pin_needs_window(self):
        """有 PIN 账号：自动登录仅在免输窗口内才发生。"""
        self._mk("甲", "1234")
        self.client.post("/api/auth/set-auto-login", json={"enabled": True})
        config.CURRENT_ACCOUNT = ""
        config.AUTO_LOGIN_SUPPRESSED = False
        # 窗口内 → 自动登录
        config.UNLOCKED_ACCOUNT = "甲"
        config.UNLOCKED_UNTIL = time.time() + 600
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["logged_in"], "甲")
        # 窗口失效（重启等）→ 不自动登录
        config.CURRENT_ACCOUNT = ""
        config.UNLOCKED_UNTIL = 0.0
        config.UNLOCKED_ACCOUNT = ""
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["logged_in"], "")

    def test_logout_suppresses_auto_login(self):
        """回归：开启自动登录后点登出，应停在账号选择页而非立刻被拉回。"""
        self._mk("乙")
        self.client.post("/api/auth/set-auto-login", json={"enabled": True})
        # 启动自动登录进入
        config.CURRENT_ACCOUNT = ""
        config.AUTO_LOGIN_SUPPRESSED = False
        self.assertEqual(self.client.get("/api/auth").get_json()["logged_in"], "乙")
        # 用户点登出 → 不再自动登录
        self.client.post("/api/auth/logout")
        self.assertEqual(config.AUTO_LOGIN_SUPPRESSED, True)
        body = self.client.get("/api/auth").get_json()
        self.assertEqual(body["logged_in"], "")
        self.assertEqual(config.CURRENT_ACCOUNT, "")
        # 手动选择其它/同账号仍可进入（不自动，但可手点）
        r = self.client.post("/api/auth/login", json={"name": "乙"})
        self.assertEqual(r.status_code, 200)

    def test_logout_keeps_window_but_clears_session(self):
        self._mk("备用账号")  # 至少保留两个账号才能注销
        self._mk("锁W", "1234")
        self.client.post("/api/auth/login", json={"name": "锁W", "pin": "1234"})
        self.client.post("/api/auth/logout")
        self.assertEqual(config.CURRENT_ACCOUNT, "")
        # 免输窗口为内存会话级，账号注销后应清理
        r = self.client.delete("/api/auth/锁W", json={"pin": "1234"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(config.UNLOCKED_ACCOUNT, "")
        self.assertEqual(config.UNLOCKED_UNTIL, 0.0)

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