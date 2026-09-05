"""每日感想 API 测试：/api/notes。"""

import datetime as dt
import unittest

from base import ApiTestCase


class NotesApiTest(ApiTestCase):
    """每日感想：读取、保存（覆盖）、删除。"""

    def _today(self):
        return dt.date.today().isoformat()

    def test_get_missing_returns_null(self):
        r = self.client.get(f"/api/notes?day={self._today()}")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["date"], self._today())
        self.assertIsNone(body["note"])

    def test_save_then_get(self):
        r = self.client.put("/api/notes", json={"day": self._today(), "content": "今天学到了新东西！"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["note"], "今天学到了新东西！")

        r = self.client.get(f"/api/notes?day={self._today()}")
        body = r.get_json()
        self.assertEqual(body["note"], "今天学到了新东西！")

    def test_save_overwrites(self):
        day = self._today()
        self.client.put("/api/notes", json={"day": day, "content": "第一版"})
        r = self.client.put("/api/notes", json={"day": day, "content": "第二版（覆盖）"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f"/api/notes?day={day}")
        self.assertEqual(r.get_json()["note"], "第二版（覆盖）")

    def test_empty_content_rejected(self):
        r = self.client.put("/api/notes", json={"day": self._today(), "content": "   "})
        self.assertEqual(r.status_code, 400)

    def test_bad_day_rejected(self):
        r = self.client.get("/api/notes?day=not-a-date")
        self.assertEqual(r.status_code, 400)

    def test_delete(self):
        day = self._today()
        self.client.put("/api/notes", json={"day": day, "content": "要删掉"})
        r = self.client.delete(f"/api/notes?day={day}")
        self.assertEqual(r.status_code, 200)
        # 删除后再删返回 404
        r = self.client.delete(f"/api/notes?day={day}")
        self.assertEqual(r.status_code, 404)
        # 读取应为空
        r = self.client.get(f"/api/notes?day={day}")
        self.assertIsNone(r.get_json()["note"])

    def test_notes_are_independent_per_day(self):
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        today = self._today()
        self.client.put("/api/notes", json={"day": yesterday, "content": "昨天的事"})
        self.client.put("/api/notes", json={"day": today, "content": "今天的事"})
        r1 = self.client.get(f"/api/notes?day={yesterday}")
        r2 = self.client.get(f"/api/notes?day={today}")
        self.assertEqual(r1.get_json()["note"], "昨天的事")
        self.assertEqual(r2.get_json()["note"], "今天的事")


if __name__ == "__main__":
    unittest.main()