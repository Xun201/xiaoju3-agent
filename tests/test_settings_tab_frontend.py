# -*- coding: utf-8 -*-
"""#264 B2a 设置 tab 前端锚（源码级静态断言，仓库前端锚惯例）。

覆盖：
- index.html：tab-settings 按钮 + settings-pane（缺省 hidden）+ 保存/刷新
  按钮 + 渲染挂载点，且 pane 位于记录区与输入区之间（与终端页同构）；
- console.js：switchChatTab 注册表化（CHAT_TABS 映射 + 条目声明，非
  if/else 链——为 B2b 密钥页/B2c 开发者暗开关预留扩展位）；
- loadSettings：GET /api/settings + 竞态守卫 + 交渲染函数；
- saveSettings：POST {updates} + 403 → showToast 权限不足；
- renderSettingsItems：遍历 items 渲染、零键名硬编码（新增键零前端改动）。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _fn_body(src, name):
    """按花括号配对提取函数源码（function name(...) { ... }）。"""
    marker = "function " + name + "("
    i = src.index(marker)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError("function %s: 未找到收尾花括号" % name)


class SettingsTabHtmlTests(unittest.TestCase):
    """index.html 结构锚。"""

    def test_tab_button_and_pane_present(self):
        html = _read("index.html")
        self.assertIn(
            '<button id="tab-settings" class="chat-tab" type="button">设置</button>',
            html)
        self.assertIn('<div class="settings-pane" id="settings-pane" hidden>', html)
        self.assertIn('id="settings-save"', html)
        self.assertIn('id="settings-refresh"', html)
        self.assertIn('id="settings-list"', html)
        # pane 位置：记录区（终端）之后、输入区之前——与终端页同构平级
        self.assertLess(html.index('id="settings-pane"'),
                        html.index('class="chat-input-area"'))
        self.assertGreater(html.index('id="settings-pane"'),
                           html.index('id="terminal-history"'))


    def test_gear_entry_replaces_minimize(self):
        """#264 B2d②：右上角 ⌄ → ⚙️ 齿轮=设置入口（title=设置）；旧
        console-minimize 在前端双文件禁绝（缩球入口已迁桌宠右键菜单）。"""
        html = _read("index.html")
        self.assertIn(
            '<button id="console-settings-entry" class="header-btn" title="设置">⚙️</button>',
            html)
        self.assertNotIn("console-minimize", html)
        self.assertNotIn("console-minimize", _read("console.js"))


class SettingsTabJsTests(unittest.TestCase):
    """console.js 行为契约锚（函数体级）。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_switch_tab_is_registry(self):
        """切换=注册表：CHAT_TABS 映射含 settings 条目；switchChatTab 消费
        注册表（CHAT_TABS[tab]），旧 if/else 链（isTerminal 分支）不残留——
        B2b/B2c 新 tab 只加条目不改函数。"""
        self.assertIn("const CHAT_TABS = {", self.js)
        self.assertIn("settings: {", self.js)
        body = _fn_body(self.js, "switchChatTab")
        self.assertIn("CHAT_TABS[tab]", body)
        self.assertNotIn("isTerminal", body)

    def test_load_settings_get_contract(self):
        """loadSettings：GET /api/settings（B1 契约）+ 竞态守卫 + 交渲染。"""
        body = _fn_body(self.js, "loadSettings")
        self.assertIn("fetch('/api/settings')", body)
        self.assertIn("settingsFetchSeq", body)
        self.assertIn("renderSettingsItems(body)", body)

    def test_save_settings_post_contract(self):
        """saveSettings：POST /api/settings，body 携带 updates（增量改动项）。"""
        body = _fn_body(self.js, "saveSettings")
        self.assertIn("method: 'POST'", body)
        self.assertIn("'/api/settings'", body)
        self.assertIn("updates", body)

    def test_save_403_shows_toast(self):
        """403 响应 → showToast 提示；文案分流在 settingsDenyText（含
        权限不足/所需等级/TOTP 原因）。"""
        body = _fn_body(self.js, "saveSettings")
        self.assertIn("403", body)
        self.assertIn("showToast", body)
        self.assertIn("settingsDenyText(body)", body)
        deny = _fn_body(self.js, "settingsDenyText")
        self.assertIn("权限不足", deny)
        self.assertIn("level_insufficient", deny)

    def test_gear_click_binds_settings_and_pet_menu_regression(self):
        """#264 B2d② 回归：齿轮 click → switchChatTab('settings')；
        setPetMinimized 仍经 __xiaoju3Console 桥被桌宠菜单「缩小」调用
        （入口迁移≠功能删除）。"""
        js = _read("console.js")
        self.assertIn("getElementById('console-settings-entry')", js)
        self.assertIn("switchChatTab('settings')", js)
        self.assertIn("setPetMinimized: setPetMinimized", js)
        self.assertIn("b.setPetMinimized(true)", _read("desktop-pet.js"))

    def test_render_iterates_without_hardcoded_keys(self):
        """渲染=遍历 items（.forEach），零键名硬编码——18 键集增减/扩白名单
        均无需改前端；分档表是唯一事实源（B1 设计取舍）。"""
        body = _fn_body(self.js, "renderSettingsItems")
        self.assertIn(".forEach", body)
        for key in ("USER_CITY", "USER_DISTRICT", "TTS_VOICE",
                    "CHILD_LOCK_ENABLED", "LOCAL_MODEL_SMALL", "DEVICE_TIER",
                    "LOCAL_MODEL", "XIAOJU3_PERSONALITY", "DEEPSEEK_API_KEY"):
            self.assertNotIn(key, body)


if __name__ == "__main__":
    unittest.main()
