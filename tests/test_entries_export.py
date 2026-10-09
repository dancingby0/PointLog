"""打卡记录导出 API 测试：/api/entries/export。"""

import json
import unittest
from pathlib import Path
from urllib.parse import unquote

import config
import data
from base import ApiTestCase


class EntriesExportApiTest(ApiTestCase):
    """打卡导出：按归属日区间筛选、时间升序、落盘/下载、参数校验。"""

    def _add(self, ts, content, points=1, start=None, end=None, category=None):
        body = {"content": content, "points": points, "ts": ts}
        if start and end:
            body["start_ts"] = start
            body["end_ts"] = end
        if category is not None:
            body["category"] = category
        r = self.client.post("/api/entries", json=body)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def _seed(self):
        """故意乱序写入；含一条带时段、一条 0 点（只记录）。"""
        self._add("2026-09-15T10:00:00+08:00", "b-中", 2)
        self._add("2026-09-01T09:00:00+08:00", "a-早", 1,
                  start="2026-09-01T08:00:00+08:00", end="2026-09-01T09:30:00+08:00")
        self._add("2026-10-01T08:00:00+08:00", "d-晚", 0)
        self._add("2026-09-30T23:30:00+08:00", "c-次晚", 3)

    def _export(self, query=""):
        """调用导出接口（默认模式：落盘 exports/ 并返回落盘信息）。"""
        r = self.client.get(f"/api/entries/export{query}")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def _exported_body(self, info):
        """读回已导出的 JSON 文件内容。"""
        p = Path(info["abs_path"])
        self.assertTrue(p.exists(), f"导出文件应已落盘: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_export_entries_saves_to_exports_dir(self):
        self._seed()

        info = self._export("?from=2026-09-01&to=2026-09-30")
        self.assertTrue(info["ok"])
        self.assertEqual(info["range"], {"from": "2026-09-01", "to": "2026-09-30"})
        self.assertEqual(info["entry_count"], 3)
        self.assertEqual(info["day_count"], 3)
        self.assertEqual(info["total_points"], 6)          # 1 + 2 + 3
        self.assertEqual(info["total_duration_min"], 90)   # 仅 a-早 填了时段
        self.assertTrue(info["filename"].startswith("entries-2026-09-01_2026-09-30-"))
        self.assertIn("exports/", info["rel_path"])
        self.assertTrue(info["rel_path"].endswith(info["filename"]))
        self.assertGreater(info["bytes"], 0)

        body = self._exported_body(info)
        self.assertEqual(body["meta"]["range"], {"from": "2026-09-01", "to": "2026-09-30"})
        self.assertEqual(body["meta"]["profile"], self.profile)
        self.assertEqual(body["meta"]["entry_count"], 3)
        self.assertEqual(body["meta"]["total_duration_min"], 90)
        # 升序（早 → 晚）
        self.assertEqual([e["content"] for e in body["entries"]], ["a-早", "b-中", "c-次晚"])

        by_content = {e["content"]: e for e in body["entries"]}
        self.assertEqual(by_content["a-早"]["day"], "2026-09-01")
        self.assertEqual(by_content["a-早"]["duration_min"], 90)
        self.assertIsNone(by_content["b-中"]["start_ts"])   # 未选时间
        self.assertIsNone(by_content["b-中"]["duration_min"])
        # 23:30 仍归属当日（凌晨 4 点界）
        self.assertEqual(by_content["c-次晚"]["day"], "2026-09-30")

        # 同一秒内再次导出 → 不覆盖，文件名加序号
        again = self._export("?from=2026-09-01&to=2026-09-30")
        self.assertNotEqual(again["filename"], info["filename"])
        self.assertEqual(len(list(Path(info["dir"]).glob("*.json"))), 2)

        # 不传参数 = 全部（含 0 点的 d-晚），仍按时间升序
        all_info = self._export()
        self.assertEqual(all_info["range"], {"from": None, "to": None})
        self.assertEqual(
            [e["content"] for e in self._exported_body(all_info)["entries"]],
            ["a-早", "b-中", "c-次晚", "d-晚"])

        # 只给一端（to）：含该日及之前
        head = self._export("?to=2026-09-15")
        self.assertEqual(
            [e["content"] for e in self._exported_body(head)["entries"]], ["a-早", "b-中"])

    def test_export_entries_download_mode(self):
        """download=1：走附件下载（不落盘），文件名由后端给定。"""
        self._seed()

        before = self._export("?from=2026-09-01&to=2026-09-30")
        out_dir = Path(before["dir"])
        count_before = len(list(out_dir.glob("*.json")))
        self.assertEqual(count_before, 1)

        r = self.client.get("/api/entries/export?from=2026-09-01&to=2026-09-30&download=1")
        self.assertEqual(r.status_code, 200)
        cd = r.headers.get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn("entries-2026-09-01_2026-09-30-", unquote(cd))
        body = json.loads(r.data.decode("utf-8"))
        self.assertEqual([e["content"] for e in body["entries"]], ["a-早", "b-中", "c-次晚"])
        # 下载模式不额外落盘
        self.assertEqual(len(list(out_dir.glob("*.json"))), count_before)

    def test_export_entries_category_is_list(self):
        """导出 category 恒为字符串数组（可多选）；老数据的单值写法读时规范化。"""
        self._add("2026-09-10T13:00:00+08:00", "多类别", 2, category=["学习", "数学"])
        d = data.load(config.CURRENT_PROFILE)
        d["entries"].append({"id": "legacy", "ts": "2026-09-10T12:00:00+08:00",
                             "points": 1, "content": "老记录", "category": "洗衣服"})
        data.save(config.CURRENT_PROFILE, d)

        body = self._exported_body(self._export("?from=2026-09-10&to=2026-09-10"))
        by_content = {e["content"]: e for e in body["entries"]}
        self.assertEqual(by_content["多类别"]["category"], ["学习", "数学"])
        self.assertEqual(by_content["老记录"]["category"], ["洗衣服"])

    def test_export_entries_validation(self):
        """非法区间/格式返回 400，且不产生任何文件。"""
        self._seed()
        self.assertEqual(self.client.get("/api/entries/export?from=2026/09/01").status_code, 400)
        self.assertEqual(
            self.client.get("/api/entries/export?from=2026-09-30&to=2026-09-01").status_code, 400)
        self.assertEqual(self.client.get("/api/entries/export?to=abc").status_code, 400)


if __name__ == "__main__":
    unittest.main()
