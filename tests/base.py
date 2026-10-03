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
        import uuid

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = data.DATA_DIR
        data.DATA_DIR = Path(self._tmp.name)
        self._old_exports_dir = config.EXPORTS_DIR
        # 导出目录也隔离：测试不往真实 exports/ 落文件
        config.EXPORTS_DIR = Path(self._tmp.name) / "exports"
        self._old_profile = config.CURRENT_PROFILE
        # 随机档案名：彻底避免跨测试共享任何档案状态
        self.profile = f"api_{uuid.uuid4().hex[:8]}"
        config.CURRENT_PROFILE = self.profile

    def tearDown(self):
        data.DATA_DIR = self._old_dir
        config.EXPORTS_DIR = self._old_exports_dir
        config.CURRENT_PROFILE = self._old_profile
        try:
            self._tmp.cleanup()
        except Exception:  # noqa: BLE001  (忽略清理期异常，避免掩盖测试结果)
            pass