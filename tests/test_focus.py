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


class InstanceLockTest(unittest.TestCase):
    """单实例锁：第二个实例应拿不到锁（避免叠出多个悬浮窗）。"""

    def test_second_acquire_fails(self):
        import socket

        from focus_timer import acquire_instance_lock, SINGLE_INSTANCE_PORT
        first = acquire_instance_lock()
        if first is None:
            self.skipTest(f"端口 {SINGLE_INSTANCE_PORT} 已被占用（可能已有计时器在跑）")
        try:
            self.assertIsNone(acquire_instance_lock())      # 第二个拿不到
        finally:
            first.close()
        # 释放后又能拿到
        again = acquire_instance_lock()
        self.assertIsNotNone(again)
        again.close()
        with socket.socket() as probe:                      # 确认端口已释放
            probe.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))


class TimerWindowTest(unittest.TestCase):
    """悬浮窗三种形态能否真正构造与切换（回归：StringVar 必须先有 root）。"""

    def _make(self, view="ball"):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("无 tkinter")
        try:
            from focus_timer import FocusTimer
            return FocusTimer("http://127.0.0.1:9", points=1, labels=["画画"],
                              wait_sec=None, view=view), tk
        except tk.TclError as exc:
            self.skipTest(f"无图形环境：{exc}")

    def test_window_builds_in_ball_view(self):
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            self.assertEqual(timer.view.get(), "ball")
            self.assertEqual(timer.time_var.get(), "00:00:00")
            self.assertEqual(timer.label_var.get(), "未选标签")
            self.assertEqual(str(timer.root.attributes("-topmost")), "1")
        finally:
            timer.root.destroy()

    def test_switch_ball_bar_full(self):
        timer, _ = self._make()
        try:
            timer._apply_view("bar")
            self.assertEqual(timer.view.get(), "bar")
            timer._apply_view("full")
            self.assertEqual(timer.view.get(), "full")
            timer._apply_view("ball")
            self.assertEqual(timer.view.get(), "ball")
        finally:
            timer.root.destroy()

    def test_escape_steps_back_one_level(self):
        timer, _ = self._make(view="full")
        try:
            timer._on_escape()
            self.assertEqual(timer.view.get(), "bar")
            timer._on_escape()
            self.assertEqual(timer.view.get(), "ball")
        finally:
            timer.root.destroy()

    def test_ball_click_expands_to_bar(self):
        timer, _ = self._make(view="ball")
        try:
            timer._on_ball_click()
            self.assertEqual(timer.view.get(), "bar")
        finally:
            timer.root.destroy()

    def test_empty_label_pool_shows_hint(self):
        timer, _ = self._make(view="full")
        try:
            timer.labels = []
            timer._render_chips()
            timer.root.update_idletasks()
            texts = [w.cget("text") for w in timer.tags_box.winfo_children()]
            self.assertEqual(len(texts), 1)
            self.assertIn("类别池是空的", texts[0])
        finally:
            timer.root.destroy()

    def test_drag_does_not_trigger_switch(self):
        """按住拖动超过 3px 就标记为"移动过"，松手不切换形态。"""
        timer, _ = self._make(view="ball")
        try:
            class Ev:
                x_root = 100
                y_root = 100
            timer._press(Ev())
            Ev.x_root, Ev.y_root = 140, 140
            timer._on_drag(Ev())
            self.assertTrue(timer._moved)
            switched = []
            timer._release(lambda: switched.append(True))
            self.assertEqual(switched, [])          # 没有触发点击
            self.assertEqual(timer.view.get(), "ball")
        finally:
            timer.root.destroy()


class WindowPlacementTest(unittest.TestCase):
    """定位与贴边：默认右下、贴边吸附、展开时朝反方向长（右下 → 向左上）。"""

    def _make(self, view="ball", auto_sync_min=0):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("无 tkinter")
        try:
            from focus_timer import FocusTimer
            return FocusTimer("http://127.0.0.1:9", points=1, labels=[], wait_sec=None,
                              view=view, auto_sync_min=auto_sync_min), tk
        except tk.TclError as exc:
            self.skipTest(f"无图形环境：{exc}")

    def test_default_position_is_bottom_right(self):
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            sw, sh = timer._screen()
            x, y = timer.root.winfo_x(), timer.root.winfo_y()
            self.assertGreater(x, sw // 2, "应位于屏幕右半边")
            self.assertGreater(y, sh // 2, "应位于屏幕下半边")
            self.assertEqual(timer._anchor, ("right", "bottom"))
        finally:
            timer.root.destroy()

    def test_expanding_keeps_right_edge(self):
        """贴右下时展开：右边缘保持不动（相当于向左展开）。"""
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            right_before = timer.root.winfo_x() + timer.root.winfo_width()
            bottom_before = timer.root.winfo_y() + timer.root.winfo_height()

            timer._apply_view("bar")
            timer.root.update_idletasks()
            self.assertEqual(timer.root.winfo_x() + timer.root.winfo_width(), right_before)
            self.assertEqual(timer.root.winfo_y() + timer.root.winfo_height(), bottom_before)

            timer._apply_view("full")
            timer.root.update_idletasks()
            self.assertEqual(timer.root.winfo_x() + timer.root.winfo_width(), right_before)
        finally:
            timer.root.destroy()

    def test_snap_to_right_edge_records_anchor(self):
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            sw, sh = timer._screen()
            w, h = timer.root.winfo_width(), timer.root.winfo_height()
            # 摆到离右边缘 5px 处 → 松手吸附到 0 距离
            timer.root.geometry(f"{w}x{h}+{sw - w - 5}+{sh // 2}")
            timer.root.update_idletasks()
            timer._snap_to_edges()
            timer.root.update_idletasks()
            self.assertEqual(timer.root.winfo_x() + timer.root.winfo_width(), sw)
            self.assertEqual(timer._anchor[0], "right")
        finally:
            timer.root.destroy()

    def test_snap_to_left_edge_switches_anchor(self):
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            sw, sh = timer._screen()
            w, h = timer.root.winfo_width(), timer.root.winfo_height()
            timer.root.geometry(f"{w}x{h}+3+{sh // 3}")
            timer.root.update_idletasks()
            timer._snap_to_edges()
            timer.root.update_idletasks()
            self.assertEqual(timer.root.winfo_x(), 0)
            self.assertEqual(timer._anchor[0], "left")
        finally:
            timer.root.destroy()

    def test_left_anchor_expands_rightward(self):
        timer, _ = self._make()
        try:
            timer.root.update_idletasks()
            sw, sh = timer._screen()
            w, h = timer.root.winfo_width(), timer.root.winfo_height()
            timer.root.geometry(f"{w}x{h}+0+{sh // 3}")
            timer.root.update_idletasks()
            timer._snap_to_edges()                 # → 贴左
            left_before = timer.root.winfo_x()
            timer._apply_view("bar")
            timer.root.update_idletasks()
            self.assertEqual(timer.root.winfo_x(), left_before)   # 左边缘不动 → 向右长
        finally:
            timer.root.destroy()


class AutoSyncUiTest(unittest.TestCase):
    """自动同步：间隔可配、默认开启、结束后自动上传开关默认打开。"""

    def _make(self, auto_sync_min=15):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("无 tkinter")
        try:
            from focus_timer import FocusTimer
            return FocusTimer("http://127.0.0.1:9", points=1, labels=[], wait_sec=None,
                              auto_sync_min=auto_sync_min), tk
        except tk.TclError as exc:
            self.skipTest(f"无图形环境：{exc}")

    def test_auto_sync_interval_is_configured(self):
        timer, _ = self._make(15)
        try:
            self.assertEqual(timer.auto_sync_min, 15)
            self.assertGreater(timer._next_sync, 0)
        finally:
            timer.root.destroy()

    def test_zero_disables_auto_sync(self):
        timer, _ = self._make(0)
        try:
            self.assertEqual(timer.auto_sync_min, 0)
            timer._maybe_auto_sync()               # 关掉时应该什么都不做
            self.assertEqual(timer._next_sync, 0)
        finally:
            timer.root.destroy()

    def test_auto_upload_checkbox_defaults_on(self):
        timer, _ = self._make()
        try:
            self.assertTrue(timer.auto_upload.get())
        finally:
            timer.root.destroy()

    def test_maybe_auto_sync_fires_when_due(self):
        timer, _ = self._make(1)
        calls = []
        timer._auto_sync = lambda quiet=False: calls.append(quiet) or 0
        try:
            timer._next_sync = 0                   # 立即到期
            timer._maybe_auto_sync()
            self.assertEqual(calls, [False])
            self.assertGreater(timer._next_sync, 0)   # 触发后重排下一次
        finally:
            timer.root.destroy()


class FormatHelperTest(unittest.TestCase):
    def test_fmt_clock(self):
        from focus_timer import fmt_clock
        self.assertEqual(fmt_clock(0), "00:00:00")
        self.assertEqual(fmt_clock(3725), "01:02:05")

    def test_fmt_short(self):
        from focus_timer import fmt_short
        self.assertEqual(fmt_short(0), "0m")
        self.assertEqual(fmt_short(5400), "1h30m")
        self.assertEqual(fmt_short(600), "10m")



if __name__ == "__main__":
    unittest.main()
