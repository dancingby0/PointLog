"""专注会话纯函数测试（focus.py）：计时状态机、按天切分、上传记录构造、统计。"""

import datetime as dt
import unittest

import focus


def T(text: str) -> dt.datetime:
    """本地时区的固定时刻（测试不依赖真实时钟）。"""
    return dt.datetime.fromisoformat(text).astimezone()


class StateMachineTest(unittest.TestCase):
    def test_start_creates_running_session(self):
        sess = focus.start_session("学数学", points=2, now=T("2026-11-02T09:00:00"))
        self.assertEqual(sess["state"], "running")
        self.assertEqual(sess["label"], "学数学")
        self.assertTrue(focus.open_segment(sess))
        self.assertEqual(focus.total_sec(sess, T("2026-11-02T09:30:00")), 1800)

    def test_pause_freezes_duration(self):
        sess = focus.start_session("x", now=T("2026-11-02T09:00:00"))
        paused = focus.pause(sess, T("2026-11-02T09:10:00"))
        self.assertEqual(paused["state"], "paused")
        self.assertFalse(focus.open_segment(paused))
        self.assertEqual(focus.total_sec(paused, T("2026-11-02T12:00:00")), 600)

    def test_resume_adds_new_segment(self):
        sess = focus.start_session("x", now=T("2026-11-02T09:00:00"))
        paused = focus.pause(sess, T("2026-11-02T09:10:00"))
        resumed = focus.resume(paused, T("2026-11-02T09:20:00"))
        self.assertEqual(resumed["state"], "running")
        self.assertEqual(len(resumed["segments"]), 2)
        self.assertEqual(focus.total_sec(resumed, T("2026-11-02T09:30:00")), 1200)  # 暂停不算

    def test_stop_is_idempotent(self):
        sess = focus.start_session("x", now=T("2026-11-02T09:00:00"))
        stopped = focus.stop(sess, T("2026-11-02T09:05:00"))
        again = focus.stop(stopped, T("2026-11-02T10:00:00"))
        self.assertEqual(again["state"], "stopped")
        self.assertEqual(focus.total_sec(again, T("2026-11-02T11:00:00")), 300)

    def test_pause_on_stopped_is_noop(self):
        stopped = focus.stop(focus.start_session(now=T("2026-11-02T09:00:00")),
                             T("2026-11-02T09:05:00"))
        self.assertEqual(focus.pause(stopped, T("2026-11-02T10:00:00"))["state"], "stopped")

    def test_resume_on_running_is_noop(self):
        sess = focus.start_session(now=T("2026-11-02T09:00:00"))
        self.assertEqual(len(focus.resume(sess, T("2026-11-02T09:01:00"))["segments"]), 1)

    def test_bad_data_returns_none(self):
        for raw in (None, {}, {"segments": []}, "x", {"segments": [{"start": "坏的"}]}):
            self.assertIsNone(focus.normalize_session(raw), msg=str(raw))

    def test_zero_length_segment_is_kept(self):
        """同一秒内开始又暂停（end == start）不能被当成脏数据丢掉，否则整条会话消失。"""
        now = T("2026-11-02T09:00:00")
        sess = focus.start_session("x", now=now)
        paused = focus.pause(sess, now)              # 同一秒
        norm = focus.normalize_session(paused)
        self.assertIsNotNone(norm)
        self.assertEqual(norm["state"], "paused")
        self.assertEqual(len(norm["segments"]), 1)

    def test_reversed_segment_is_dropped(self):
        raw = {"state": "stopped",
               "segments": [{"start": "2026-11-02T10:00:00", "end": "2026-11-02T09:00:00"}]}
        self.assertIsNone(focus.normalize_session(raw))

    def test_segment_cap_limits_runaway_timer(self):
        """忘关计时器：单段最多算 24 小时，总量封顶 12 小时。"""
        sess = focus.start_session(now=T("2026-11-01T09:00:00"))
        self.assertEqual(focus.total_sec(sess, T("2026-11-05T09:00:00")), focus.MAX_TOTAL_SEC)


class SplitByDayTest(unittest.TestCase):
    def test_split_at_4am_boundary(self):
        """03:00–05:00 的会话：前一天 60 分钟、当天 60 分钟。"""
        sess = focus.stop(focus.start_session(now=T("2026-11-02T03:00:00")),
                          T("2026-11-02T05:00:00"))
        parts = dict(focus.split_by_day(sess, T("2026-11-02T05:00:00")))
        self.assertEqual(parts[dt.date(2026, 11, 1)], 3600)
        self.assertEqual(parts[dt.date(2026, 11, 2)], 3600)

    def test_same_day_session(self):
        sess = focus.stop(focus.start_session(now=T("2026-11-02T09:00:00")),
                          T("2026-11-02T10:30:00"))
        parts = focus.split_by_day(sess, T("2026-11-02T10:30:00"))
        self.assertEqual(parts, [(dt.date(2026, 11, 2), 5400)])



class BuildEntryTest(unittest.TestCase):
    def test_builds_standard_entry(self):
        sess = focus.stop(focus.start_session("学数学", now=T("2026-11-02T09:00:00")),
                          T("2026-11-02T10:23:00"))
        entry = focus.build_entry(sess, T("2026-11-02T10:23:00"), points=2)
        self.assertEqual(entry["content"], "专注 1h23m · 学数学")
        self.assertEqual(entry["points"], 2)
        self.assertEqual(entry["category"], ["学数学"])
        self.assertEqual(entry["start_ts"], T("2026-11-02T09:00:00").isoformat(timespec="seconds"))
        self.assertEqual(entry["end_ts"], T("2026-11-02T10:23:00").isoformat(timespec="seconds"))

    def test_short_session_returns_none(self):
        sess = focus.stop(focus.start_session(now=T("2026-11-02T09:00:00")),
                          T("2026-11-02T09:00:30"))
        self.assertIsNone(focus.build_entry(sess, T("2026-11-02T09:00:30")))

    def test_label_override_and_empty_category(self):
        sess = focus.stop(focus.start_session(now=T("2026-11-02T09:00:00")),
                          T("2026-11-02T10:00:00"))
        entry = focus.build_entry(sess, T("2026-11-02T10:00:00"), label="画画")
        self.assertEqual(entry["content"], "专注 1h00m · 画画")
        self.assertEqual(entry["category"], ["画画"])

        entry2 = focus.build_entry(sess, T("2026-11-02T10:00:00"))
        self.assertEqual(entry2["category"], [])

    def test_duration_excludes_paused_time(self):
        sess = focus.start_session(now=T("2026-11-02T09:00:00"))
        sess = focus.pause(sess, T("2026-11-02T09:10:00"))
        sess = focus.resume(sess, T("2026-11-02T09:40:00"))
        sess = focus.stop(sess, T("2026-11-02T09:50:00"))
        entry = focus.build_entry(sess, T("2026-11-02T09:50:00"))
        self.assertEqual(entry["content"], "专注 20m")


class AggregateTest(unittest.TestCase):
    TODAY = dt.date(2026, 11, 2)

    def test_today_and_total(self):
        s1 = focus.stop(focus.start_session("学习日语", now=T("2026-11-02T09:00:00")),
                        T("2026-11-02T10:00:00"))     # 今日 60m
        s2 = focus.stop(focus.start_session("画画", now=T("2026-11-01T20:00:00")),
                        T("2026-11-01T20:30:00"))     # 昨天 30m
        out = focus.aggregate([s1, s2], self.TODAY, T("2026-11-02T10:00:00"))
        self.assertEqual(out["today_text"], "1h00m")
        self.assertEqual(out["total_text"], "1h30m")
        self.assertEqual(out["days"], 2)
        self.assertEqual(out["sessions"], 2)
        labels = {row["label"]: row["text"] for row in out["by_label"]}
        self.assertEqual(labels["学习日语"], "1h00m")
        self.assertEqual(labels["画画"], "30m")

    def test_running_session_counts_up_to_now(self):
        s = focus.start_session("科研工作", now=T("2026-11-02T09:00:00"))
        out = focus.aggregate([s], self.TODAY, T("2026-11-02T09:45:00"))
        self.assertEqual(out["today_text"], "45m")
        self.assertEqual(out["running"]["label"], "科研工作")
        self.assertEqual(out["running"]["elapsed_text"], "45m")

    def test_empty(self):
        out = focus.aggregate([], self.TODAY, T("2026-11-02T10:00:00"))
        self.assertEqual(out["today_text"], "0m")
        self.assertEqual(out["days"], 0)
        self.assertIsNone(out["running"])

    def test_bad_rows_ignored(self):
        out = focus.aggregate([{}, None, "x"], self.TODAY, T("2026-11-02T10:00:00"))
        self.assertEqual(out["sessions"], 0)


class FormatTest(unittest.TestCase):
    def test_fmt_duration(self):
        self.assertEqual(focus.fmt_duration(0), "0m")
        self.assertEqual(focus.fmt_duration(59), "1m")
        self.assertEqual(focus.fmt_duration(3600), "1h00m")
        self.assertEqual(focus.fmt_duration(5400), "1h30m")
        self.assertEqual(focus.fmt_duration(600), "10m")


if __name__ == "__main__":
    unittest.main()
