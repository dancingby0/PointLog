"""档案间打卡记录转移测试：transfer_entries.py（移动 / 复制 / 幂等 / 备份 / 只搬打卡记录）。"""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import transfer_entries


class TransferEntriesTest(unittest.TestCase):
    """转移规则：entries 合并（按 id 去重）、其余数据块不动、写盘前备份。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "data"
        self.account = "Felicia"
        self.src = "e1tTil"
        self.dst = "dancingby"
        self.src_path = self.path_of(self.src)
        self.dst_path = self.path_of(self.dst)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 辅助 ----

    def path_of(self, profile):
        return self.root / self.account / profile / "data.json"

    def _write(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _seed(self):
        """造一份典型数据：源 2 条打卡 + 感想/备忘/主目标，目标 1 条打卡。"""
        self._write(self.src_path, {
            "entries": [
                {"id": "s1", "ts": "2026-10-05T04:00:00.000Z", "points": 2,
                 "content": "证明牛顿二项式定理", "category": "学习"},
                {"id": "s2", "ts": "2026-10-09T11:20:00.000Z", "points": 20,
                 "content": "游泳2公里", "category": ["锻炼"],
                 "start_ts": None, "end_ts": None},
            ],
            "daily_notes": {"2026-09-08": "生日ing"},
            "memos": [{"id": "m1", "text": "隔天游泳"}],
            "main_goal": "学习数学分析",
            "diary_tags": ["数学", "锻炼", "睡眠", "学习办公"],
        })
        self._write(self.dst_path, {
            "entries": [
                {"id": "d1", "ts": "2026-10-10T08:39:00.000Z", "points": 30,
                 "content": "完成国奖答辩", "category": ["学习办公"]},
            ],
            "daily_notes": {"2026-10-10": "完成国奖答辩，和同学去吃烤鱼"},
            "memos": [{"id": "m2", "text": "10/11 8:00 毕业照"}],
            "main_goal": "",
            "diary_tags": ["洗衣服", "刷牙", "睡眠", "学习办公"],
        })

    # ---- 转移 ----

    def test_move_merges_entries_and_clears_source(self):
        self._seed()
        info = transfer_entries.transfer(self.src, self.dst, account=self.account, root=self.root)

        self.assertEqual(info["source_entries"], 2)
        self.assertEqual(info["target_before"], 1)
        self.assertEqual(info["moved"], 2)
        self.assertEqual(info["moved_points"], 22)
        self.assertEqual(info["skipped_existing"], 0)
        self.assertEqual(info["target_after"], 3)
        self.assertTrue(info["written"])

        dst = self._read(self.dst_path)
        self.assertEqual([e["id"] for e in dst["entries"]], ["d1", "s1", "s2"])
        # 目标的私人内容不被覆盖
        self.assertEqual(dst["daily_notes"]["2026-10-10"], "完成国奖答辩，和同学去吃烤鱼")
        self.assertEqual([m["id"] for m in dst["memos"]], ["m2"])
        self.assertEqual(dst["main_goal"], "")

        src = self._read(self.src_path)
        self.assertEqual(src["entries"], [])                        # 转移：源档案打卡记录清空
        self.assertEqual(src["daily_notes"], {"2026-09-08": "生日ing"})  # 感想/备忘/主目标保留
        self.assertEqual([m["id"] for m in src["memos"]], ["m1"])
        self.assertEqual(src["main_goal"], "学习数学分析")

    def test_copy_keeps_source_entries(self):
        self._seed()
        transfer_entries.transfer(self.src, self.dst, account=self.account,
                                  copy_only=True, root=self.root)
        self.assertEqual(len(self._read(self.src_path)["entries"]), 2)   # 复制：源档案不变
        self.assertEqual(len(self._read(self.dst_path)["entries"]), 3)

    def test_transfer_is_idempotent(self):
        self._seed()
        first = transfer_entries.transfer(self.src, self.dst, account=self.account, root=self.root)
        self.assertEqual(first["moved"], 2)
        snapshot = self.dst_path.read_text(encoding="utf-8")

        second = transfer_entries.transfer(self.src, self.dst, account=self.account, root=self.root)
        self.assertEqual(second["moved"], 0)            # 源已空 → 无事可做
        self.assertFalse(second["written"])
        self.assertEqual(self.dst_path.read_text(encoding="utf-8"), snapshot)

    def test_rerun_after_copy_skips_existing_ids(self):
        """复制后再跑：按 id 去重，不会翻倍。"""
        self._seed()
        transfer_entries.transfer(self.src, self.dst, account=self.account,
                                  copy_only=True, root=self.root)
        again = transfer_entries.transfer(self.src, self.dst, account=self.account,
                                          copy_only=True, root=self.root)
        self.assertEqual(again["moved"], 0)
        self.assertEqual(again["skipped_existing"], 2)
        self.assertFalse(again["written"])
        self.assertEqual(len(self._read(self.dst_path)["entries"]), 3)

    def test_dry_run_does_not_write_or_backup(self):
        self._seed()
        before_src = self.src_path.read_text(encoding="utf-8")
        before_dst = self.dst_path.read_text(encoding="utf-8")

        info = transfer_entries.transfer(self.src, self.dst, account=self.account,
                                         dry_run=True, root=self.root)
        self.assertEqual(info["moved"], 2)
        self.assertEqual(info["target_after"], 3)       # 预测值
        self.assertFalse(info["written"])
        self.assertEqual(info["backups"], [])
        self.assertEqual(self.src_path.read_text(encoding="utf-8"), before_src)
        self.assertEqual(self.dst_path.read_text(encoding="utf-8"), before_dst)
        self.assertEqual(list(self.root.rglob("*.bak-transfer-*")), [])

    def test_writes_backups_of_both_files(self):
        self._seed()
        info = transfer_entries.transfer(self.src, self.dst, account=self.account,
                                         root=self.root, stamp="20261011-220000")

        self.assertEqual(len(info["backups"]), 2)
        src_bak = self.src_path.with_name(self.src_path.name + ".bak-transfer-20261011-220000")
        dst_bak = self.dst_path.with_name(self.dst_path.name + ".bak-transfer-20261011-220000")
        for bak in (src_bak, dst_bak):
            self.assertTrue(bak.exists())
        # 备份是"改之前"的状态
        self.assertEqual(len(self._read(src_bak)["entries"]), 2)
        self.assertEqual(len(self._read(dst_bak)["entries"]), 1)

    def test_backup_never_overwrites_an_existing_one(self):
        self._seed()
        first = transfer_entries._backup(self.dst_path, "s")
        second = transfer_entries._backup(self.dst_path, "s")
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_merge_tags_unions_category_pool(self):
        self._seed()
        info = transfer_entries.transfer(self.src, self.dst, account=self.account, root=self.root)
        self.assertEqual(info["tags_added"], ["数学", "锻炼"])
        self.assertEqual(self._read(self.dst_path)["diary_tags"],
                         ["洗衣服", "刷牙", "睡眠", "学习办公", "数学", "锻炼"])

    def test_merge_tags_can_be_disabled(self):
        self._seed()
        transfer_entries.transfer(self.src, self.dst, account=self.account,
                                  merge_tags=False, root=self.root)
        self.assertEqual(self._read(self.dst_path)["diary_tags"],
                         ["洗衣服", "刷牙", "睡眠", "学习办公"])

    def test_duplicate_hint_is_reported_but_kept(self):
        """内容 + 点数 + 日期都相同 → 提示疑似重复，但仍按 id 正常搬入（不静默删）。"""
        self._write(self.src_path, {"entries": [
            {"id": "s1", "ts": "2026-10-10T08:39:00.000Z", "points": 30, "content": "完成国奖答辩"},
        ]})
        self._write(self.dst_path, {"entries": [
            {"id": "d1", "ts": "2026-10-10T08:39:00.000Z", "points": 30, "content": "完成国奖答辩"},
        ]})
        info = transfer_entries.transfer(self.src, self.dst, account=self.account, root=self.root)
        self.assertEqual(len(info["duplicate_hints"]), 1)
        self.assertEqual(info["moved"], 1)
        self.assertEqual(len(self._read(self.dst_path)["entries"]), 2)

    # ---- 异常与布局 ----

    def test_same_profile_is_rejected(self):
        self._seed()
        with self.assertRaises(ValueError):
            transfer_entries.transfer(self.src, self.src, account=self.account, root=self.root)

    def test_missing_target_profile_is_rejected(self):
        self._seed()
        with self.assertRaises(ValueError) as ctx:
            transfer_entries.transfer(self.src, "nope", account=self.account, root=self.root)
        self.assertIn("不存在", str(ctx.exception))
        self.assertEqual(len(self._read(self.src_path)["entries"]), 2)   # 未被改动

    def test_legacy_layout_without_account(self):
        """无账号旧布局：data/<档案>/data.json。"""
        src = self.root / self.src / "data.json"
        dst = self.root / self.dst / "data.json"
        self._write(src, {"entries": [{"id": "s1", "ts": "2026-10-05T04:00:00.000Z",
                                       "points": 1, "content": "x"}]})
        self._write(dst, {"entries": []})
        info = transfer_entries.transfer(self.src, self.dst, root=self.root)
        self.assertEqual(info["moved"], 1)
        self.assertEqual(len(self._read(dst)["entries"]), 1)
        self.assertEqual(self._read(src)["entries"], [])

    def test_main_dry_run_prints_summary(self):
        self._seed()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = transfer_entries.main(["--from", self.src, "--to", self.dst,
                                          "--account", self.account,
                                          "--data-dir", str(self.root), "--dry-run"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[dry-run]", out)
        self.assertIn("搬入 2 条 / 22 点", out)
        self.assertIn("（未写盘）", out)

    def test_main_reports_error_with_nonzero_code(self):
        self._seed()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = transfer_entries.main(["--from", self.src, "--to", "nope",
                                          "--account", self.account,
                                          "--data-dir", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("×", buf.getvalue())


if __name__ == "__main__":
    unittest.main()


