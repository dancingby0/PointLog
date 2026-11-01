"""每日日常 + 备忘时间范围的 API 测试。"""

import datetime as dt
import unittest

import config
import data
import utils
from tests.base import ApiTestCase


def _today():
    return utils.date_of(dt.datetime.now().astimezone())


class RoutineApiTest(ApiTestCase):
    def test_create_list_update_delete(self):
        res = self.client.post("/api/routines", json={
            "start": "08:00", "end": "09:00", "text": "晨读", "points": 2, "days": [0, 2]})
        self.assertEqual(res.status_code, 201)
        item = res.get_json()
        self.assertTrue(item["id"])

        body = self.client.get("/api/routines").get_json()
        self.assertEqual([r["text"] for r in body["routines"]], ["晨读"])

        upd = self.client.put(f"/api/routines/{item['id']}", json={"points": 3})
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.get_json()["points"], 3)
        self.assertEqual(upd.get_json()["text"], "晨读")      # 未传的字段保持原值

        self.assertEqual(self.client.delete(f"/api/routines/{item['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/routines").get_json()["routines"], [])

    def test_rejects_invalid_item(self):
        res = self.client.post("/api/routines", json={"start": "09:00", "end": "08:00",
                                                     "text": "反了"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("结束时间", res.get_json()["error"])

    def test_missing_routine_returns_404(self):
        self.assertEqual(self.client.put("/api/routines/nope", json={"text": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/routines/nope").status_code, 404)


class ScheduleApiTest(ApiTestCase):
    def test_empty_day(self):
        body = self.client.get("/api/schedule").get_json()
        self.assertEqual(body["day"], _today().isoformat())
        self.assertEqual(body["items"], [])
        self.assertEqual(body["reminders"], [])
        self.assertEqual(body["planned_points"], 0)

    def test_day_filters_by_weekday(self):
        target = dt.date(2026, 11, 2)          # 周一
        self.client.post("/api/routines", json={
            "start": "08:00", "end": "09:00", "text": "周一专用", "points": 1, "days": [0]})
        self.client.post("/api/routines", json={
            "start": "10:00", "end": "11:00", "text": "每天", "points": 2})

        monday = self.client.get(f"/api/schedule?day={target.isoformat()}").get_json()
        self.assertEqual([i["text"] for i in monday["items"]], ["周一专用", "每天"])
        self.assertEqual(monday["planned_points"], 3)

        sunday = self.client.get("/api/schedule?day=2026-11-01").get_json()
        self.assertEqual([i["text"] for i in sunday["items"]], ["每天"])
        self.assertEqual(sunday["planned_points"], 2)

    def test_bad_day_returns_400(self):
        self.assertEqual(self.client.get("/api/schedule?day=2026-13-40").status_code, 400)


    def test_memo_reminders_follow_schedule(self):
        """备忘带日期段：生效日出现在日常里，过期后不在这天显示。"""
        today = _today()
        past = (today - dt.timedelta(days=10)).isoformat()
        long_ago = (today - dt.timedelta(days=20)).isoformat()
        self.client.post("/api/memos", json={
            "text": "已过期的备忘",
            "schedule": {"mode": "dates", "ranges": [{"from": long_ago, "to": past}]}})
        self.client.post("/api/memos", json={
            "text": "每天提醒", "schedule": {"mode": "daily"}})
        self.client.post("/api/memos", json={"text": "无时间"})

        view = self.client.get(f"/api/schedule?day={today.isoformat()}").get_json()
        texts = [m["text"] for m in view["reminders"]]
        self.assertIn("每天提醒", texts)
        self.assertNotIn("无时间", texts)                  # mode=none 不进日常
        self.assertNotIn("已过期的备忘", texts)             # 已过生效期 → 不在这天显示

        # 回到生效期内那天：仍会显示；但它相对"今天"已过期 → 标红（不随查看日改变）
        inside = (today - dt.timedelta(days=15)).isoformat()
        view2 = self.client.get(f"/api/schedule?day={inside}").get_json()
        hit = next(m for m in view2["reminders"] if m["text"] == "已过期的备忘")
        self.assertTrue(hit["expired"])

    def test_expired_memo_still_listed_and_flagged(self):
        """过期不删除：/api/memos 里仍在，且 expired=true。"""
        today = _today()
        long_ago = (today - dt.timedelta(days=30)).isoformat()
        old = (today - dt.timedelta(days=20)).isoformat()
        created = self.client.post("/api/memos", json={
            "text": "旧的事",
            "schedule": {"mode": "dates", "ranges": [{"from": long_ago, "to": old}]}})
        self.assertEqual(created.status_code, 201)

        memos = self.client.get("/api/memos").get_json()["memos"]
        item = next(m for m in memos if m["text"] == "旧的事")
        self.assertTrue(item["expired"])
        self.assertIn("~", item["when"])
        self.assertEqual(len(memos), 1)                    # 没有被自动清理


class MemoScheduleApiTest(ApiTestCase):
    def test_create_with_monthdays(self):
        res = self.client.post("/api/memos", json={
            "text": "每月 8-9 号交材料",
            "schedule": {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["schedule"]["mode"], "monthdays")

        listed = self.client.get("/api/memos").get_json()["memos"][0]
        self.assertEqual(listed["when"], "每月 8–9 号")

    def test_update_changes_only_text(self):
        created = self.client.post("/api/memos", json={
            "text": "原名", "schedule": {"mode": "daily"}}).get_json()
        res = self.client.put(f"/api/memos/{created['id']}", json={"text": "改名"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["text"], "改名")
        self.assertEqual(res.get_json()["schedule"]["mode"], "daily")   # 时间范围保留

    def test_update_missing_memo(self):
        self.assertEqual(self.client.put("/api/memos/nope", json={"text": "x"}).status_code, 404)

    def test_legacy_memo_without_schedule_still_works(self):
        """老数据没有 schedule 字段：读出来是 mode=none，不报错。"""
        d = data.load(config.CURRENT_PROFILE)
        d["memos"].append({"id": "legacy1", "text": "老备忘"})
        data.save(config.CURRENT_PROFILE, d)

        memos = self.client.get("/api/memos").get_json()["memos"]
        self.assertEqual(memos[0]["schedule"]["mode"], "none")
        self.assertFalse(memos[0]["expired"])
        self.assertEqual(memos[0]["when"], "不设定")

    def test_rejects_empty_text(self):
        self.assertEqual(self.client.post("/api/memos", json={"text": "  "}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
