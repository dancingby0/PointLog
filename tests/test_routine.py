"""备忘时间范围匹配测试（routine.py 纯函数）+ 多行文本规范化（textblock.py）。"""

import datetime as dt
import unittest

import routine
import textblock


def D(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


class ScheduleNormalizeTest(unittest.TestCase):
    def test_none_mode_by_default(self):
        self.assertEqual(routine.normalize_schedule(None)["mode"], "none")
        self.assertEqual(routine.normalize_schedule({})["mode"], "none")
        self.assertEqual(routine.normalize_schedule("垃圾")["mode"], "none")

    def test_dates_ranges_swapped_and_invalid_dropped(self):
        sch = routine.normalize_schedule({"mode": "dates", "ranges": [
            {"from": "2026-10-09", "to": "2026-10-08"},     # 写反 → 交换
            {"from": "2026-10-11", "to": "2026-10-12"},
            {"from": "坏的", "to": "2026-10-12"},            # 丢掉
            {"from": "2026-10-20"},                          # 只给起点 → 单日
        ]})
        self.assertEqual(sch["ranges"], [
            {"from": "2026-10-08", "to": "2026-10-09"},
            {"from": "2026-10-11", "to": "2026-10-12"},
            {"from": "2026-10-20", "to": "2026-10-20"},
        ])

    def test_monthdays_clamped_and_swapped(self):
        sch = routine.normalize_schedule({"mode": "monthdays", "monthdays": [
            {"from": 8, "to": 9}, {"from": 12, "to": 11}, {"from": 0, "to": 5},
            {"from": 30, "to": 99},
        ]})
        self.assertEqual(sch["monthdays"], [
            {"from": 8, "to": 9}, {"from": 11, "to": 12}, {"from": 30, "to": 31},
        ])

    def test_empty_selection_degrades_to_none(self):
        for mode in ("dates", "monthdays", "weekdays"):
            self.assertEqual(routine.normalize_schedule({"mode": mode})["mode"], "none", msg=mode)


class MemoActiveTest(unittest.TestCase):
    def test_daily_always_active(self):
        sch = {"mode": "daily"}
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-11")))
        self.assertTrue(routine.memo_active_on(sch, D("2030-01-01")))

    def test_dates_inclusive_both_ends(self):
        sch = {"mode": "dates", "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-07")))
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-08")))
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-09")))
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-10")))

    def test_monthdays_every_month(self):
        sch = {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-08")))
        self.assertTrue(routine.memo_active_on(sch, D("2027-03-09")))    # 换年换月照样生效
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-10")))

    def test_weekdays_multiple(self):
        """2026-11-01 周日、11-02 周一、11-07 周六。"""
        sch = {"mode": "weekdays", "weekdays": [5, 6]}
        self.assertTrue(routine.memo_active_on(sch, D("2026-11-01")))
        self.assertFalse(routine.memo_active_on(sch, D("2026-11-02")))
        self.assertTrue(routine.memo_active_on(sch, D("2026-11-07")))

    def test_weekdays_sorted_and_deduped(self):
        sch = routine.normalize_schedule({"mode": "weekdays",
                                          "weekdays": [6, 5, 5, 9, "1", "x"]})
        self.assertEqual(sch["weekdays"], [1, 5, 6])       # 9/x 丢弃、去重、升序

    def test_none_never_active(self):
        self.assertFalse(routine.memo_active_on({"mode": "none"}, D("2026-10-11")))

    def test_switching_mode_keeps_other_fields(self):
        """来回切模式不丢已填内容。"""
        sch = routine.normalize_schedule({
            "mode": "weekdays", "weekdays": [6],
            "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}],
            "monthdays": [{"from": 8, "to": 9}],
        })
        self.assertEqual(len(sch["ranges"]), 1)
        self.assertEqual(len(sch["monthdays"]), 1)
        self.assertEqual(sch["weekdays"], [6])



class MemoExpiredTest(unittest.TestCase):
    def test_dates_expire_after_last_day(self):
        sch = {"mode": "dates", "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}
        self.assertFalse(routine.memo_expired(sch, D("2026-10-09")))    # 末日不算过期
        self.assertTrue(routine.memo_expired(sch, D("2026-10-10")))

    def test_looping_modes_never_expire(self):
        for sch in ({"mode": "daily"},
                    {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]},
                    {"mode": "weekdays", "weekdays": [6]},
                    {"mode": "none"}):
            self.assertFalse(routine.memo_expired(sch, D("2030-01-01")), msg=str(sch))


class ScheduleTextTest(unittest.TestCase):
    def test_texts(self):
        self.assertEqual(routine.schedule_text({"mode": "none"}), "不设定")
        self.assertEqual(routine.schedule_text({"mode": "daily"}), "每天")
        self.assertEqual(routine.schedule_text(
            {"mode": "dates", "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}),
            "2026-10-08~2026-10-09")
        self.assertEqual(routine.schedule_text(
            {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}), "每月 8–9 号")
        self.assertEqual(routine.schedule_text({"mode": "weekdays", "weekdays": [5, 6]}),
                         "每周六、日")
        self.assertEqual(routine.schedule_text(
            {"mode": "weekdays", "weekdays": [0, 1, 2, 3, 4, 5, 6]}), "每天")


class DayRemindersTest(unittest.TestCase):
    DAY = dt.date(2026, 10, 11)

    def test_only_active_memos_and_expired_sorted_last(self):
        memos = [
            {"id": "a", "text": "过期的", "schedule": {"mode": "dates", "ranges": [
                {"from": "2026-10-10", "to": "2026-10-11"}]}},
            {"id": "b", "text": "每天", "schedule": {"mode": "daily"}},
            {"id": "c", "text": "不设定", "schedule": {"mode": "none"}},
            {"id": "d", "text": "没到日子", "schedule": {"mode": "dates", "ranges": [
                {"from": "2026-11-01", "to": "2026-11-02"}]}},
        ]
        out = routine.day_reminders(memos, self.DAY, today=dt.date(2026, 10, 12))
        self.assertEqual([m["text"] for m in out], ["每天", "过期的"])
        self.assertFalse(out[0]["expired"])
        self.assertTrue(out[1]["expired"])


class TextBlockTest(unittest.TestCase):
    def test_keeps_newlines_and_trims_edges(self):
        raw = "\n\n第一行  \n第二行\n\n\n第三行\n\n"
        # 首尾空行去掉、行尾空白去掉，但中间的换行（含空行）原样保留
        self.assertEqual(textblock.normalize_text(raw), "第一行\n第二行\n\n\n第三行")

    def test_normalizes_crlf(self):
        self.assertEqual(textblock.normalize_text("a\r\nb\rc"), "a\nb\nc")

    def test_empty_variants(self):
        for raw in (None, "", "   \n\n  "):
            self.assertEqual(textblock.normalize_text(raw), "")

    def test_accepts_list_for_compat(self):
        self.assertEqual(textblock.normalize_text(["a", " ", "b"]), "a\nb")

    def test_truncates_over_long_text(self):
        self.assertEqual(len(textblock.normalize_text("x" * 9999)), textblock.MAX_TEXT)

    def test_text_stats(self):
        stats = textblock.text_stats("abc\ndef\n\n")
        self.assertEqual(stats["lines"], 2)
        self.assertEqual(stats["chars"], 6)
        self.assertFalse(stats["empty"])
        self.assertTrue(textblock.text_stats("  \n ")["empty"])


if __name__ == "__main__":
    unittest.main()
