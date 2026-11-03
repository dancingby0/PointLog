"""专注 API 测试：计时状态机、上传为打卡（幂等）、统计。"""

import datetime as dt
import unittest

import config
import data
import utils
from tests.base import ApiTestCase


class FocusSessionApiTest(ApiTestCase):
    def test_start_creates_running_session(self):
        res = self.client.post("/api/focus/sessions", json={"label": "学数学", "points": 2})
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertEqual(body["state"], "running")
        self.assertEqual(body["label"], "学数学")
        self.assertEqual(body["points"], 2)

        cur = self.client.get("/api/focus/current").get_json()
        self.assertEqual(cur["session"]["id"], body["id"])
        self.assertGreaterEqual(cur["elapsed_sec"], 0)

    def test_pause_resume_stop(self):
        sid = self.client.post("/api/focus/sessions", json={"label": "x"}).get_json()["id"]

        paused = self.client.post(f"/api/focus/sessions/{sid}/pause").get_json()
        self.assertEqual(paused["state"], "paused")
        self.assertIsNotNone(paused["segments"][-1]["end"])

        resumed = self.client.post(f"/api/focus/sessions/{sid}/resume").get_json()
        self.assertEqual(resumed["state"], "running")
        self.assertEqual(len(resumed["segments"]), 2)

        stopped = self.client.post(f"/api/focus/sessions/{sid}/stop").get_json()
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(self.client.post(f"/api/focus/sessions/{sid}/stop")
                         .get_json()["state"], "stopped")          # 幂等

    def test_unknown_session_404(self):
        self.assertEqual(self.client.post("/api/focus/sessions/nope/pause").status_code, 404)
        self.assertEqual(self.client.post("/api/focus/sessions/nope/upload").status_code, 404)
        self.assertEqual(self.client.delete("/api/focus/sessions/nope").status_code, 404)

    def test_bad_action_400(self):
        sid = self.client.post("/api/focus/sessions", json={}).get_json()["id"]
        self.assertEqual(self.client.post(f"/api/focus/sessions/{sid}/bogus").status_code, 400)

    def test_starting_new_session_ends_previous(self):
        config.CURRENT_ACCOUNT = "someone"
        config.CURRENT_PROFILE = "p1"
        data.profile_dir("p1")
        first = self.client.post("/api/focus/sessions", json={"label": "旧"}).get_json()["id"]
        self.client.post("/api/focus/sessions", json={"label": "新"})
        rows = self.client.get("/api/focus/sessions").get_json()["sessions"]
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[first]["state"], "stopped")     # 自动结束，避免并发计时

    def test_label_length_limit(self):
        res = self.client.post("/api/focus/sessions", json={"label": "x" * 41})
        self.assertEqual(res.status_code, 400)


class FocusUploadApiTest(ApiTestCase):
    def _make_session(self, minutes=30, label="学习日语", points=2):
        """造一个已结束、时长确定的会话（直接写账号级 focus.json，避免等真实时间）。"""
        account = "soloupload"
        data.account_dir(account)
        start = dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)
        end = start + dt.timedelta(minutes=minutes)
        data.save_focus(account, {"version": 1, "sessions": [{
            "id": "sess1", "label": label, "state": "stopped", "points": points,
            "segments": [{"start": start.isoformat(timespec="seconds"),
                          "end": end.isoformat(timespec="seconds")}],
            "created_at": start.isoformat(timespec="seconds"),
            "entry_id": None, "uploaded_at": None,
        }]})
        config.CURRENT_ACCOUNT = account
        config.CURRENT_PROFILE = self.profile        # 打卡记录写进当前档案
        return account

    def test_upload_creates_entry(self):
        self._make_session(30, "学习日语", 2)
        res = self.client.post("/api/focus/sessions/sess1/upload", json={})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["entry"]["content"], "专注 30m · 学习日语")
        self.assertEqual(body["entry"]["points"], 2)
        self.assertEqual(body["entry"]["category"], ["学习日语"])

        d = data.load(config.CURRENT_PROFILE)
        self.assertEqual(len(d["entries"]), 1)
        self.assertIn("学习日语", d["diary_tags"])          # 标签入池
        stored = data.load_focus("soloupload")["sessions"][0]
        self.assertEqual(stored["entry_id"], body["entry"]["id"])

    def test_upload_is_idempotent(self):
        self._make_session(30)
        first = self.client.post("/api/focus/sessions/sess1/upload", json={}).get_json()
        second = self.client.post("/api/focus/sessions/sess1/upload",
                                  json={"points": 5}).get_json()
        d = data.load(config.CURRENT_PROFILE)
        self.assertEqual(len(d["entries"]), 1)              # 不会翻倍
        self.assertEqual(first["entry"]["id"], second["entry"]["id"])
        self.assertEqual(d["entries"][0]["points"], 5)       # 重复上传是更新

    def test_upload_rejects_short_session(self):
        self._make_session(0.5)                             # 30 秒
        res = self.client.post("/api/focus/sessions/sess1/upload", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("1 分钟", res.get_json()["error"])

    def test_upload_pauses_running_session_first(self):
        account = "solorun"
        data.account_dir(account)
        config.CURRENT_ACCOUNT = account
        config.CURRENT_PROFILE = self.profile
        sid = self.client.post("/api/focus/sessions", json={"label": "x"}).get_json()["id"]
        # 手动把开始时间挪到 5 分钟前，保证达到上传门槛
        store = data.load_focus(account)
        past = dt.datetime.now().astimezone() - dt.timedelta(minutes=5)
        for s in store["sessions"]:
            if str(s.get("id")) == sid:
                s["segments"] = [{"start": past.isoformat(timespec="seconds"), "end": None}]
        data.save_focus(account, store)

        res = self.client.post(f"/api/focus/sessions/{sid}/upload", json={})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["session"]["state"], "paused")

    def test_uploaded_entry_shows_in_daily_points(self):
        self._make_session(40, "学数学", 3)
        self.client.post("/api/focus/sessions/sess1/upload", json={})
        today = utils.date_of(dt.datetime.now().astimezone()).isoformat()
        body = self.client.get(f"/api/entries?day={today}").get_json()
        self.assertEqual(len(body["entries"]), 1)
        self.assertEqual(body["entries"][0]["content"], "专注 40m · 学数学")
        self.assertEqual(body["day_points"], 3)             # 进入点数系统


class FocusStatsApiTest(ApiTestCase):
    def test_empty_stats(self):
        body = self.client.get("/api/focus/stats").get_json()
        self.assertEqual(body["today_text"], "0m")
        self.assertEqual(body["days"], 0)
        self.assertEqual(body["by_label"], [])

    def test_stats_counts_today_and_total(self):
        now = dt.datetime.now().astimezone()
        d = data.load(config.CURRENT_PROFILE)
        d.setdefault("focus_sessions", []).extend([
            {"id": "a", "label": "画画", "state": "stopped", "points": 1,
             "segments": [{"start": (now - dt.timedelta(minutes=90)).isoformat(timespec="seconds"),
                           "end": now.isoformat(timespec="seconds")}],
             "created_at": now.isoformat(timespec="seconds")},
            {"id": "b", "label": "科研工作", "state": "stopped", "points": 1,
             "segments": [{"start": (now - dt.timedelta(days=1, minutes=30)).isoformat(timespec="seconds"),
                           "end": (now - dt.timedelta(days=1)).isoformat(timespec="seconds")}],
             "created_at": (now - dt.timedelta(days=1)).isoformat(timespec="seconds")},
        ])
        data.save(config.CURRENT_PROFILE, d)
        body = self.client.get("/api/focus/stats").get_json()
        self.assertEqual(body["today_text"], "1h30m")
        self.assertEqual(body["total_text"], "2h00m")
        self.assertEqual(body["days"], 2)
        labels = {r["label"]: r["text"] for r in body["by_label"]}
        self.assertEqual(labels["画画"], "1h30m")
        self.assertEqual(labels["科研工作"], "30m")

    def test_sessions_list_reports_upload_state(self):
        self.client.post("/api/focus/sessions", json={"label": "x"})
        rows = self.client.get("/api/focus/sessions").get_json()["sessions"]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["uploaded"])
        self.assertEqual(rows[0]["state"], "running")

    def test_delete_session(self):
        sid = self.client.post("/api/focus/sessions", json={"label": "x"}).get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/focus/sessions/{sid}").status_code, 200)
        self.assertEqual(self.client.get("/api/focus/sessions").get_json()["sessions"], [])


class FocusCrossProfileTest(ApiTestCase):
    """回归：未登录时开始计时（会话落在 default），登录后上传不应 404。

    真实故障：账号有 PIN 时服务启动不会自动登录，计时器先开始的会话写进
    data/default/data.json；用户在浏览器输 PIN 登录后当前档案变成账号下的档案，
    再点上传就 404（会话不在"当前档案"里）。
    """

    def setUp(self):
        super().setUp()
        # 造一个带 PIN 的账号（模拟真实环境：不会自动登录）
        self._old_account = config.CURRENT_ACCOUNT
        self._old_profile = config.CURRENT_PROFILE
        data.account_dir("pinner")
        meta = data.load_accounts_meta()
        meta["accounts"] = ["pinner"]
        meta["current"] = "pinner"
        meta["auto_login"] = True
        data.save_accounts_meta(meta)
        data.save_account_settings("pinner", {"pin_hash": "x"})
        # 未登录状态：会话会落到无账号的 default
        config.CURRENT_ACCOUNT = ""
        config.CURRENT_PROFILE = "default"

    def tearDown(self):
        config.CURRENT_ACCOUNT = self._old_account
        config.CURRENT_PROFILE = self._old_profile
        super().tearDown()

    def _start_and_switch(self, minutes=20):
        """登录后建会话并结束，再把会话移到根 default 模拟"历史遗留"。"""
        config.CURRENT_ACCOUNT = "pinner"
        config.CURRENT_PROFILE = "painted"
        created = self.client.post("/api/focus/sessions", json={"label": "画画"})
        self.assertEqual(created.status_code, 201)
        sid = created.get_json()["id"]
        self.client.post(f"/api/focus/sessions/{sid}/stop")

        # 把时长改成 20 分钟（避免测试等真实时间）
        d = data.load("painted")
        past = dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)
        for s in d["focus_sessions"]:
            if str(s.get("id")) == sid:
                s["segments"] = [
                    {"start": past.isoformat(timespec="seconds"),
                     "end": dt.datetime.now().astimezone().isoformat(timespec="seconds")}]
        data.save("painted", d)

        # 挪到根目录 default，模拟早期版本"未登录时计时"留下的数据
        legacy = data.DATA_DIR / "default" / "data.json"
        moved = next(s for s in d["focus_sessions"] if str(s.get("id")) == sid)
        data.save_path(legacy, {**data.default_data(), "focus_sessions": [moved]})
        d["focus_sessions"] = [s for s in d["focus_sessions"] if str(s.get("id")) != sid]
        data.save("painted", d)
        return sid

    def test_start_is_rejected_when_not_logged_in(self):
        """未登录（账号有 PIN）时不许开始计时：宁可报错也不写进看不见的目录。"""
        res = self.client.post("/api/focus/sessions", json={"label": "画画"})
        self.assertEqual(res.status_code, 409)
        self.assertTrue(res.get_json()["need_login"])
        self.assertIn("登录", res.get_json()["error"])
        # 根目录 default 不该被写入
        legacy = data.DATA_DIR / "default" / "data.json"
        self.assertFalse(legacy.exists())

    def test_operations_work_after_manual_login(self):
        """用户登录后再计时 → 一切正常（这是正常运行路径）。"""
        config.CURRENT_ACCOUNT = "pinner"
        config.CURRENT_PROFILE = "painted"
        res = self.client.post("/api/focus/sessions", json={"label": "画画"})
        self.assertEqual(res.status_code, 201)
        sid = res.get_json()["id"]
        self.assertEqual(self.client.post(f"/api/focus/sessions/{sid}/stop").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/focus/sessions/{sid}").status_code, 200)

    def test_legacy_session_in_root_default_is_still_reachable(self):
        """历史遗留：早期版本写进根目录 default 的会话，登录后仍能找到并上传。"""
        legacy = data.DATA_DIR / "default" / "data.json"
        now = dt.datetime.now().astimezone()
        start = now - dt.timedelta(minutes=30)
        data.save_path(legacy, {**data.default_data(), "focus_sessions": [{
            "id": "legacy1", "label": "画画", "state": "stopped", "points": 1,
            "segments": [{"start": start.isoformat(timespec="seconds"),
                          "end": now.isoformat(timespec="seconds")}],
            "created_at": start.isoformat(timespec="seconds"), "entry_id": None,
        }]})

        data.profile_dir("painted")
        config.CURRENT_ACCOUNT = "pinner"
        config.CURRENT_PROFILE = "painted"

        # current 只返回运行中的会话，这里已 stop → 应为空（但统计仍可见）
        self.assertIsNone(self.client.get("/api/focus/current").get_json()["session"])
        stats = self.client.get("/api/focus/stats").get_json()
        self.assertEqual(stats["sessions"], 1)

        res = self.client.post("/api/focus/sessions/legacy1/upload", json={})
        self.assertEqual(res.status_code, 200, msg=res.get_json())
        self.assertEqual(data.load_path(legacy)["entries"][0]["content"], "专注 30m · 画画")
        self.assertEqual(data.load("painted")["entries"], [])


    def test_current_and_stats_see_other_profiles(self):
        sid = self._start_and_switch()
        cur = self.client.get("/api/focus/current").get_json()
        # 该会话已 stop → current 为空；但 stats 仍应统计到它
        self.assertIsNone(cur["session"])

        stats = self.client.get("/api/focus/stats").get_json()
        self.assertEqual(stats["sessions"], 1)            # 根 default 里的会话也被统计
        self.assertIn("画画", [r["label"] for r in stats["by_label"]])

    def test_delete_crosses_profiles(self):
        sid = self._start_and_switch()
        self.assertEqual(self.client.delete(f"/api/focus/sessions/{sid}").status_code, 200)
        legacy = data.DATA_DIR / "default" / "data.json"
        self.assertEqual(data.load_path(legacy)["focus_sessions"], [])


class FocusCrossProfileTest(ApiTestCase):
    """v2.9：专注数据存账号级 focus.json —— 无需登录、不受档案影响。"""

    def setUp(self):
        super().setUp()
        self._old_account = config.CURRENT_ACCOUNT
        self._old_profile = config.CURRENT_PROFILE
        data.account_dir("pinner")
        meta = data.load_accounts_meta()
        meta["accounts"] = ["pinner"]
        meta["current"] = "pinner"
        meta["auto_login"] = True
        data.save_accounts_meta(meta)
        data.save_account_settings("pinner", {"pin_hash": "x"})
        # 未登录状态（账号有 PIN）：以前这会写进根 default，现在应落到账号级 focus.json
        config.CURRENT_ACCOUNT = ""
        config.CURRENT_PROFILE = "default"

    def tearDown(self):
        config.CURRENT_ACCOUNT = self._old_account
        config.CURRENT_PROFILE = self._old_profile
        super().tearDown()

    def test_works_without_login_and_lands_in_account_file(self):
        res = self.client.post("/api/focus/sessions", json={"label": "画画"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["state"], "running")

        focus_file = data.focus_path("pinner")
        self.assertTrue(focus_file.exists())
        self.assertEqual(len(data.load_focus("pinner")["sessions"]), 1)
        # 不再写进无账号归属的根 default 档案
        self.assertFalse((data.DATA_DIR / "default" / "data.json").exists())

    def test_survives_profile_switch(self):
        sid = self.client.post("/api/focus/sessions", json={"label": "画画"}).get_json()["id"]
        # 登录并切到账号下的某个档案 → 会话依然在（账号级，不随档案漂移）
        config.CURRENT_ACCOUNT = "pinner"
        config.CURRENT_PROFILE = "painted"
        data.profile_dir("painted")
        self.assertEqual(self.client.post(f"/api/focus/sessions/{sid}/stop").status_code, 200)
        self.assertEqual(self.client.get("/api/focus/stats").get_json()["sessions"], 1)

    def test_legacy_profile_sessions_are_migrated_once(self):
        """早期存在档案 data.json 里的 focus_sessions 会被并进账号级并清空旧字段。"""
        profile_file = data.account_dir("pinner") / "old" / "data.json"
        now = dt.datetime.now().astimezone()
        start = now - dt.timedelta(minutes=30)
        data.save_path(profile_file, {**data.default_data(), "focus_sessions": [{
            "id": "legacy1", "label": "旧会话", "state": "stopped", "points": 1,
            "segments": [{"start": start.isoformat(timespec="seconds"),
                          "end": now.isoformat(timespec="seconds")}],
            "created_at": start.isoformat(timespec="seconds"), "entry_id": None,
        }]})

        stats = self.client.get("/api/focus/stats").get_json()
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["by_label"][0]["label"], "旧会话")
        # 旧字段被清空（避免重复统计），账号级文件里有
        self.assertEqual(data.load_path(profile_file)["focus_sessions"], [])
        self.assertEqual(len(data.load_focus("pinner")["sessions"]), 1)
        # 再读一次不会重复并入
        self.assertEqual(self.client.get("/api/focus/stats").get_json()["sessions"], 1)


class FocusAutoSyncTest(ApiTestCase):
    """POST /api/focus/sync：批量上传"已结束且未上传"的会话（幂等）。"""

    def _seed(self, account="solo"):
        data.account_dir(account)
        now = dt.datetime.now().astimezone()
        rows = []
        for idx, (label, minutes, state) in enumerate([
            ("画画", 30, "stopped"),
            ("学数学", 12, "paused"),
            ("太短的", 0.2, "stopped"),          # 不足 1 分钟 → 跳过
            ("运行中的", 20, "running"),          # 运行中 → 跳过
        ]):
            start = now - dt.timedelta(minutes=minutes + 5)
            rows.append({
                "id": f"s{idx}", "label": label, "state": state, "points": 1,
                "segments": [{"start": start.isoformat(timespec="seconds"),
                              "end": (start + dt.timedelta(minutes=minutes)).isoformat(
                                  timespec="seconds")}],
                "created_at": start.isoformat(timespec="seconds"), "entry_id": None,
            })
        data.save_focus(account, {"version": 1, "sessions": rows})
        config.CURRENT_ACCOUNT = account
        config.CURRENT_PROFILE = "p1"
        data.profile_dir("p1")

    def test_sync_uploads_only_eligible_sessions(self):
        self._seed()
        res = self.client.post("/api/focus/sync", json={})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["count"], 2)                     # 画画 + 学数学
        labels = {u["label"] for u in body["uploaded"]}
        self.assertEqual(labels, {"画画", "学数学"})
        self.assertEqual(body["failed"], [])

        entries = data.load("p1")["entries"]
        self.assertEqual(len(entries), 2)
        self.assertTrue(all("专注" in e["content"] for e in entries))

    def test_sync_is_idempotent(self):
        self._seed()
        self.assertEqual(self.client.post("/api/focus/sync", json={}).get_json()["count"], 2)
        second = self.client.post("/api/focus/sync", json={}).get_json()
        self.assertEqual(second["count"], 0)                   # 已上传的不再重复
        self.assertEqual(len(data.load("p1")["entries"]), 2)

    def test_sync_respects_min_minutes(self):
        self._seed()
        body = self.client.post("/api/focus/sync", json={"min_minutes": 20}).get_json()
        self.assertEqual(body["count"], 1)                     # 只有 30 分钟的画画
        self.assertEqual(body["uploaded"][0]["label"], "画画")

    def test_sync_overrides_points(self):
        self._seed()
        body = self.client.post("/api/focus/sync", json={"points": 3}).get_json()
        self.assertTrue(all(u["points"] == 3 for u in body["uploaded"]))

    def test_sync_rejects_bad_min_minutes(self):
        self._seed()
        self.assertEqual(self.client.post("/api/focus/sync",
                                          json={"min_minutes": "abc"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()

