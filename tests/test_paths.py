# -*- coding: utf-8 -*-
"""paths.py 双根判定的离线测试（步 1a 基建）。

覆盖三通道：
1. 非 frozen 真值：两根同值、锚定模块所在目录（现网行为零变化的根基）；
2. 纯函数 _resolve：非 frozen 忽略 meipass/executable；frozen 两根分岔、
   DATA_ROOT 取 exe 所在目录；
3. mock 集成：patch sys.frozen / sys._MEIPASS / sys.executable 后 reload，
   模块常量按 frozen 口径取值（tearDown reload 恢复，零跨用例污染）。

全程离线、不触网络/子进程/真实文件系统写入。
"""
import importlib
import os
import sys
import unittest
from unittest import mock

import paths

_MODULE_DIR = os.path.dirname(os.path.abspath(paths.__file__))


class PathsNonFrozenTests(unittest.TestCase):
    """非 frozen（现网 python 直跑）形态。"""

    def test_frozen_flag_false(self):
        """非 frozen 环境 FROZEN 恒为 False。"""
        self.assertFalse(paths.FROZEN)

    def test_two_roots_identical(self):
        """非 frozen 下两根同值——现网行为零变化的根基。"""
        self.assertEqual(paths.RESOURCE_ROOT, paths.DATA_ROOT)

    def test_roots_anchor_to_module_dir(self):
        """两根锚定 paths.py 所在目录（项目根）。"""
        self.assertEqual(paths.RESOURCE_ROOT, _MODULE_DIR)
        self.assertEqual(paths.DATA_ROOT, _MODULE_DIR)

    def test_resolve_non_frozen_ignores_meipass_and_executable(self):
        """纯函数：非 frozen 分支忽略 meipass / executable，恒取模块目录。"""
        r, d = paths._resolve(False, r"C:\_MEIignore", r"C:\Elsewhere\xiaoju3.exe")
        self.assertEqual((r, d), (_MODULE_DIR, _MODULE_DIR))


class PathsFrozenTests(unittest.TestCase):
    """frozen（PyInstaller onefile）形态：mock sys 属性后 reload。"""

    MEIPASS = r"C:\_MEI12345"
    EXE = r"C:\Apps\xiaoju3\xiaoju3.exe"

    def _reload_frozen(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", self.MEIPASS, create=True), \
             mock.patch.object(sys, "executable", self.EXE):
            return importlib.reload(paths)

    def tearDown(self):
        # patch 上下文已退出，sys 恢复真值；reload 把模块恢复为非 frozen 口径
        importlib.reload(paths)

    def test_frozen_flag_true(self):
        """mock sys.frozen 后 FROZEN 为 True。"""
        self.assertTrue(self._reload_frozen().FROZEN)

    def test_resource_root_is_meipass(self):
        """frozen 下资源根 = sys._MEIPASS（只读解压目录）。"""
        m = self._reload_frozen()
        self.assertEqual(m.RESOURCE_ROOT, self.MEIPASS)

    def test_data_root_is_exe_dir(self):
        """frozen 下数据根 = exe 所在目录（可写持久）。"""
        m = self._reload_frozen()
        expected = os.path.dirname(os.path.abspath(self.EXE))
        self.assertEqual(m.DATA_ROOT, expected)

    def test_roots_diverge_in_frozen(self):
        """frozen 下两根分岔（_MEIPASS ≠ exe 目录）——双根存在的意义。"""
        m = self._reload_frozen()
        self.assertNotEqual(m.RESOURCE_ROOT, m.DATA_ROOT)


if __name__ == "__main__":
    unittest.main()
