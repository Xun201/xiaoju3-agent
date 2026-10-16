# -*- coding: utf-8 -*-
"""批 C.3 新锚：todo 搬家薄化对账（语句形态规范，C.2 同款）。"""
import io
import re
import unittest


class TodoMoveC3Tests(unittest.TestCase):
    """批 C.3 锚（design_227c_batch_c3_todo.md）：main 零 todo 残留 /
    todo_handler 本体与数据域标注 / 依赖方向与工具口径（借
    permission_handler 版 _arg_after）/ 调用方对齐 / SHARE_PREFIX 单一来源。"""

    def _read(self, name):
        with io.open(name, encoding="utf-8") as f:
            return f.read()

    def test_main_zero_todo_residual(self):
        """main 零 todo 本体残留（语句形态锚：def 行不存在）+ cb 注入退役。"""
        src = self._read("main.py")
        self.assertIsNone(re.search(r"^def handle_todo_command\(", src, re.M))
        self.assertIsNone(re.search(r"^def _notify_todo_done\(", src, re.M))
        self.assertNotIn("todo_cb", src)   # cb 注入退役零残留

    def test_handler_has_body_and_annotation(self):
        """todo_handler：两本体在位 + 数据域标注（灵魂核 ext）在模块头。"""
        src = self._read("todo_handler.py")
        self.assertIsNotNone(re.search(r"^def handle_todo_command\(", src, re.M))
        self.assertIsNotNone(re.search(r"^def _notify_todo_done\(", src, re.M))
        self.assertIn("灵魂核", src)
        self.assertIn("ext", src)

    def test_dependency_direction_and_tool_source(self):
        """依赖方向（零 import main 语句）+ 工具口径（_arg_after 借
        permission_handler，防第三副本回潮——行首语句形态锚）。"""
        src = self._read("todo_handler.py")
        self.assertIsNone(re.search(r"^\s*import main\b", src, re.M))
        self.assertIsNone(re.search(r"^\s*from main import\b", src, re.M))
        self.assertIsNotNone(
            re.search(r"^from permission_handler import _arg_after", src, re.M))
        self.assertIsNone(re.search(r"^def _arg_after\(", src, re.M))

    def test_callers_all_aligned(self):
        """调用方全对齐：dashboard 两处直调新家 / content_handler 内聚直调 /
        main 预分流改指。"""
        dash = self._read("xiaoju3_dashboard.py")
        self.assertNotIn("main.handle_todo_command", dash)
        self.assertEqual(
            dash.count("todo_handler.handle_todo_command(user_msg"), 2)
        ch = self._read("content_handler.py")
        self.assertIn("todo_handler.handle_todo_command", ch)
        self.assertNotIn("todo_cb", ch)
        mn = self._read("main.py")
        self.assertIn("todo_handler.handle_todo_command(todo_cmd", mn)

    def test_share_prefix_single_source(self):
        """SHARE_PREFIX 单一来源：main 定义已迁走，todo_handler 持有。"""
        mn = self._read("main.py")
        th = self._read("todo_handler.py")
        self.assertIsNone(re.search(r"^SHARE_PREFIX = ", mn, re.M))
        self.assertIsNotNone(re.search(r'^SHARE_PREFIX = "https://chat\.deepseek\.com/share/"',
                                       th, re.M))

    def test_import_surface_clean(self):
        """main 零 todo_extractor/看门狗伴生残留；todo_handler 持有。"""
        mn = self._read("main.py")
        self.assertNotIn("plugins.todo_extractor", mn)
        self.assertNotIn("_extract_work_thread", mn)
        self.assertNotIn("TODO_EXTRACT_WATCHDOG_S", mn)
        th = self._read("todo_handler.py")
        self.assertIn("plugins.todo_extractor", th)
        self.assertIn("_extract_work_thread", th)
        self.assertIn("TODO_EXTRACT_WATCHDOG_S", th)


if __name__ == "__main__":
    unittest.main()
