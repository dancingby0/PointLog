"""data.py 数据层测试：读写、归档、损坏恢复。"""

import unittest

import data
from base import DataTestCase


class DataLayerTest(DataTestCase):
    """测试 data.py 的读写、归档、损坏恢复。"""

    def test_new_profile_returns_default(self):
        d = data.load(self.profile)
        self.assertEqual(d["entries"], [])
        self.assertEqual(d["daily_notes"], {})
        self.assertEqual(d["memos"], [])

    def test_old_list_daily_notes_is_migrated(self):
        """早期版本 daily_notes 是数组，读取时应迁移为空字典。"""
        d = data.default_data()
        d["daily_notes"] = []   # 模拟旧数据
        data.save(self.profile, d)
        loaded = data.load(self.profile)
        self.assertEqual(loaded["daily_notes"], {})

    def test_save_then_load_roundtrip(self):
        d = data.default_data()
        d["entries"].append({"id": "1", "ts": "2026-09-05T10:00:00", "points": 1, "content": "hi", "category": None})
        data.save(self.profile, d)
        loaded = data.load(self.profile)
        self.assertEqual(loaded, d)
        self.assertTrue(data.data_path(self.profile).exists())

    def test_corrupt_file_is_backed_up_and_reset(self):
        path = data.data_path(self.profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        d = data.load(self.profile)
        self.assertEqual(d, data.default_data())
        self.assertTrue(path.with_suffix(".json.bak").exists())


if __name__ == "__main__":
    unittest.main()