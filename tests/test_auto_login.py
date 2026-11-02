"""自动登录入口测试：确保"脚本先于浏览器发请求"时也能落到正确档案。

背景：自动登录原先只在 GET /api/auth（浏览器打开页面）时触发。桌面计时器由 launcher
同时拉起，可能先请求 /api/focus/*，那时 CURRENT_ACCOUNT 为空、CURRENT_PROFILE 还是
"default"，数据会写进 default 档案。ensure_auto_login() 把判断抽出来给各入口复用。
"""

import unittest

import config
import data
from routes import accounts
from tests.base import ApiTestCase


class EnsureAutoLoginTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._old_account = config.CURRENT_ACCOUNT
        self._old_profile = config.CURRENT_PROFILE
        self._old_suppressed = config.AUTO_LOGIN_SUPPRESSED
        # 干净起点：未登录、不抑制
        config.CURRENT_ACCOUNT = ""
        config.CURRENT_PROFILE = "default"
        config.AUTO_LOGIN_SUPPRESSED = False
        data.account_dir("tester")            # 建账号目录
        meta = data.load_accounts_meta()
        meta["accounts"] = ["tester"]
        meta["current"] = "tester"
        meta["auto_login"] = True
        data.save_accounts_meta(meta)

    def tearDown(self):
        config.CURRENT_ACCOUNT = self._old_account
        config.CURRENT_PROFILE = self._old_profile
        config.AUTO_LOGIN_SUPPRESSED = self._old_suppressed
        super().tearDown()

    def test_logs_in_when_enabled_and_no_pin(self):
        self.assertEqual(accounts.ensure_auto_login(), "tester")
        self.assertEqual(config.CURRENT_ACCOUNT, "tester")
        # 档案可能回退到 "default"，但必须已经挂在账号目录下（而不是根 data/default）
        prof_dir = data.profile_dir(config.CURRENT_PROFILE)
        self.assertIn("tester", str(prof_dir))

    def test_idempotent(self):
        accounts.ensure_auto_login()
        profile = config.CURRENT_PROFILE
        self.assertEqual(accounts.ensure_auto_login(), "tester")
        self.assertEqual(config.CURRENT_PROFILE, profile)

    def test_respects_manual_logout(self):
        """用户主动登出后本进程内不再自动登录。"""
        config.AUTO_LOGIN_SUPPRESSED = True
        self.assertEqual(accounts.ensure_auto_login(), "")
        self.assertEqual(config.CURRENT_ACCOUNT, "")

    def test_respects_disabled_auto_login(self):
        meta = data.load_accounts_meta()
        meta["auto_login"] = False
        data.save_accounts_meta(meta)
        self.assertEqual(accounts.ensure_auto_login(), "")

    def test_pin_account_requires_unlock_window(self):
        data.save_account_settings("tester", {"pin_hash": "x"})
        self.assertEqual(accounts.ensure_auto_login(), "")
        config.UNLOCKED_ACCOUNT = "tester"
        config.UNLOCKED_UNTIL = 9e18          # 处于免输窗口
        try:
            self.assertEqual(accounts.ensure_auto_login(), "tester")
        finally:
            config.UNLOCKED_ACCOUNT = ""
            config.UNLOCKED_UNTIL = 0.0

    def test_focus_api_triggers_auto_login(self):
        """计时器先请求 /api/focus/* → 也会补做自动登录，不写进 default 档案。"""
        config.CURRENT_PROFILE = "default"
        res = self.client.post("/api/focus/sessions", json={"label": "x"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(config.CURRENT_ACCOUNT, "tester")
        # 会话落在 tester 账号下的某个档案里，而不是根 data/default
        sess_file = data.profile_dir(config.CURRENT_PROFILE) / "data.json"
        stored = data.load(config.CURRENT_PROFILE)
        self.assertEqual(len(stored["focus_sessions"]), 1)
        self.assertTrue(str(sess_file).replace("\\", "/").startswith(
            str(data.account_dir("tester")).replace("\\", "/")))


if __name__ == "__main__":
    unittest.main()
