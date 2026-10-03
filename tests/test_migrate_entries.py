"""历史打卡记录迁移测试：migrate_entries.py（旧记录统一改为"不选时间"）。"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import migrate_entries
from utils import date_of, parse_ts


class MigrateEntriesTest(unittest.TestCase):
    """迁移规则：ts 规范化为归属日 12:00（本地）、start/end 置 null、归属日与点数不变。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "acct" / "prof" / "data.json"
        self.path.parent.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, entries):
        self.path.write_text(
            json.dumps({"entries": entries, "daily_notes": {}}, ensure_ascii=False),
            encoding="utf-8")

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_migrate_normalizes_ts_and_clears_span(self):
        self._write([
            # 旧记录（UTC 带 Z）：本地 +08 为 09-23 21:07 → 归属日 09-23
            {"id": "1", "ts": "2026-09-23T13:07:00.000Z", "points": 1,
             "content": "x", "category": "洗衣服"},
            # 旧记录（凌晨 2:30 → 按 4 点规则归属前一天 09-23）
            {"id": "2", "ts": "2026-09-24T02:30:00+08:00", "points": 2,
             "content": "y", "category": None,
             "start_ts": "2026-09-24T01:00:00+08:00", "end_ts": "2026-09-24T02:00:00+08:00"},
        ])

        info = migrate_entries.migrate_profile_file(self.path)
        self.assertEqual(info["entries"], 2)
        self.assertEqual(info["changed"], 2)
        self.assertEqual(info["skipped"], 0)

        entries = self._read()["entries"]
        for e in entries:
            # 归属日不变 + ts 规范化为该日 12:00（本地）
            day = date_of(parse_ts(e["ts"]))
            self.assertEqual(parse_ts(e["ts"]).hour, 12)
            self.assertIsNone(e["start_ts"])
            self.assertIsNone(e["end_ts"])
        self.assertEqual(date_of(parse_ts(entries[0]["ts"])).isoformat(), "2026-09-23")
        self.assertEqual(date_of(parse_ts(entries[1]["ts"])).isoformat(), "2026-09-23")
        # 内容与点数保持不变
        self.assertEqual(entries[0]["points"], 1)
        self.assertEqual(entries[0]["category"], "洗衣服")
        self.assertEqual(entries[1]["points"], 2)

    def test_migrate_is_idempotent(self):
        self._write([{"id": "1", "ts": "2026-09-23T13:07:00.000Z", "points": 1, "content": "x"}])
        first = migrate_entries.migrate_profile_file(self.path)
        self.assertEqual(first["changed"], 1)
        snapshot = self.path.read_text(encoding="utf-8")
        # 再跑一次：无改动，文件字节不变
        second = migrate_entries.migrate_profile_file(self.path)
        self.assertEqual(second["changed"], 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), snapshot)

    def test_dry_run_does_not_write(self):
        self._write([{"id": "1", "ts": "2026-09-23T13:07:00.000Z", "points": 1, "content": "x"}])
        snapshot = self.path.read_text(encoding="utf-8")
        info = migrate_entries.migrate_profile_file(self.path, dry_run=True)
        self.assertEqual(info["changed"], 1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), snapshot)

    def test_unparsable_ts_is_skipped(self):
        self._write([{"id": "1", "ts": "not-a-time", "points": 1, "content": "x"}])
        info = migrate_entries.migrate_profile_file(self.path)
        self.assertEqual(info["changed"], 0)
        self.assertEqual(info["skipped"], 1)
        self.assertEqual(self._read()["entries"][0]["ts"], "not-a-time")

    def test_migration_creates_backup(self):
        """改写前留下 data.json.bak 备份（便于回退）。"""
        self._write([{"id": "1", "ts": "2026-09-23T13:07:00.000Z", "points": 1, "content": "x"}])
        migrate_entries.migrate_profile_file(self.path)
        backup = self.path.with_suffix(".json.bak")
        self.assertTrue(backup.exists())
        raw = json.loads(backup.read_text(encoding="utf-8"))
        self.assertEqual(raw["entries"][0]["ts"], "2026-09-23T13:07:00.000Z")

    def test_migrate_all_finds_account_scoped_files(self):
        self._write([{"id": "1", "ts": "2026-09-23T13:07:00.000Z", "points": 1, "content": "x"}])
        # 账号层第二个档案
        other = self.root / "acct" / "prof2" / "data.json"
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps({"entries": [
            {"id": "2", "ts": "2026-09-24T10:00:00+08:00", "points": 0, "content": "z"}
        ]}, ensure_ascii=False), encoding="utf-8")

        summary = migrate_entries.migrate_all(self.root)
        self.assertEqual(summary["files"], 2)
        self.assertEqual(summary["entries"], 2)
        self.assertEqual(summary["changed"], 2)
        self.assertEqual(len(summary["details"]), 2)
        self.assertEqual(
            json.loads(other.read_text(encoding="utf-8"))["entries"][0]["start_ts"], None)


if __name__ == "__main__":
    unittest.main()
