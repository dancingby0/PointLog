"""测试公共基类。

- DataTestCase：数据层测试用（临时数据目录隔离，不动真实 data/）
- ApiTestCase：API 测试用（临时数据目录 + 独立档案 + Flask test client）
"""

import tempfile
import unittest
from pathlib import Path

import app as app_module
import config
import data


class DataTestCase(unittest.TestCase):
    """数据层基类：把 data.DATA_DIR 指到临时目录，测完还原。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = data.DATA_DIR
        data.DATA_DIR = Path(self._tmp.name)
        self.profile = "tmp_test"

    def tearDown(self):
        data.DATA_DIR = self._old_dir
        self._tmp.cleanup()


class ApiTestCase(unittest.TestCase):
    """API 基类：临时数据目录 + 独立档案隔离 + Flask test client。"""

    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = data.DATA_DIR
        data.DATA_DIR = Path(self._tmp.name)
        self._old_profile = config.CURRENT_PROFILE
        self.profile = "api_test"
        config.CURRENT_PROFILE = self.profile

    def tearDown(self):
        data.DATA_DIR = self._old_dir
        config.CURRENT_PROFILE = self._old_profile
        self._tmp.cleanup()