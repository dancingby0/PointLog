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
        """造一个已结束、时长确定的会话（直接写库，避免测试等待真实时间）。"""
        start = dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)
        end = start + dt.timedelta(minutes=minutes)
        d = data.load(config.CURRENT_PROFILE)
        d.setdefault("focus_sessions", []).append({
            "id": "sess1", "label": label, "state": "stopped", "points": points,
            "segments": [{"start": start.isoformat(timespec="seconds"),
                          "end": end.isoformat(timespec="seconds")}],
            "created_at": start.isoformat(timespec="seconds"),
            "entry_id": None, "uploaded_at": None,
        })
        data.save(config.CURRENT_PROFILE, d)

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
        self.assertEqual(d["focus_sessions"][0]["entry_id"], body["entry"]["id"])

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
        sid = self.client.post("/api/focus/sessions", json={"label": "x"}).get_json()["id"]
        d = data.load(config.CURRENT_PROFILE)
        past = (dt.datetime.now().astimezone() - dt.timedelta(minutes=5))
        d["focus_sessions"][0]["segments"] = [
            {"start": past.isoformat(timespec="seconds"), "end": None}]
        data.save(config.CURRENT_PROFILE, d)

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


if __name__ == "__main__":
    unittest.main()

