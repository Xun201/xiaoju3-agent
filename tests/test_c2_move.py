# -*- coding: utf-8 -*-
"""批 C.2 新锚：location 搬家薄化对账（语句形态规范首用）。"""
import io
import re
import unittest


class LocationMoveC2Tests(unittest.TestCase):
    """批 C.2 锚（design_227c_batch_c C.2）：main 零 location 残留 /
    数据域标注更新 / 依赖方向语句形态锚（规范首用）。"""

    def _read(self, name):
        import io
        with io.open(name, encoding="utf-8") as f:
            return f.read()

    def test_main_zero_location_residual(self):
        """main 零 location 本体残留（语句形态锚：def 行不存在）。"""
        src = self._read("main.py")
        self.assertIsNone(re.search(r"^def handle_location_command\(", src, re.M))
        self.assertNotIn("location_cb", src)   # cb 注入退役零残留

    def test_handler_has_body_and_annotation(self):
        """system_handler：location_command 本体在位 + 数据域标注更新为已迁入。"""
        src = self._read("system_handler.py")
        self.assertIsNotNone(re.search(r"^def location_command\(", src, re.M))
        self.assertIn("C.2 已迁入 2026-10-16", src)          # 审计地图更新
        self.assertIn("不写 .env", src)                      # 注释误报修正记档

    def test_dependency_direction_statement_form(self):
        """依赖方向（语句形态规范首用）：零 import main 语句 + brain 惰性
        import 保持在函数体内（方向=分派层调大脑层，合法）。"""
        src = self._read("system_handler.py")
        self.assertIsNone(re.search(r"^\s*import main\b", src, re.M))
        self.assertIn("import brain", src)   # location_command 清除静默期同款

    def test_dashboard_and_brain_refs_aligned(self):
        """调用方/引用全对齐：dashboard 两处+brain docstring 均指新家。"""
        dash = self._read("xiaoju3_dashboard.py")
        self.assertNotIn("main.handle_location_command", dash)
        self.assertEqual(dash.count("system_handler.location_command(user_msg)"), 2)
        brain = self._read("brain.py")
        self.assertNotIn("main.handle_location_command", brain)
        self.assertIn("system_handler.location_command", brain)


if __name__ == "__main__":
    unittest.main()
