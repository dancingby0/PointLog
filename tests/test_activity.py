"""活动聚合测试：activity.py（AW 事件 → 每日摘要，纯函数、不依赖真实 ActivityWatch）。"""

import datetime as dt
import unittest

import activity


def ev(start: str, minutes: float, **data) -> dict:
    """构造一条 AW 事件（start 用本地朴素时间，如 2026-10-11T09:00:00）。"""
    return {"timestamp": start, "duration": minutes * 60, "data": data}


class AggregateDayTest(unittest.TestCase):
    DAY = dt.date(2026, 10, 11)

    def _agg(self, window, afk, web=None, settings=None):
        return activity.aggregate_day(self.DAY, window, afk, web, settings or {})

    # ---------- 活跃时长口径 ----------

    def test_active_is_window_intersect_not_afk(self):
        out = self._agg(
            [ev("2026-10-11T09:00:00", 120, app="Code", title="main.py")],
            [ev("2026-10-11T09:00:00", 40, status="not-afk"),
             ev("2026-10-11T09:40:00", 80, status="afk")],
        )
        self.assertEqual(out["active_min"], 40.0)
        self.assertEqual(out["apps"][0]["app"], "Code")
        self.assertEqual(out["apps"][0]["min"], 40.0)

    def test_missing_afk_means_zero(self):
        out = self._agg([ev("2026-10-11T09:00:00", 60, app="Code")], [])
        self.assertEqual(out["active_min"], 0.0)
        self.assertEqual(out["apps"], [])

    def test_zero_duration_events_ignored(self):
        out = self._agg(
            [ev("2026-10-11T09:00:00", 0, app="Code"),
             ev("2026-10-11T09:00:00", 30, app="Code")],
            [ev("2026-10-11T09:00:00", 60, status="not-afk")],
        )
        self.assertEqual(out["active_min"], 30.0)

    def test_duplicate_window_events_not_double_counted(self):
        """同一段窗口被 AFK 交集切开后不能重复累加。"""
        out = self._agg(
            [ev("2026-10-11T09:00:00", 60, app="Code"),
             ev("2026-10-11T09:00:00", 60, app="Code")],
            [ev("2026-10-11T09:00:00", 60, status="not-afk")],
        )
        self.assertEqual(out["active_min"], 60.0)

    def test_day_boundary_splits_at_4am(self):
        """凌晨 3:00–5:00 的事件：前一天得 60 分钟，本天得 60 分钟。"""
        window = [ev("2026-10-11T03:00:00", 120, app="Code")]
        afk = [ev("2026-10-11T03:00:00", 120, status="not-afk")]
        today = activity.aggregate_day(self.DAY, window, afk, [], {})
        prev = activity.aggregate_day(dt.date(2026, 10, 10), window, afk, [], {})
        self.assertEqual(today["active_min"], 60.0)
        self.assertEqual(prev["active_min"], 60.0)

    def test_ignored_apps_excluded_from_active(self):
        out = self._agg(
            [ev("2026-10-11T09:00:00", 30, app="Code"),
             ev("2026-10-11T09:30:00", 20, app="ActivityWatch")],
            [ev("2026-10-11T09:00:00", 60, status="not-afk")],
            settings={"ignored_apps": ["activitywatch"]},
        )
        self.assertEqual(out["active_min"], 30.0)
        self.assertEqual(out["excluded_min"], 20.0)

    def test_excluded_title_kept_as_time_but_dropped_as_title(self):
        out = self._agg(
            [ev("2026-10-11T09:00:00", 10, app="Code", title="excluded")],
            [ev("2026-10-11T09:00:00", 10, status="not-afk")],
        )
        self.assertEqual(out["active_min"], 10.0)
        self.assertEqual(out["titles"], [])


    # ---------- 类别与网页 ----------

    def test_same_domain_split_by_title(self):
        """B 站里"考研课程"算学习、"游戏实况"算娱乐（url + title 双条件规则）。"""
        out = self._agg(
            [ev("2026-10-11T09:00:00", 60, app="chrome", title="bilibili")],
            [ev("2026-10-11T09:00:00", 60, status="not-afk")],
            web=[ev("2026-10-11T09:00:00", 40, url="https://www.bilibili.com/video/BV1",
                    title="考研数学 强化课 教程", audible=False),
                 ev("2026-10-11T09:40:00", 20, url="https://www.bilibili.com/video/BV2",
                    title="游戏实况 鬼畜", audible=True)],
        )
        pages = {p["title"]: p["min"] for p in out["pages"]}
        self.assertEqual(pages["考研数学 强化课 教程"], 40.0)
        self.assertEqual(pages["游戏实况 鬼畜"], 20.0)
        # 域名总量合并、类别取占比大的一边
        site = next(s for s in out["sites"] if s["domain"] == "bilibili.com")
        self.assertEqual(site["min"], 60.0)
        self.assertEqual(site["category"], "学习")
        self.assertTrue(site["audible"])

    def test_web_watcher_distinguishes_domains(self):
        out = self._agg(
            [ev("2026-10-11T09:00:00", 60, app="chrome", title="chrome")],
            [ev("2026-10-11T09:00:00", 60, status="not-afk")],
            web=[ev("2026-10-11T09:00:00", 25, url="https://chat.deepseek.com/chat",
                    title="DeepSeek"),
                 ev("2026-10-11T09:25:00", 35, url="https://www.bilibili.com/", title="哔哩哔哩")],
        )
        sites = {s["domain"]: s for s in out["sites"]}
        self.assertEqual(sites["chat.deepseek.com"]["min"], 25.0)
        self.assertEqual(sites["chat.deepseek.com"]["category"], "AI辅助")
        self.assertEqual(sites["bilibili.com"]["min"], 35.0)
        self.assertEqual(sites["bilibili.com"]["category"], "娱乐")

    def test_background_tab_not_counted(self):
        """网页事件落在非活跃区间（挂机/后台）→ 不计入网站时长。"""
        out = self._agg(
            [ev("2026-10-11T09:00:00", 30, app="chrome")],
            [ev("2026-10-11T09:00:00", 30, status="not-afk")],
            web=[ev("2026-10-11T20:00:00", 30, url="https://www.bilibili.com/", title="后台")],
        )
        self.assertEqual(out["sites"], [])

    def test_non_http_urls_ignored(self):
        self.assertEqual(activity.domain_of("chrome://newtab"), "")
        self.assertEqual(activity.domain_of("about:blank"), "")
        self.assertEqual(activity.domain_of("https://www.Example.com/a/b"), "example.com")


class CategorizeTest(unittest.TestCase):
    def test_first_rule_wins(self):
        rules = [{"category": "A", "app": "code"}, {"category": "B", "app": "code"}]
        self.assertEqual(activity.categorize(app="Code", rules=rules), "A")

    def test_and_semantics_across_fields(self):
        rules = [{"category": "学习", "url": "bilibili", "title": "课程"}]
        self.assertEqual(activity.categorize(url="https://bilibili.com/x", title="课程1",
                                            rules=rules), "学习")
        self.assertEqual(activity.categorize(url="https://bilibili.com/x", title="鬼畜",
                                            rules=rules), activity.UNCATEGORIZED)

    def test_invalid_regex_does_not_break(self):
        rules = [{"category": "坏", "app": "([unclosed"}, {"category": "好", "app": "code"}]
        self.assertEqual(activity.categorize(app="Code", rules=rules), "好")

    def test_empty_rule_list_means_no_categories(self):
        """显式给空规则 = 不分类（与"没配置"用默认规则区分开）。"""
        self.assertEqual(activity.categorize(app="Code", rules=[]), activity.UNCATEGORIZED)
        self.assertEqual(activity.categorize(app="Code"), "编程")   # 没给 rules → 默认规则


class PickBucketsTest(unittest.TestCase):
    def test_picks_by_type_and_prefers_host(self):
        infos = [
            {"id": "aw-watcher-window_pcA", "type": "currentwindow"},
            {"id": "aw-watcher-window_pcB", "type": "currentwindow"},
            {"id": "aw-watcher-afk_pcB", "type": "afkstatus"},
            {"id": "aw-watcher-web-chrome", "type": "web.tab.current"},
        ]
        picked = activity.pick_buckets(infos, host="pcB")
        self.assertEqual(picked["window"], "aw-watcher-window_pcB")
        self.assertEqual(picked["afk"], "aw-watcher-afk_pcB")
        self.assertEqual(picked["web"], "aw-watcher-web-chrome")

    def test_missing_web_bucket_is_none(self):
        picked = activity.pick_buckets([{"id": "aw-watcher-window_a", "type": "currentwindow"}])
        self.assertIsNone(picked["web"])
        self.assertIsNone(picked["afk"])


if __name__ == "__main__":
    unittest.main()
