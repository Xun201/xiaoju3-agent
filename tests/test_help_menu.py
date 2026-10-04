# -*- coding: utf-8 -*-
"""help_menu 分类菜单测试（2026-10-04 分类化改版）：分类段齐全、等级
可见性口径（低等级无高等级段）、/sudo 不进菜单（兼容保留口径）、与
docs/COMMANDS_REFERENCE.md 同步锚。全离线纯函数。"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins.help_menu import get_help_menu

# 菜单可见的全量指令（Lv.4 视角；/sudo 为兼容保留指令，刻意不进菜单）
_MENU_COMMANDS = [
    "/help", "/creator", "/clear", "/set_location", "/clear_location",
    "/name", "/register", "/coder_auth", "/lv4_auth", "/lv4_revoke",
    "/approve", "/deny", "/reset_fuse",
    "/todos", "/todos done", "/todos clear", "/todo_from_link",
    "/gen_log", "/soul_export", "/soul_import", "/send_image",
]


class HelpMenuCategoryTests(unittest.TestCase):
    """分类化 /help：七大分类段 + 全指令覆盖 + 等级标注。"""

    def test_lv4_menu_contains_all_categories(self):
        menu = get_help_menu("Lv.4")
        for cat in ["对话直达", "待办", "权限", "记忆", "系统",
                    "主人级", "智能家居"]:
            self.assertIn(cat, menu)
        self.assertIn("多品牌智能家居插件开发中", menu)   # 待实现标注

    def test_lv4_menu_contains_all_commands(self):
        menu = get_help_menu("Lv.4")
        for cmd in _MENU_COMMANDS:
            self.assertIn(cmd, menu, f"菜单缺指令: {cmd}")

    def test_level_tags_present(self):
        menu = get_help_menu("Lv.4")
        for tag in ["【Lv.2】", "【Lv.3】", "【Lv.4】"]:
            self.assertIn(tag, menu)

    def test_upgrade_hints_per_level(self):
        self.assertIn("/register", get_help_menu("Lv.1"))
        self.assertIn("/coder_auth", get_help_menu("Lv.2"))
        self.assertIn("/lv4_auth", get_help_menu("Lv.3"))
        self.assertNotIn("升级指引", get_help_menu("Lv.4"))   # 满级无指引

    def test_menu_no_markdown_symbols(self):
        """纯文本化（2026-10-04 修排版）：菜单零 Markdown 符号——控制台
        （textContent 注入）与 QQ（文本消息）都不渲染 Markdown，** 与
        反引号必然裸露。四个等级全查。"""
        for lv in ("Lv.1", "Lv.2", "Lv.3", "Lv.4"):
            menu = get_help_menu(lv)
            self.assertNotIn("**", menu, f"{lv} 菜单裸露 **")
            self.assertNotIn("`", menu, f"{lv} 菜单裸露反引号")

    def test_todos_clear_confirm_not_in_menu(self):
        """二次确认口径（2026-10-04）：/todos clear 的 confirm 第二步
        不进菜单——直接发带 confirm 的消息会跳过安全提示一步清空；
        /todos clear 本身保留；/lv4_auth confirm 属完成授权必经步骤
        （无码无法授权），保留口径不受影响。"""
        menu = get_help_menu("Lv.4")
        self.assertNotIn("clear confirm", menu)
        self.assertIn("/todos clear", menu)
        self.assertIn("/lv4_auth confirm", menu)


class HelpMenuVisibilityTests(unittest.TestCase):
    """可见性口径（2026-10-02 锚延续 + 分类化保持）：低等级不见高等级段。"""

    def test_lv1_minimal(self):
        menu = get_help_menu("Lv.1")
        self.assertNotIn("/todos", menu)
        self.assertNotIn("/gen_log", menu)
        self.assertNotIn("主人级", menu)

    def test_lv2_todos_but_no_lv3_lv4(self):
        menu = get_help_menu("Lv.2")
        self.assertIn("/todos", menu)
        self.assertIn("/reset_fuse", menu)
        self.assertNotIn("/gen_log", menu)
        self.assertNotIn("/soul_export", menu)
        self.assertNotIn("主人级", menu)          # 既有口径锚（test_main 同款）

    def test_lv3_memory_log_but_no_lv4(self):
        menu = get_help_menu("Lv.3")
        self.assertIn("/gen_log", menu)
        self.assertIn("/soul_export", menu)
        self.assertNotIn("/soul_import", menu)
        self.assertNotIn("/send_image", menu)

    def test_sudo_never_in_menu(self):
        # 2026-10-02 口径：/sudo 兼容保留、不进菜单（仅 COMMANDS_REFERENCE 留档）
        for lv in ("Lv.1", "Lv.2", "Lv.3", "Lv.4"):
            self.assertNotIn("/sudo", get_help_menu(lv))


class CommandsReferenceSyncTests(unittest.TestCase):
    """菜单 ⊆ docs/COMMANDS_REFERENCE.md（查阅文档是超集，同步锚）；
    /sudo 反向锚：参考文档必留档、菜单必不出现。"""

    def _reference(self):
        path = os.path.join(PROJECT_ROOT, "docs", "COMMANDS_REFERENCE.md")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_menu_commands_all_documented(self):
        ref = self._reference()
        for cmd in _MENU_COMMANDS:
            self.assertIn(cmd, ref, f"参考文档缺指令: {cmd}")

    def test_compat_sudo_documented_but_not_in_menu(self):
        ref = self._reference()
        self.assertIn("/sudo", ref)
        self.assertIn("兼容保留", ref)
        self.assertNotIn("/sudo", get_help_menu("Lv.4"))

    def test_home_commands_marked_pending(self):
        ref = self._reference()
        self.assertIn("/home_devices", ref)
        self.assertIn("开发中", ref)


if __name__ == "__main__":
    unittest.main()
