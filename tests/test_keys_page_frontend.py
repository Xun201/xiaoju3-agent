# -*- coding: utf-8 -*-
"""#264 B2b 密钥管理页前端锚（源码级静态断言）。

覆盖：
- index.html：🔑入口（缺省 hidden）+ keys-pane + 挂载点/刷新按钮；
- console.js：GET /api/keys 探针+loadKeys；**掩码渲染零明文接触**
  （渲染函数体不引用 value——后端只回 masked/set，前端不自己拼）；
- 覆盖流程：二次确认（window.confirm）+ POST body {key,value,confirm:true}；
- LV3+ 门：探针 403 → 🔑 hidden（后端 403 双保险）。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _fn_body(src, name):
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


class KeysPageHtmlTests(unittest.TestCase):
    """index.html 结构锚。"""

    def test_entry_button_and_pane_present(self):
        html = _read("index.html")
        self.assertIn(
            '<button id="keys-entry" class="header-btn" title="密钥管理" hidden>🔑</button>',
            html)   # 缺省 hidden：探针 200 才显示（LV3+ 门）
        self.assertIn('<div class="settings-pane" id="keys-pane" hidden>', html)
        self.assertIn('id="keys-list"', html)
        self.assertIn('id="keys-refresh"', html)
        # pane 位置：settings-pane 之后、输入区之前（三 pane 平级）
        self.assertLess(html.index('id="keys-pane"'),
                        html.index('class="chat-input-area"'))
        self.assertGreater(html.index('id="keys-pane"'),
                           html.index('id="settings-list"'))


class KeysPageJsTests(unittest.TestCase):
    """console.js 契约锚。"""

    @classmethod
    def setUpClass(cls):
        cls.cjs = _read("console.js")

    def test_get_keys_probe_and_load(self):
        """GET /api/keys：页面加载探针（LV3+ 门）+ loadKeys 拉取。"""
        self.assertIn("function probeKeysAccess()", self.cjs)
        probe = _fn_body(self.cjs, "probeKeysAccess")
        self.assertIn("fetch('/api/keys')", probe)
        self.assertIn("keysEntryBtn.hidden = false", probe)
        self.assertIn("keysEntryBtn.hidden = true", probe)   # 403 → 入口隐藏
        load = _fn_body(self.cjs, "loadKeys")
        self.assertIn("fetch('/api/keys')", load)
        self.assertIn("renderKeysItems(body)", load)

    def test_masked_render_never_touches_plaintext(self):
        """掩码渲染零明文接触（设计稿铁律）：渲染函数体只用 masked/set，
        不读不拼 value（GET 响应本就无 value 字段，前端不得假设有）。"""
        for fn in ("renderKeysItems", "buildKeysRow"):
            body = _fn_body(self.cjs, fn)
            self.assertNotIn(".value", body, fn + " 引用了 value（明文泄露风险）")
            self.assertNotIn("value:", body, fn + " 拼装了 value 字段")
        build = _fn_body(self.cjs, "buildKeysRow")
        self.assertIn("it.masked", build)   # 掩码严格按后端返回
        self.assertIn("it.set", build)      # 未配置灰态

    def test_overwrite_second_confirm(self):
        """覆盖流程：保存前 window.confirm 二次确认（设计稿拍板防误操作）。"""
        body = _fn_body(self.cjs, "startKeyEdit")
        self.assertIn("window.confirm('确认覆盖 '", body)
        self.assertIn("旧值不可恢复。", body)

    def test_post_body_has_confirm_true(self):
        """POST /api/keys body {key,value,confirm:true}（后端 400 兜底）。"""
        body = _fn_body(self.cjs, "startKeyEdit")
        self.assertIn("method: 'POST'", body)
        self.assertIn("key: it.key", body)
        self.assertIn("value: value", body)
        self.assertIn("confirm: true", body)
        self.assertIn("input.value = ''", body)   # 明文即清不缓存

    def test_header_icon_order_and_theme_entry_removed(self):
        """#264 B2b 微调：header-actions 排列=…🔑（密钥）→⚙️（设置）；
        头部 🦊 主题按钮禁绝（双入口冗余，入口=桌宠菜单+设置页偏好组）。
        回归：三主题入口中桌宠菜单/设置页仍在（toggleTheme 单一实现）。"""
        html = _read("index.html")
        keys_idx = html.index('id="keys-entry"')
        gear_idx = html.index('id="console-settings-entry"')
        self.assertLess(keys_idx, gear_idx)   # 🔑 在 ⚙️ 之前
        self.assertNotIn('id="theme-toggle"', html)
        js = _read("console.js")
        self.assertIn("toggleTheme: toggleTheme", js)   # 桌宠菜单入口在
        self.assertIn("applyTheme(themeSel.value)", js)   # 设置页入口在

    def test_lv_gate_hides_entry(self):
        """LV3+ 门双保险：探针 403/异常 → 🔑 hidden；注册表 keys 条目在位。"""
        self.assertIn("keys: {", self.cjs)
        self.assertIn("btn: function () { return keysEntryBtn; }", self.cjs)
        self.assertIn("keysEntryBtn.addEventListener('click'", self.cjs)
        self.assertIn("switchChatTab('keys')", self.cjs)


    def test_keys_back_button(self):
        """#264 B2c 合并批：密钥 pane「← 返回」= 回对话窗口（与设置页同构）。
        另锁 header 探针绑定与刷新接线（事①配套）。"""
        html = _read("index.html")
        self.assertIn('id="keys-back"', html)
        cjs = _read("console.js")
        self.assertIn("getElementById('keys-back')", cjs)
        self.assertIn("keysBackBtn.addEventListener('click'", cjs)
        self.assertIn("switchChatTab('console')", cjs)
        self.assertIn("keysRefreshBtn.addEventListener('click', loadKeys)", cjs)


if __name__ == "__main__":
    unittest.main()
