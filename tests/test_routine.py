"""routine.py 测试：备忘时间范围匹配 + 日常筛选（纯函数）。"""

import datetime as dt
import unittest

import routine


def D(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


class ScheduleNormalizeTest(unittest.TestCase):
    def test_none_mode_by_default(self):
        self.assertEqual(routine.normalize_schedule(None)["mode"], "none")
        self.assertEqual(routine.normalize_schedule({})["mode"], "none")
        self.assertEqual(routine.normalize_schedule("垃圾")["mode"], "none")

    def test_dates_ranges_sorted_and_swapped(self):
        sch = routine.normalize_schedule({"mode": "dates", "ranges": [
            {"from": "2026-10-09", "to": "2026-10-08"},     # 写反 → 交换
            {"from": "2026-10-11", "to": "2026-10-12"},
            {"from": "坏的", "to": "2026-10-12"},            # 丢掉
            {"from": "2026-10-20"},                          # 只给起点 → 单日
        ]})
        self.assertEqual(sch["mode"], "dates")
        self.assertEqual(sch["ranges"], [
            {"from": "2026-10-08", "to": "2026-10-09"},
            {"from": "2026-10-11", "to": "2026-10-12"},
            {"from": "2026-10-20", "to": "2026-10-20"},
        ])

    def test_dates_without_ranges_degrades_to_none(self):
        self.assertEqual(routine.normalize_schedule({"mode": "dates", "ranges": []})["mode"], "none")

    def test_monthdays_clamped(self):
        sch = routine.normalize_schedule({"mode": "monthdays", "monthdays": [
            {"from": 8, "to": 9},
            {"from": 12, "to": 11},     # 写反 → 交换
            {"from": 0, "to": 5},       # 非法 → 丢
            {"from": 30, "to": 99},     # 终点夹到 31
        ]})
        self.assertEqual(sch["monthdays"], [
            {"from": 8, "to": 9},
            {"from": 11, "to": 12},
            {"from": 30, "to": 31},
        ])

    def test_monthdays_without_items_degrades_to_none(self):
        self.assertEqual(
            routine.normalize_schedule({"mode": "monthdays", "monthdays": []})["mode"], "none")


class MemoActiveTest(unittest.TestCase):
    def test_daily(self):
        sch = {"mode": "daily"}
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-11")))
        self.assertTrue(routine.memo_active_on(sch, D("2030-01-01")))

    def test_dates_inclusive_both_ends(self):
        sch = {"mode": "dates", "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-07")))
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-08")))   # 闭区间
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-09")))   # 闭区间
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-10")))

    def test_monthdays_matches_every_month(self):
        sch = {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}
        self.assertTrue(routine.memo_active_on(sch, D("2026-10-08")))
        self.assertTrue(routine.memo_active_on(sch, D("2027-03-09")))   # 换年换月照样生效
        self.assertFalse(routine.memo_active_on(sch, D("2026-10-10")))

    def test_none_mode_never_active(self):
        self.assertFalse(routine.memo_active_on({"mode": "none"}, D("2026-10-11")))


class MemoExpiredTest(unittest.TestCase):
    def test_dates_expires_after_end(self):
        sch = {"mode": "dates", "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}
        self.assertFalse(routine.memo_expired(sch, D("2026-10-09")))   # 最后一天不算过期
        self.assertTrue(routine.memo_expired(sch, D("2026-10-10")))

    def test_daily_never_expires(self):
        self.assertFalse(routine.memo_expired({"mode": "daily"}, D("2030-01-01")))

    def test_monthdays_never_expires(self):
        sch = {"mode": "monthdays", "monthdays": [{"from": 8, "to": 9}]}
        self.assertFalse(routine.memo_expired(sch, D("2030-01-01")))

    def test_none_never_expires(self):
        self.assertFalse(routine.memo_expired({"mode": "none"}, D("2030-01-01")))


class RoutineItemTest(unittest.TestCase):
    def test_normalize_basic(self):
        item = routine.normalize_routine_item(
            {"start": "8:00", "end": "9:05", "text": " 晨读 ", "points": "2"})
        self.assertEqual(item["start"], "08:00")
        self.assertEqual(item["end"], "09:05")
        self.assertEqual(item["text"], "晨读")
        self.assertEqual(item["points"], 2)
        self.assertEqual(item["days"], [])
        self.assertTrue(item["enabled"])

    def test_hhmm_variants(self):
        for raw, want in [("8", "08:00"), ("0800", "08:00"), ("23:30", "23:30"),
                          ("7：5", "07:05"), ("24", "00:00")]:
            self.assertEqual(routine.normalize_routine_item(
                {"start": raw, "end": "23:59", "text": "x"})["start"], want, msg=raw)

    def test_rejects_bad_input(self):
        bad = [
            {"start": "08:00", "end": "09:00", "text": "  "},          # 空内容
            {"start": "", "end": "09:00", "text": "x"},                # 缺开始
            {"start": "09:00", "end": "09:00", "text": "x"},            # 结束不晚于开始
            {"start": "08:00", "end": "09:00", "text": "x", "points": "abc"},
            {"start": "08:00", "end": "09:00", "text": "x", "points": -1},
            {"start": "08:00", "end": "09:00", "text": "x" * 61},
        ]
        for payload in bad:
            with self.assertRaises(ValueError, msg=str(payload)):
                routine.normalize_routine_item(payload)

    def test_days_dedup_and_sorted(self):
        item = routine.normalize_routine_item(
            {"start": "08:00", "end": "09:00", "text": "x", "days": [5, 2, 2, 9, "3"]})
        self.assertEqual(item["days"], [2, 3, 5])          # 9 越界被丢，重复去掉

    def test_fractional_points_kept(self):
        self.assertEqual(routine.normalize_routine_item(
            {"start": "08:00", "end": "09:00", "text": "x", "points": 1.5})["points"], 1.5)


class RoutineForDayTest(unittest.TestCase):
    """2026-11-01 是周日（weekday=6），2026-11-02 周一（weekday=0）。"""

    SUNDAY = dt.date(2026, 11, 1)
    MONDAY = dt.date(2026, 11, 2)

    def test_everyday_items_always_included(self):
        routines = [{"id": "1", "start": "08:00", "end": "09:00", "text": "晨读", "points": 2}]
        self.assertEqual(len(routine.routine_for_day(routines, self.SUNDAY)), 1)
        self.assertEqual(len(routine.routine_for_day(routines, self.MONDAY)), 1)

    def test_weekday_filter(self):
        routines = [{"id": "1", "start": "08:00", "end": "09:00", "text": "上课",
                     "points": 3, "days": [0]}]                  # 只周一
        self.assertEqual(routine.routine_for_day(routines, self.SUNDAY), [])
        self.assertEqual(len(routine.routine_for_day(routines, self.MONDAY)), 1)

    def test_disabled_items_skipped(self):
        routines = [{"id": "1", "start": "08:00", "end": "09:00", "text": "x", "enabled": False}]
        self.assertEqual(routine.routine_for_day(routines, self.SUNDAY), [])

    def test_broken_items_do_not_break_page(self):
        routines = [{"id": "bad", "start": "xx", "text": "坏"},
                    {"id": "ok", "start": "08:00", "end": "09:00", "text": "好"}]
        items = routine.routine_for_day(routines, self.SUNDAY)
        self.assertEqual([i["text"] for i in items], ["好"])

    def test_sorted_by_start_time(self):
        routines = [{"id": "b", "start": "20:00", "end": "21:00", "text": "晚上"},
                    {"id": "a", "start": "07:00", "end": "08:00", "text": "早上"}]
        self.assertEqual([i["text"] for i in routine.routine_for_day(routines, self.SUNDAY)],
                         ["早上", "晚上"])


class DayScheduleTest(unittest.TestCase):
    DAY = dt.date(2026, 10, 11)

    def test_merges_routines_and_matching_memos(self):
        routines = [{"id": "r1", "start": "08:00", "end": "09:00", "text": "晨读", "points": 2},
                    {"id": "r2", "start": "20:00", "end": "21:00", "text": "运动", "points": 5}]
        memos = [
            {"id": "m1", "text": "开组会", "schedule": {"mode": "dates",
                                                     "ranges": [{"from": "2026-10-08",
                                                                 "to": "2026-10-09"}]}},
            {"id": "m2", "text": "交表格", "schedule": {"mode": "dates",
                                                     "ranges": [{"from": "2026-10-10",
                                                                 "to": "2026-10-12"}]}},
            {"id": "m3", "text": "纯备忘", "schedule": {"mode": "none"}},
            {"id": "m4", "text": "每天喝水", "schedule": {"mode": "daily"}},
        ]
        view = routine.day_schedule(routines, memos, self.DAY, today=dt.date(2026, 10, 20))
        self.assertEqual([i["text"] for i in view["items"]], ["晨读", "运动"])
        self.assertEqual(view["planned_points"], 7)
        self.assertEqual([m["text"] for m in view["reminders"]], ["每天喝水", "交表格"])
        self.assertEqual(view["weekday_label"], "日")
        # 已过 10-12 → 标过期（不删）
        expired = {m["text"]: m["expired"] for m in view["reminders"]}
        self.assertTrue(expired["交表格"])
        self.assertFalse(expired["每天喝水"])

    def test_expired_sorted_last(self):
        memos = [{"id": "a", "text": "过期的", "schedule": {"mode": "dates",
                                                         "ranges": [{"from": "2026-10-11",
                                                                     "to": "2026-10-11"}]}},
                 {"id": "b", "text": "还在的", "schedule": {"mode": "daily"}}]
        # 当天（10-11）范围最后一天不算过期 → 两条都未过期
        view = routine.day_schedule([], memos, self.DAY, today=dt.date(2026, 10, 11))
        self.assertFalse(any(m["expired"] for m in view["reminders"]))
        # 过了 10-11 → 过期项排到末尾（其余按文本排序，与中文码位无关）
        view2 = routine.day_schedule([], memos, self.DAY, today=dt.date(2026, 10, 12))
        self.assertEqual(view2["reminders"][-1]["text"], "过期的")
        self.assertTrue(view2["reminders"][-1]["expired"])
        self.assertEqual(view2["reminders"][0]["text"], "还在的")


class WeekdayScheduleTest(unittest.TestCase):
    """每周几（可多选）。2026-11-01 是周日，11-02 周一，11-07 周六。"""

    def test_weekdays_multiple(self):
        sch = {"mode": "weekdays", "weekdays": [5, 6]}          # 周六、周日
        self.assertTrue(routine.memo_active_on(sch, D("2026-11-01")))   # 周日
        self.assertFalse(routine.memo_active_on(sch, D("2026-11-02")))  # 周一
        self.assertTrue(routine.memo_active_on(sch, D("2026-11-07")))   # 周六

    def test_weekdays_sorted_and_deduped(self):
        sch = routine.normalize_schedule({"mode": "weekdays",
                                          "weekdays": [6, 5, 5, 9, "1", "x"]})
        self.assertEqual(sch["weekdays"], [1, 5, 6])       # 9/x 丢弃、去重、升序

    def test_weekdays_without_selection_degrades_to_none(self):
        self.assertEqual(routine.normalize_schedule({"mode": "weekdays", "weekdays": []})["mode"],
                         "none")

    def test_weekdays_never_expires(self):
        sch = {"mode": "weekdays", "weekdays": [6]}
        self.assertFalse(routine.memo_expired(sch, D("2030-01-01")))

    def test_weekdays_text(self):
        self.assertEqual(routine.schedule_text({"mode": "weekdays", "weekdays": [5, 6]}),
                         "每周六、日")
        self.assertEqual(routine.schedule_text({"mode": "weekdays", "weekdays": [0]}), "每周一")
        self.assertEqual(routine.schedule_text({"mode": "weekdays", "weekdays": [0, 1, 2, 3, 4, 5, 6]}),
                         "每天")     # 七天全选等同每天

    def test_all_modes_keep_other_fields(self):
        """切换模式不改动其他模式的数据（用户来回切不会丢已填内容）。"""
        sch = routine.normalize_schedule({
            "mode": "weekdays", "weekdays": [6],
            "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}],
            "monthdays": [{"from": 8, "to": 9}],
        })
        self.assertEqual(sch["mode"], "weekdays")
        self.assertEqual(len(sch["ranges"]), 1)
        self.assertEqual(len(sch["monthdays"]), 1)
        self.assertEqual(len(sch["weekdays"]), 1)


class ScheduleTextTest(unittest.TestCase):
    def test_texts(self):
        self.assertEqual(routine.schedule_text({"mode": "none"}), "不设定")
        self.assertEqual(routine.schedule_text({"mode": "daily"}), "每天")
        self.assertEqual(
            routine.schedule_text({"mode": "dates",
                                   "ranges": [{"from": "2026-10-08", "to": "2026-10-09"}]}),
            "2026-10-08~2026-10-09")
        self.assertEqual(
            routine.schedule_text({"mode": "dates",
                                   "ranges": [{"from": "2026-10-08", "to": "2026-10-08"}]}),
            "2026-10-08")
        self.assertEqual(
            routine.schedule_text({"mode": "monthdays",
                                   "monthdays": [{"from": 8, "to": 9}, {"from": 11, "to": 12}]}),
            "每月 8–9 号、11–12 号")
