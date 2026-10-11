# -*- coding: utf-8 -*-
"""#305 幽灵根因修复锚：pytest 收集守卫。

根因（WMI 四次铁证 12:17/12:24/12:31/12:35）：`python -m pytest` rootdir
递归收集扫进 _dev/，E3 实验脚本 popen_*_test.py 匹配默认 `*_test.py` 模式
且模块级裸 Popen launcher-user.bat——import 即真 fire 一棵 NapCat 幽灵树
（父=pytest 进程、跑完即死、无 launcher 日志=此前全部谜团统一解释）。

锚：
- pytest.ini：testpaths 圈定 tests/ + norecursedirs 追加 _dev 等私有/产物目录；
- 五个 E3 实验脚本必须带 __main__ 执行门（防再次被 import 即执行）。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GUARDED_SCRIPTS = [
    "_dev/popen_cwd_form_test.py",
    "_dev/popen_file_redirect_test.py",
    "_dev/popen_live_parent_test.py",
    "_dev/popen_no_window_test.py",
    "_dev/popen_replicate_test.py",
]


class PytestCollectionGuardTests(unittest.TestCase):
    """收集范围圈定 + 实验脚本执行门。"""

    def test_pytest_ini_scopes_collection(self):
        ini = os.path.join(ROOT, "pytest.ini")
        self.assertTrue(os.path.isfile(ini), "pytest.ini 缺失")
        with open(ini, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("testpaths = tests", content)
        self.assertIn("_dev", content)   # norecursedirs 双保险

    def test_dev_experiment_scripts_guarded(self):
        """E3 实验脚本全部带 __main__ 门——模块级裸 Popen 不得复活。"""
        for rel in GUARDED_SCRIPTS:
            path = os.path.join(ROOT, rel)
            self.assertTrue(os.path.isfile(path), rel + " 缺失")
            with open(path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn('__name__ == "__main__"', content,
                          rel + " 缺执行门（import 即 fire 风险回归）")
            unguarded = [l for l in content.splitlines()
                         if l.lstrip().startswith("p = subprocess.Popen")
                         and not l.startswith((" ", "\t"))]
            self.assertFalse(unguarded,
                             rel + " 仍有模块级裸 Popen: " + repr(unguarded))


if __name__ == "__main__":
    unittest.main()
