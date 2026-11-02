"""每日日常 / 点数标准 / 今日提醒 / 备忘时间范围的 API 测试。"""

import datetime as dt
import unittest

import config
import data
import utils
from tests.base import ApiTestCase


def _today():
    return utils.date_of(dt.datetime.now().astimezone())


class DailyRoutineApiTest(ApiTestCase):
    """每日日常：一段可换行文字，与点数标准完全独立。"""

    def test_drops_legacy_routines_field(self):
        """v2.7 早期的 routines 清单字段：读时丢弃，不再出现在 API 里。"""
        d = data.load(config.CURRENT_PROFILE)
        d["routines"] = [{"id": "x", "start": "08:00", "end": "09:00", "text": "旧结构"}]
        data.save(config.CURRENT_PROFILE, d)
        self.assertNotIn("routines", data.load(config.CURRENT_PROFILE))

    def test_get_returns_empty_by_default(self):
        body = self.client.get("/api/daily-routine").get_json()
        self.assertEqual(body["text"], "")
        self.assertTrue(body["empty"])
        self.assertEqual(body["lines"], 0)

    def test_put_keeps_newlines(self):
        text = "早餐 + 背单词\n上午 刷题 2 小时\n\n晚上 复盘"
        res = self.client.put("/api/daily-routine", json={"text": text})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["text"], text)
        self.assertEqual(res.get_json()["lines"], 3)     # 空行不算行
        self.assertEqual(self.client.get("/api/daily-routine").get_json()["text"], text)

    def test_put_trims_edge_blank_lines_only(self):
        res = self.client.put("/api/daily-routine", json={"text": "\n\n第一行\n\n第二行\n\n"})
        self.assertEqual(res.get_json()["text"], "第一行\n\n第二行")   # 中间空行保留

    def test_put_rejects_missing_text(self):
        self.assertEqual(self.client.put("/api/daily-routine", json={}).status_code, 400)

    def test_independent_from_point_rules(self):
        """改一个不影响另一个。"""
        self.client.put("/api/daily-routine", json={"text": "日常内容"})
        self.client.put("/api/point-rules", json={"text": "点数内容"})
        self.assertEqual(self.client.get("/api/daily-routine").get_json()["text"], "日常内容")
        self.assertEqual(self.client.get("/api/point-rules").get_json()["text"], "点数内容")

        self.client.put("/api/daily-routine", json={"text": "只改日常"})
        self.assertEqual(self.client.get("/api/point-rules").get_json()["text"], "点数内容")


class PointRulesApiTest(ApiTestCase):
    def test_roundtrip(self):
        text = "专注 1h 10 点\n游泳 100m 1 点"
        res = self.client.put("/api/point-rules", json={"text": text})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/point-rules").get_json()["text"], text)

    def test_legacy_profile_without_field(self):
        """老档案没有这两个字段：读出空文本，不报错。"""
        d = data.load(config.CURRENT_PROFILE)
        d.pop("daily_routine", None)
        d.pop("point_rules", None)
        data.save(config.CURRENT_PROFILE, d)
        self.assertEqual(self.client.get("/api/daily-routine").get_json()["text"], "")
        self.assertEqual(self.client.get("/api/point-rules").get_json()["text"], "")



class TodayViewApiTest(ApiTestCase):
    def test_empty_profile(self):
        body = self.client.get("/api/today-view").get_json()
        self.assertEqual(body["day"], _today().isoformat())
        self.assertEqual(body["daily_routine"]["text"], "")
        self.assertEqual(body["point_rules"]["text"], "")
        self.assertEqual(body["reminders"], [])

    def test_returns_both_texts_and_reminders(self):
        self.client.put("/api/daily-routine", json={"text": "日常一行"})
        self.client.put("/api/point-rules", json={"text": "标准一行"})
        self.client.post("/api/memos", json={
            "text": "每天提醒", "schedule": {"mode": "daily"}})
        self.client.post("/api/memos", json={"text": "不设时间"})

        body = self.client.get("/api/today-view").get_json()
        self.assertEqual(body["daily_routine"]["text"], "日常一行")
        self.assertEqual(body["point_rules"]["text"], "标准一行")
        self.assertEqual([m["text"] for m in body["reminders"]], ["每天提醒"])

    def test_day_switches_reminders_only(self):
        """换日期只影响提醒清单；两段文本是所有天通用的。"""
        self.client.put("/api/daily-routine", json={"text": "通用日常"})
        self.client.post("/api/memos", json={
            "text": "周末提醒", "schedule": {"mode": "weekdays", "weekdays": [5, 6]}})

        sunday = self.client.get("/api/today-view?day=2026-11-01").get_json()
        tuesday = self.client.get("/api/today-view?day=2026-11-03").get_json()
        self.assertEqual([m["text"] for m in sunday["reminders"]], ["周末提醒"])
        self.assertEqual(tuesday["reminders"], [])
        self.assertEqual(sunday["daily_routine"]["text"], "通用日常")
        self.assertEqual(tuesday["daily_routine"]["text"], "通用日常")

    def test_bad_day_returns_400(self):
        self.assertEqual(self.client.get("/api/today-view?day=2026-13-40").status_code, 400)


class MemoScheduleApiTest(ApiTestCase):
    def test_create_with_weekdays(self):
        res = self.client.post("/api/memos", json={
            "text": "每周六日教弟弟编程",
            "schedule": {"mode": "weekdays", "weekdays": [5, 6]}})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["schedule"]["weekdays"], [5, 6])

        listed = self.client.get("/api/memos").get_json()["memos"][0]
        self.assertEqual(listed["when"], "每周六、日")
        self.assertFalse(listed["expired"])

    def test_create_with_monthdays(self):
        res = self.client.post("/api/memos", json={
            "text": "每月 8-9 号交材料",
            "schedule": {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}})
        self.assertEqual(res.get_json()["schedule"]["mode"], "monthdays")
        self.assertEqual(self.client.get("/api/memos").get_json()["memos"][0]["when"],
                         "每月 8–9 号")

    def test_update_changes_only_text(self):
        created = self.client.post("/api/memos", json={
            "text": "原名", "schedule": {"mode": "daily"}}).get_json()
        res = self.client.put(f"/api/memos/{created['id']}", json={"text": "改名"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["text"], "改名")
        self.assertEqual(res.get_json()["schedule"]["mode"], "daily")

    def test_update_missing_memo(self):
        self.assertEqual(self.client.put("/api/memos/nope", json={"text": "x"}).status_code, 404)

    def test_legacy_memo_without_schedule(self):
        d = data.load(config.CURRENT_PROFILE)
        d["memos"].append({"id": "legacy1", "text": "老备忘"})
        data.save(config.CURRENT_PROFILE, d)
        memos = self.client.get("/api/memos").get_json()["memos"]
        self.assertEqual(memos[0]["schedule"]["mode"], "none")
        self.assertEqual(memos[0]["when"], "不设定")
        self.assertFalse(memos[0]["expired"])

    def test_expired_memo_kept_and_flagged(self):
        today = _today()
        long_ago = (today - dt.timedelta(days=30)).isoformat()
        old = (today - dt.timedelta(days=20)).isoformat()
        self.client.post("/api/memos", json={
            "text": "旧的事",
            "schedule": {"mode": "dates", "ranges": [{"from": long_ago, "to": old}]}})
        memos = self.client.get("/api/memos").get_json()["memos"]
        self.assertEqual(len(memos), 1)                 # 没有被自动清理
        self.assertTrue(memos[0]["expired"])

    def test_rejects_empty_text(self):
        self.assertEqual(self.client.post("/api/memos", json={"text": "  "}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
