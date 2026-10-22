# -*- coding: utf-8 -*-
"""直出思维流契约补充锚（2026-10-22 二轮重构收尾，补足退役测试净减口子）。

覆盖：直出构建器 XSS/边界口径、刷新同步链、看门狗清理点、错开淡入细节、
直出 CSS 逐条、终端面板直出、运行时烟雾存在性（作用域雷唯一可靠门）。
"""
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


def _extract_span(js, start_marker, end_marker, start=0):
    i = js.index(start_marker, start)
    return js[i:js.index(end_marker, i)]


class ThinkLiveBuilderDeepTests(unittest.TestCase):
    """buildThinkLiveBlock 深度契约。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_builder_textcontent_only(self):
        """全 textContent 注入：构建器函数体零 innerHTML（XSS 口径；
        切片到 return wrap 为止，不吃下一函数的注释）。"""
        body = _extract_span(self.js, "function buildThinkLiveBlock",
                             "return wrap;")
        self.assertNotIn("innerHTML", body)
        self.assertEqual(body.count("textContent ="), 2)  # 标签+行文本

    def test_fallback_dark_block_intact(self):
        """深色降级块零回退：#1f2937/白字/13px/前 200 字/textContent。"""
        body = _extract_span(self.js, "function buildThinkFallbackBlock",
                             "const THINK_STAGE_RE")
        for token in ("#1f2937", "#ffffff", "13px", "slice(0, 200)",
                      "textContent ="):
            self.assertIn(token, body)

    def test_sync_think_card_rebuild_chain(self):
        """刷新重生成同步链：旧块移除→null 早退→重建→降级兜底，全链在位。"""
        body = _extract_span(self.js, "function syncThinkCard",
                             "function appendUserMessage")
        self.assertIn("const old = msgEl.querySelector('.think-live');", body)
        self.assertIn("if (old) old.remove();", body)
        self.assertIn("if (thinkText === null) return;", body)
        self.assertIn("buildThinkLiveBlock(thinkText)", body)
        self.assertIn("buildThinkFallbackBlock(thinkText)", body)
        self.assertIn('console.error("CoT Render Error: ", e)', body)


class WatchdogCleanupTests(unittest.TestCase):
    """看门狗清理点全覆盖：任何收口路径都拆狗，无悬挂定时器。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_watchdog_cleared_on_done_and_error_and_catch(self):
        """done 清狗 + error 帧 throw 后 catch 清狗 + legacy 无看门狗残留。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        done_at = block.index("} else if (etype === 'done') {")
        done_body = block[done_at:block.index("} else if (etype === 'error') {", done_at)]
        self.assertIn("clearTimeout(watchdog);", done_body)
        self.assertIn("clearTimeout(streamGuard);", done_body)
        catch_body = block[block.index(".catch(function (err) {"):]
        self.assertIn("clearTimeout(watchdog);", catch_body)
        self.assertIn("clearTimeout(streamGuard);", catch_body)

    def test_total_guard_190s_kept(self):
        """190s 总闸 AbortController 保留（比后端 180s 略长的最终防线）。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        self.assertIn("const streamGuard = setTimeout(() => ac.abort(), 190000);", block)
        self.assertIn("signal: ac.signal", block)

    def test_watchdog_error_message_copy(self):
        """看门狗报错文案：明示自动中断+可重试（现场可懂，不抛裸异常）。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        self.assertIn("长时间无响应已自动中断", block)
        self.assertIn("mountSystemToolbar(errMsg)", block)


class HistoryStaggerDetailTests(unittest.TestCase):
    """错开淡入细节：仅历史批渲染，流式零沾染。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_stagger_cap_and_scope(self):
        """延时上限 400ms 防长历史尾等待；user/assistant 两类都挂。"""
        hist = _extract_span(self.js, "function loadHistory",
                             "// ==================== 4.")
        self.assertIn("Math.min(idx * 45, 400)", hist)
        self.assertEqual(hist.count("classList.add('msg-enter')"), 1)  # el 统一出口
        self.assertIn("el = appendUserMessage(", hist)
        self.assertIn("el = appendBotMessage(", hist)


class ThinkLiveCssDetailTests(unittest.TestCase):
    """直出 CSS 逐条口径。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")

    def _rule(self, selector):
        start = self.html.index(selector)
        return self.html[start:self.html.index("}", start)]

    def test_live_block_rules(self):
        """块：灰色小号（12px + secondary 文字色）；行：pre-wrap+break-word。"""
        block = self._rule(".think-live {")
        self.assertIn("font-size: 12px", block)
        block_line = self._rule(".think-live-line {")
        self.assertIn("white-space: pre-wrap", block_line)
        self.assertIn("word-break: break-word", block_line)

    def test_tabular_nums_on_label(self):
        """耗时数字等宽（用时 X 秒防抖，UI 规范延续到直出标签）。"""
        block = self._rule(".think-live-label {")
        self.assertIn("font-variant-numeric: tabular-nums", block)

    def test_tool_and_badge_concentric(self):
        """同心圆角落点：.tool-btn 与 .source-badge 两处（appendBotMessage
        工具栏/来源徽章）。"""
        html = self.html
        self.assertIn(".tool-btn {", html)
        self.assertIn(".source-badge {", html)


class RuntimeSmokePresenceTests(unittest.TestCase):
    """运行时烟雾存在性：作用域雷的唯一可靠自动门必须常驻。"""

    def test_smoke_file_registered(self):
        path = os.path.join(PROJECT_ROOT, "tests",
                            "test_streamcard_runtime_smoke.py")
        self.assertTrue(os.path.exists(path))
        src = open(path, encoding="utf-8").read()
        self.assertIn("__XJ3_SMOKE__", src)
        self.assertIn("window.sendMessage", src)

    def test_terminal_panel_uses_live_block(self):
        """终端记录面板同步直出（二轮重构补漏点）：不再引用旧卡片构建器。"""
        js = _read("console.js")
        self.assertIn("buildThinkLiveBlock(parts.think)", js)
        self.assertNotIn("buildThinkCardEl()", js)


class DashCardTests(unittest.TestCase):
    """侧栏仪表盘卡片化锚（2026-10-22 答辩微调：小米负一屏风，纯样式零逻辑）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        cls.js = _read("console.js")

    def test_card_family_and_breathing_gap(self):
        """卡片家族：多层柔影+卡片圆角令牌；侧栏呼吸间距 12px；底色让位。"""
        html = self.html
        start = html.index(".dash-card {")
        block = html[start:html.index("}", start)]
        self.assertIn("box-shadow: var(--shadow-card)", block)
        self.assertIn("border-radius: var(--radius-card)", block)
        sb = html[html.index(".sidebar {"):]
        sb = sb[:sb.index("}", 0) + 1] if False else html[html.index(".sidebar {"):html.index(".panel-header")]
        self.assertIn("gap: 12px", sb)
        self.assertEqual(html.count('class="stat-item dash-card"'), 5)  # CPU/内存/温度/天气/待办

    def test_gradient_progress_bars(self):
        """暖橘渐变默认档 + 三档阈值各自渐变（尾巴 H 阈值口径不变）。"""
        html = self.html
        self.assertIn("background-image: linear-gradient(90deg, #f6b26b, #e8833a)", html)
        for pair in (("#7bc98a, #2fa24c"), ("#f5d06f, #eab308"), ("#ef8b87, #e0433f")):
            self.assertIn(f"linear-gradient(90deg, {pair})", html)
        self.assertIn("阈值在 console.js 常量", html)   # 阈值注释保留（口径未动）

    def test_p0_badge_low_sat_red(self):
        """P0 低饱和红徽标：CSS 类 + 渲染侧修饰类成对。"""
        html = self.html
        start = html.index(".todo-pr-badge.todo-pr-p0 {")
        block = html[start:html.index("}", start)]
        self.assertIn("background: #fdecea", block)
        self.assertIn("color: #b3423e", block)
        self.assertIn('todo-pr-badge${pr === \'P0\' ? \' todo-pr-p0\' : \'\'}', self.js)

    def test_quick_cards_static_and_wiring(self):
        """占位卡：天气静态卡带「示例数据」标注（真实性红线）；快捷按钮接线
        =预填待办话术+/api/health 既有端点消费，零新增后端。"""
        html = self.html
        self.assertIn("示例数据 · 聚合面板见路线图 #351", html)
        self.assertIn('id="quick-todo"', html)
        self.assertIn('id="quick-check"', html)
        js = self.js
        self.assertIn("function initQuickActions", js)
        self.assertIn("input.value = '帮我记待办：';", js)
        self.assertIn("fetch('/api/health')", js)
        self.assertIn("🩺 系统自检通过：服务健康", js)

    def test_sidebar_scroll_fix(self):
        """紧急修复（2026-10-22）：侧栏整栏滚动+底部留白+细腻滚动条；待办
        列表内层滚动上限改视口自适应（180px 写死退役）；卡片禁 flex 压缩
        （todos-list 有 overflow→min-height 归零→待办卡被压瘪才是截断真因）。"""
        html = self.html
        sb = html[html.index(".sidebar {"):html.index(".panel-header")]
        self.assertIn("overflow-y: auto", sb)
        self.assertIn("padding-bottom: 20px", sb)
        self.assertIn(".sidebar::-webkit-scrollbar-thumb", html)
        tl_at = html.index(".todos-list {")
        tl = html[tl_at:html.index("}", tl_at)]
        self.assertIn("max-height: 32vh", tl)
        self.assertNotIn("max-height: 180px", html)
        dc_at = html.index(".dash-card {")
        dc = html[dc_at:html.index("}", dc_at)]
        self.assertIn("flex-shrink: 0", dc)


if __name__ == "__main__":
    unittest.main()
