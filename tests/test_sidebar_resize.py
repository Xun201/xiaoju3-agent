# -*- coding: utf-8 -*-
"""侧栏拖拽调宽（2026-10-27）：QuitBridge 布局偏好两方法 + 前端静态锚。

覆盖：
- get_layout_pref：未设置返回 None；损坏文件兜底不炸；
- set_layout_pref：合法值落盘回读 / 0=删键复位 / 非法（越界/非数字）
  拒绝且文件不被污染 / 与 exit、dev 键共存互不覆盖；
- 前端锚（按静态锚规范=语句形态：函数体提取+标签/CSS 规则形态，
  不锚松散文本子串）：
  - index.html：把手 div 节点 + #sidebar-resizer 规则含 col-resize
    + ≤768px 媒体内 display:none；
  - console.js：initSidebarResize 函数体含指针捕获/rAF/双击复位/
    js_api 读写/localStorage 键。
"""
import json
import os
import re
import tempfile
import unittest

import desktop_launcher as dl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _fn_body(src, name):
    """按花括号配对提取 JS 函数源码（function name(...) { ... }）。"""
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


def _css_rule(css, selector):
    """提取 CSS 规则体（selector { ... }，取首个命中）。"""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not m:
        raise AssertionError("CSS 规则未找到: %s" % selector)
    return m.group(1)


class LayoutPrefBridgeTests(unittest.TestCase):
    """QuitBridge.get/set_layout_pref（ui_pref.json 布局 KV）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_layout_")
        self.path = os.path.join(self.tmp, "ui_pref.json")
        self.bridge = dl.QuitBridge(lambda: None, {"quitting": None},
                                    pref_path=self.path)

    def _raw(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_get_default_none(self):
        self.assertEqual(self.bridge.get_layout_pref(), {"sidebar_width": None})

    def test_get_corrupt_file_no_crash(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{{{ not json")
        self.assertEqual(self.bridge.get_layout_pref(), {"sidebar_width": None})

    def test_set_valid_roundtrip(self):
        r = self.bridge.set_layout_pref(420)
        self.assertTrue(r["ok"])
        self.assertEqual(r["sidebar_width"], 420)
        self.assertEqual(self._raw()["sidebar_width"], 420)
        self.assertEqual(self.bridge.get_layout_pref()["sidebar_width"], 420)

    def test_set_accepts_js_number_and_numeric_string(self):
        self.assertTrue(self.bridge.set_layout_pref(380.0)["ok"])     # JS number
        self.assertTrue(self.bridge.set_layout_pref("392")["ok"])     # 字符串数字
        self.assertEqual(self._raw()["sidebar_width"], 392)

    def test_set_zero_resets_key(self):
        self.bridge.set_layout_pref(420)
        self.assertTrue(self.bridge.set_layout_pref(0)["ok"])
        self.assertIsNone(self.bridge.get_layout_pref()["sidebar_width"])
        self.assertNotIn("sidebar_width", self._raw())

    def test_set_none_readonly_no_write(self):
        self.bridge.set_layout_pref(420)
        before = self._raw()
        r = self.bridge.set_layout_pref(None)
        self.assertTrue(r["ok"])
        self.assertEqual(self._raw(), before)

    def test_set_invalid_rejected_file_untouched(self):
        self.bridge.set_layout_pref(420)
        before = self._raw()
        for bad in (299, 2001, -1, "abc", [400], object()):
            r = self.bridge.set_layout_pref(bad)
            self.assertFalse(r["ok"], "应拒绝: %r" % (bad,))
            self.assertEqual(r.get("error"), "invalid_width")
        self.assertEqual(self._raw(), before)

    def test_merge_coexists_with_exit_and_dev(self):
        self.bridge.set_exit_pref("full_exit")
        self.bridge.set_layout_pref(400)
        self.assertEqual(self._raw()["exit"], "full_exit")
        self.assertEqual(self._raw()["sidebar_width"], 400)
        self.bridge.set_dev_pref(unlocked=True)
        self.assertEqual(self._raw()["sidebar_width"], 400)
        self.assertEqual(self._raw()["dev_unlocked"], True)
        # 复位不动其他键
        self.bridge.set_layout_pref(0)
        self.assertEqual(self._raw()["exit"], "full_exit")
        self.assertEqual(self._raw()["dev_unlocked"], True)

    def test_falsy_width_other_than_zero_rejected(self):
        # 0 有专义（复位）；空串按非法拒绝，不静默当 None
        self.assertFalse(self.bridge.set_layout_pref("")["ok"])


class SidebarResizeFrontendTests(unittest.TestCase):
    """前端静态锚（语句形态）。"""

    def setUp(self):
        self.html = _read("index.html")
        self.js = _read("console.js")

    def test_handle_node_present(self):
        self.assertIn('<div id="sidebar-resizer"', self.html)
        # 把手位于 .sidebar 与 .chat-area 之间（DOM 顺序锚）
        self.assertLess(self.html.index('<div class="sidebar">'),
                        self.html.index('<div id="sidebar-resizer"'))
        self.assertLess(self.html.index('<div id="sidebar-resizer"'),
                        self.html.index('<div class="chat-area">'))

    def test_resizer_css_rule(self):
        body = _css_rule(self.html, "#sidebar-resizer")
        self.assertIn("cursor: col-resize", body)
        self.assertIn("flex: 0 0 6px", body)   # 2026-10-29 终版：热区 6px
        self.assertIn("margin: 0", body)        # 2026-10-29 二次拍板：色块化布局 body padding 归零，无需负 margin hack
        self.assertIn("align-self: stretch", body)

    def test_resizer_thinline_after_rule(self):
        """分界线形态（2026-10-29 队长口径升级）：全高贯穿——::after
        top/bottom 归零（原 12px 内缩=断裂根因），默认 2px 浅灰实线。"""
        body = _css_rule(self.html, "#sidebar-resizer::after")
        self.assertIn("content: \"", body)
        self.assertIn("position: absolute", body)
        self.assertIn("width: 2px", body)
        self.assertIn("top: 0", body)
        self.assertIn("bottom: 0", body)
        self.assertNotIn("background:", body)  # 2026-10-29 终版：常态无 background 声明（物理删除）
        # 旧内缩断裂形态禁回归
        self.assertNotIn("top: 12px", body)
        self.assertNotIn("bottom: 12px", body)

    def test_resizer_hover_blue_thick(self):
        """hover/拖拽态：点缀蓝高亮+加粗 4px（2026-10-29 队长口径）。"""
        m = re.search(r"#sidebar-resizer:(?:hover|dragging)::after[^{]*\{([^}]*)\}",
                      self.html)
        self.assertTrue(m, "hover/dragging ::after 规则未找到")
        self.assertIn("#2563eb", m.group(1))      # hover/拖拽=点缀蓝浮现

    def test_mobile_media_hides_resizer(self):
        m = re.search(r"@media \(max-width: 768px\)\s*\{", self.html)
        self.assertTrue(m, "≤768px 媒体查询未找到")
        tail = self.html[m.end():m.end() + 2000]
        self.assertRegex(tail, r"#sidebar-resizer\s*\{[^}]*display:\s*none")

    def test_console_logic_anchors(self):
        body = _fn_body(self.js, "initSidebarResize")
        self.assertIn("setPointerCapture", body)
        self.assertIn("requestAnimationFrame", body)
        self.assertIn("'pointerup'", body)
        self.assertIn("'dblclick'", body)
        self.assertIn("set_layout_pref(0)", body)      # 双击复位=删键语义
        self.assertIn("get_layout_pref", body)
        self.assertIn("xiaoju3_sidebar_width", body)
        self.assertIn("matchMedia('(max-width: 768px)')", body)

    def test_drag_clamp_bounds_in_js(self):
        body = _fn_body(self.js, "initSidebarResize")
        self.assertIn("const MIN_W = 300", body)       # 下限同 CSS min-width
        self.assertRegex(body, r"innerWidth \* 0\.55")  # 上限=窗口 55%


if __name__ == "__main__":
    unittest.main()
