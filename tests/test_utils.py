"""通用工具测试：类别规范化 clean_categories（打卡类别支持多选）。"""

import unittest

from utils import clean_categories


class CleanCategoriesTest(unittest.TestCase):
    """类别恒为字符串列表：兼容老数据的单值写法，并做去空白 / 去重。"""

    def test_none_and_empty_become_empty_list(self):
        self.assertEqual(clean_categories(None), [])
        self.assertEqual(clean_categories(""), [])
        self.assertEqual(clean_categories("   "), [])
        self.assertEqual(clean_categories([]), [])

    def test_legacy_single_string(self):
        """老数据是单值字符串 → 单元素数组。"""
        self.assertEqual(clean_categories("学习"), ["学习"])
        self.assertEqual(clean_categories("  学习  "), ["学习"])

    def test_list_trim_dedupe_keep_order(self):
        self.assertEqual(clean_categories([" 学习 ", "数学", "学习", "", None]),
                         ["学习", "数学"])

    def test_tuple_and_set(self):
        self.assertEqual(clean_categories(("洗澡", "刷牙")), ["洗澡", "刷牙"])
        self.assertEqual(clean_categories({"睡眠"}), ["睡眠"])

    def test_other_types_are_stringified(self):
        self.assertEqual(clean_categories(3), ["3"])
        self.assertEqual(clean_categories([3, "3"]), ["3"])   # 去重按文本算


if __name__ == "__main__":
    unittest.main()
