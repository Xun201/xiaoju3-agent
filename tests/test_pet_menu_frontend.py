# -*- coding: utf-8 -*-
"""#264 B2d 第①批 · 桌宠右键菜单前端锚（源码级静态断言）。

覆盖：
- desktop-pet.js：img.contextmenu 阻止默认 + 自绘菜单六项（缩小/设置/
  切换主题/关于/—/退出）+ 视口钳制 + 桥未就绪 warn 兜底；
- desktop-pet.js：pointerdown 左键门（右键/中键不进拖拽——右键留给菜单）；
- console.js：__xiaoju3Console 桥五方法 + toggleTheme 抽取同源（按钮与
  菜单共用一实现）；
- console.js：关于卡极简内容（版本回退/Apache 2.0）+ 退出 stub 批次标记。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class PetMenuJsTests(unittest.TestCase):
    """desktop-pet.js 菜单锚。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("desktop-pet.js")

    def test_contextmenu_menu_six_entries(self):
        """img.contextmenu 阻止默认 + 菜单六项齐备（含分隔线）+ 视口钳制。"""
        self.assertIn("img.addEventListener('contextmenu'", self.js)
        self.assertIn("e.preventDefault()", self.js)
        for label in ("缩小", "设置", "切换主题", "关于", "退出"):
            self.assertIn("label: '%s'" % label, self.js)
        self.assertIn("{ sep: true }", self.js)
        self.assertIn("window.innerWidth - rect.width - 4", self.js)   # 视口钳制
        self.assertIn("window.__xiaoju3Console", self.js)
        self.assertIn("console.warn('[pet-menu] 桥未就绪", self.js)    # 桥兜底

    def test_pointerdown_left_button_gate(self):
        """右键/中键不进入拖拽（e.button !== 0 早退）——右键留给菜单，
        且按压音效/形变不被右键触发。"""
        self.assertIn("if (e.button !== 0) return;", self.js)
        # 门必须在 pointerdown 处理器内、preventDefault 之前
        idx_handler = self.js.index("img.addEventListener('pointerdown'")
        idx_gate = self.js.index("if (e.button !== 0) return;")
        idx_prevent = self.js.index("e.preventDefault();", idx_handler)
        self.assertLess(idx_gate, idx_prevent)
        self.assertGreater(idx_gate, idx_handler)


class ConsoleBridgeTests(unittest.TestCase):
    """console.js 桥与关于卡锚。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_bridge_five_methods_and_toggle_theme_shared(self):
        """__xiaoju3Console 桥五方法齐备；themeBtn 与菜单共用 toggleTheme
        （handler 不再内联主题逻辑——单一实现源）。"""
        self.assertIn("window.__xiaoju3Console = {", self.js)
        for method in ("switchTab: switchChatTab", "setPetMinimized: setPetMinimized",
                       "toggleTheme: toggleTheme", "openAbout: openAbout",
                       "quitApp: quitApp"):
            self.assertIn(method, self.js)
        self.assertIn("themeBtn.addEventListener('click', toggleTheme)", self.js)
        body_start = self.js.index("themeBtn.addEventListener")
        self.assertNotIn("getStoredTheme() === 'orange'",
                         self.js[body_start:body_start + 200])   # handler 无内联逻辑

    def test_about_minimal_and_quit_stub(self):
        """关于卡=极简拍板（版本回退+一句话+Apache 2.0）；退出=第①批 stub
        （真弹窗随第③批，stub 内注明）。"""
        about = self.js[self.js.index("function openAbout()"):
                        self.js.index("function quitApp()")]
        self.assertIn("about-overlay", about)
        self.assertIn("Apache License 2.0", about)
        self.assertIn("v1.0.4", about)          # header-version 缺失时的回退
        stub = self.js[self.js.index("function quitApp()"):]
        self.assertIn("第③批", stub)
        self.assertIn("showToast", stub)


if __name__ == "__main__":
    unittest.main()
