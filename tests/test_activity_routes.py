"""活动 API 测试：routes/activity.py（ActivityWatch 客户端全部用假对象，不依赖真实 AW）。"""

import datetime as dt
import unittest
from unittest import mock

import aw_client
import config
import data
import utils
from tests.base import ApiTestCase


def _today():
    return utils.date_of(dt.datetime.now().astimezone())


def _ev(day, hour, minutes, **data):
    """构造一条落在 day 当天某时刻的 AW 事件（本地朴素时间，duration 分钟）。"""
    start = dt.datetime.combine(day, dt.time(hour, 0))
    return {"timestamp": start.isoformat(), "duration": minutes * 60, "data": data}


class FakeAw:
    """假 AwClient：可配置桶列表与事件。"""

    def __init__(self, infos=None, events=None):
        self.infos = infos if infos is not None else [
            {"id": "aw-watcher-window_pc", "type": "currentwindow",
             "client": "aw-watcher-window", "hostname": "pc"},
            {"id": "aw-watcher-afk_pc", "type": "afkstatus",
             "client": "aw-watcher-afk", "hostname": "pc"},
            {"id": "aw-watcher-web-chrome", "type": "web.tab.current",
             "client": "aw-watcher-web", "hostname": "pc"},
        ]
        self.events_by_bucket = events or {}
        self.calls = []

    def bucket_summaries(self):
        return self.infos

    def events(self, bucket_id, start, end, limit=-1):
        self.calls.append(bucket_id)
        return self.events_by_bucket.get(bucket_id, [])


def _day_events(day, app="Code", window_min=60, afk_min=60):
    return {
        "aw-watcher-window_pc": [_ev(day, 9, window_min, app=app, title="main.py")],
        "aw-watcher-afk_pc": [_ev(day, 9, afk_min, status="not-afk")],
        "aw-watcher-web-chrome": [_ev(day, 9, 20, url="https://chat.deepseek.com/c",
                                      title="DeepSeek", audible=False)],
    }


class ActivityStatusTest(ApiTestCase):
    def test_status_when_activitywatch_missing(self):
        def boom(*args, **kwargs):
            raise aw_client.AwUnavailable("拒绝连接")

        with mock.patch("aw_client.AwClient", side_effect=boom):
            res = self.client.get("/api/activity/status")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertFalse(body["connected"])
        self.assertIn("拒绝连接", body["error"])
        self.assertIn("ActivityWatch", body["hint"])
        self.assertEqual(body["synced_days"], 0)

    def test_status_lists_buckets_and_warns_missing_web_watcher(self):
        fake = FakeAw(infos=[{"id": "aw-watcher-window_pc", "type": "currentwindow"},
                             {"id": "aw-watcher-afk_pc", "type": "afkstatus"}])
        with mock.patch("aw_client.AwClient", lambda *a, **k: fake):
            body = self.client.get("/api/activity/status").get_json()
        self.assertTrue(body["connected"])
        self.assertFalse(body["has_web_watcher"])
        self.assertIn("aw-watcher-web", body["hint"])
        self.assertEqual(body["picked"]["window"], "aw-watcher-window_pc")


class ActivitySyncTest(ApiTestCase):
    def test_sync_today_writes_activity_file(self):
        day = _today()
        fake = FakeAw(events=_day_events(day))
        with mock.patch("aw_client.AwClient", lambda *a, **k: fake):
            res = self.client.post("/api/activity/sync", json={"days": 1})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["synced"], 1)
        self.assertTrue(body["has_web_watcher"])

        store = data.load_activity(config.CURRENT_PROFILE)
        item = store["days"][day.isoformat()]
        self.assertEqual(item["active_min"], 60.0)
        self.assertEqual(item["apps"][0]["app"], "Code")
        self.assertEqual(item["sites"][0]["domain"], "chat.deepseek.com")
        self.assertEqual(item["sites"][0]["category"], "AI辅助")
        self.assertEqual(item["source"], "activitywatch")
        self.assertTrue((data.profile_dir(config.CURRENT_PROFILE) / "activity.json").exists())

    def test_sync_is_idempotent(self):
        day = _today()
        fake = FakeAw(events=_day_events(day))
        with mock.patch("aw_client.AwClient", lambda *a, **k: fake):
            self.client.post("/api/activity/sync", json={"days": 1})
            self.client.post("/api/activity/sync", json={"days": 1})
        store = data.load_activity(config.CURRENT_PROFILE)
        self.assertEqual(list(store["days"]), [day.isoformat()])   # 覆盖写，不重复追加
        self.assertEqual(len(store["days"][day.isoformat()]["apps"]), 1)

    def test_sync_range_covers_each_day(self):
        today = _today()
        fake = FakeAw()
        with mock.patch("aw_client.AwClient", lambda *a, **k: fake):
            body = self.client.post("/api/activity/sync",
                                    json={"from": (today - dt.timedelta(days=2)).isoformat(),
                                          "to": today.isoformat()}).get_json()
        self.assertEqual(body["synced"], 3)
        store = data.load_activity(config.CURRENT_PROFILE)
        self.assertEqual(len(store["days"]), 3)
        self.assertEqual(len(fake.calls), 3 * 3)          # 每天查 window/afk/web 三个桶

    def test_sync_returns_503_when_unreachable(self):
        def boom(*args, **kwargs):
            raise aw_client.AwUnavailable("拒绝连接")

        with mock.patch("aw_client.AwClient", side_effect=boom):
            res = self.client.post("/api/activity/sync", json={"days": 1})
        self.assertEqual(res.status_code, 503)
        self.assertIn("ActivityWatch", res.get_json()["error"])

    def test_sync_returns_409_without_window_afk_buckets(self):
        fake = FakeAw(infos=[{"id": "aw-watcher-web-chrome", "type": "web.tab.current"}])
        with mock.patch("aw_client.AwClient", lambda *a, **k: fake):
            res = self.client.post("/api/activity/sync", json={"days": 1})
        self.assertEqual(res.status_code, 409)
        self.assertIn("窗口", res.get_json()["error"])

    def test_sync_rejects_too_many_days(self):
        today = _today()
        res = self.client.post("/api/activity/sync",
                               json={"from": (today - dt.timedelta(days=200)).isoformat(),
                                     "to": today.isoformat()})
        self.assertEqual(res.status_code, 400)
        self.assertIn("最多", res.get_json()["error"])

    def test_sync_rejects_bad_body(self):
        self.assertEqual(self.client.post("/api/activity/sync",
                                          json={"days": "abc"}).status_code, 400)

    def test_sync_respects_disabled_switch(self):
        self.client.put("/api/activity/config", json={"enabled": False})
        res = self.client.post("/api/activity/sync", json={"days": 1})
        self.assertEqual(res.status_code, 400)
        self.assertIn("关闭", res.get_json()["error"])


class ActivityConfigTest(ApiTestCase):
    def test_get_returns_defaults(self):
        body = self.client.get("/api/activity/config").get_json()["settings"]
        self.assertEqual(body["base_url"], "http://127.0.0.1:5600")
        self.assertTrue(body["rules"])
        self.assertEqual(body["gap_allow_sec"], 120)

    def test_put_persists_valid_settings(self):
        payload = {
            "base_url": "http://127.0.0.1:5600/",
            "host": "pc",
            "gap_allow_sec": 300,
            "ignored_apps": ["ActivityWatch", " PointLog "],
            "rules": [{"category": "AI辅助", "url": r"deepseek\.com"},
                      {"category": "学习", "url": "bilibili", "title": "课程|考研"}],
        }
        res = self.client.put("/api/activity/config", json=payload)
        self.assertEqual(res.status_code, 200)
        saved = data.load_activity(config.CURRENT_PROFILE)["settings"]
        self.assertEqual(saved["base_url"], "http://127.0.0.1:5600")   # 去掉尾部斜杠
        self.assertEqual(saved["gap_allow_sec"], 300)
        self.assertEqual(saved["ignored_apps"], ["activitywatch", "pointlog"])
        self.assertEqual(len(saved["rules"]), 2)
        self.assertEqual(res.get_json()["settings"]["rules"][1]["title"], "课程|考研")

    def test_put_rejects_invalid_regex(self):
        res = self.client.put("/api/activity/config",
                              json={"rules": [{"category": "坏", "url": "([unclosed"}]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("正则", res.get_json()["error"])

    def test_put_rejects_rule_without_pattern(self):
        res = self.client.put("/api/activity/config", json={"rules": [{"category": "空"}]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("url", res.get_json()["error"])

    def test_put_rejects_bad_base_url(self):
        for bad in ("127.0.0.1:5600", "ftp://x", ""):
            res = self.client.put("/api/activity/config", json={"base_url": bad})
            self.assertEqual(res.status_code, 400, msg=bad)


class ActivityQueryTest(ApiTestCase):
    def _seed(self, day=None):
        day = day or _today()
        store = data.load_activity(config.CURRENT_PROFILE)
        store["days"][day.isoformat()] = {
            "day": day.isoformat(), "active_min": 42.5, "excluded_min": 0,
            "first_ts": None, "last_ts": None,
            "apps": [{"app": "Code", "min": 30.0, "category": "编程"}],
            "sites": [{"domain": "bilibili.com", "min": 12.5, "category": "娱乐"}],
            "titles": [], "pages": [], "categories": [],
            "source": "activitywatch", "imported_at": "2026-10-11T22:00:00+08:00",
        }
        data.save_activity(config.CURRENT_PROFILE, store)

    def test_days_list_is_lightweight(self):
        self._seed()
        body = self.client.get("/api/activity/days").get_json()
        self.assertEqual(body["synced_days"], 1)
        self.assertEqual(body["days"][0]["active_min"], 42.5)
        self.assertEqual(body["days"][0]["top_app"], "Code")
        self.assertEqual(body["days"][0]["top_site"], "bilibili.com")
        self.assertNotIn("apps", body["days"][0])
        self.assertTrue(body["has_web_watcher"])

    def test_day_detail_and_404(self):
        self._seed()
        day = _today().isoformat()
        ok = self.client.get(f"/api/activity/day/{day}")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["apps"][0]["app"], "Code")

        missing = self.client.get("/api/activity/day/1999-01-01")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("同步", missing.get_json()["error"])

    def test_day_detail_rejects_bad_date(self):
        self.assertEqual(self.client.get("/api/activity/day/2026-13-40").status_code, 400)

    def test_delete_day(self):
        self._seed()
        day = _today().isoformat()
        res = self.client.delete(f"/api/activity/day/{day}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["synced_days"], 0)
        self.assertEqual(self.client.delete(f"/api/activity/day/{day}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
