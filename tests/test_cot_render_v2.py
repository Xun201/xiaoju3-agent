# -*- coding: utf-8 -*-
"""任务 2 CoT DeepSeek 风格改版 + 任务 4 桌宠下线只留加速球（前端静态断言）。

契据（2026-10-01 用户口径，独立于 tests/test_dashboard.py——该文件归主控）：

任务 2（console.js / index.html）：
- 收到 <think> 块后【一次性把所有行渲染出来】：[思考]/[计划]/[行动] 各占
  一行，徽章分色（蓝/绿/橙）+ 层级缩进成完整列表；既有 THINK_LINE_STEP_MS
  逐行淡入 setTimeout 链废止（无逐条闪动/逐字打字）。
- 全部渲染完等待 1.5 秒（THINK_COLLAPSE_DELAY_MS = 1500）后动画折叠：
  内联 max-height 从实测可视高度收缩到 0，CSS transition 约 300ms
  （.think-card.think-anim .think-card-body）；折叠完成后才显示正文气泡
  （.think-pending 显隐机制，由 console.js 挂/摘类）。
- 用户点击折叠卡片标题可再展开（toggleThinkCard 类切换保留），展开态
  .think-card-body 既有 max-height: 260px + overflow-y: auto 滚动保留。
- 降级链零回退：无阶段标记内容沿用原逐字打字机（THINK_TYPE_MS）、裸标记
  扫描/[行动] 剥离/强制兜底卡片/深色降级块/历史回放折叠态全部保留。

任务 4（index.html / console.js / desktop-pet.js）：
- index.html 停止加载 desktop-pet.js（script 标签注释掉并注明原因；文件
  本体保留在仓库不删除，未来可恢复；onerror 裂图回退链原样保留）。
- 加速球（#xiaoju3-ball，60px 小橘头像）保留：可拖拽（位移平方>9 阈值、
  localStorage 位置记忆）、可展开/收回（console-minimize 互切），逻辑不动。
- 右下角只允许一个悬浮元素：加速球（页面 img 仅剩球头像一张，无其他形象）。

全部静态断言，离线可跑（无网络、无浏览器；node 语法门缺 node 时跳过）。
"""

import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


def _strip_html_comments(html):
    """去掉 HTML 注释后的内容（检查"实际会被浏览器加载/渲染"的部分）。"""
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _extract_span(js, start_marker, end_marker, start=0):
    """提取 js 中 [start_marker, end_marker) 区间源码（断言函数体内部结构）。"""
    i = js.index(start_marker, start)
    return js[i:js.index(end_marker, i)]


# ---------------------------------------------------------------------------
# 任务 2：一次性渲染（无逐行 setTimeout 链）
# ---------------------------------------------------------------------------

class CotOneShotRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _typewriter_body(self):
        return _extract_span(self.console_js,
                             "function startThinkTypewriter",
                             "window.toggleThinkCard")

    def test_line_step_chain_removed(self):
        """逐行淡入链已废止：THINK_LINE_STEP_MS 常量与 revealNextLine
        setTimeout 链不再存在于 console.js（一次性渲染取代逐条闪动）。"""
        js = self.console_js
        self.assertNotIn("THINK_LINE_STEP_MS", js)
        self.assertNotIn("revealNextLine", js)
        self.assertNotIn("setTimeout(revealNextLine", js)

    def test_one_shot_render_all_lines(self):
        """一次性渲染主链路：有阶段标记时 body 清空后 forEach 同帧插入全部
        行（buildThinkLineEl），随后立即调度收起（无任何逐行定时器）。"""
        body = self._typewriter_body()
        self.assertIn(
            "segs.forEach(function (seg) { body.appendChild(buildThinkLineEl(seg)); });",
            body)
        # 渲染完成后才调度折叠（先全量上屏、后收起）
        self.assertLess(
            body.index("body.appendChild(buildThinkLineEl(seg))"),
            body.rindex("scheduleThinkCollapse(card, msgEl)"))
        # 每行插入前先清空正文（强制兜底卡片可能已预填全文的场景）
        self.assertIn("body.textContent = '';", body)

    def test_stage_split_and_line_builder_kept(self):
        """分段函数与单行构建器保留：[思考]/[计划]/[行动] 半角方括号阶段
        标记起新段（与后端协议同口径），buildThinkLineEl 构建单行段元素。"""
        js = self.console_js
        self.assertIn("function splitThinkStageLines", js)
        self.assertIn("function buildThinkLineEl", js)
        self.assertIn(r"/^\[(思考|计划|行动)\]/", js)
        el_body = _extract_span(js, "function buildThinkLineEl",
                                "function hideBubbleUntilThinkDone")
        # 全部 textContent 注入免 XSS；类名基础标记保留
        self.assertIn("tag.textContent = seg.tag", el_body)
        self.assertIn("text.textContent = seg.text", el_body)
        self.assertIn("className = 'think-line'", el_body)
        self.assertIn("className = 'think-line-tag'", el_body)
        self.assertIn("className = 'think-line-text'", el_body)
        # 阶段分色 + 层级缩进类挂载（三阶段颜色/缩进区分，完整列表视觉）
        self.assertIn("classList.add(THINK_TAG_CLASS[seg.tag]", el_body)
        self.assertIn("classList.add(THINK_INDENT_CLASS[seg.tag]", el_body)
        self.assertIn("'思考': 'think-tag-think'", js)
        self.assertIn("'计划': 'think-tag-plan'", js)
        self.assertIn("'行动': 'think-tag-action'", js)
        self.assertIn("'思考': 'think-indent-1'", js)
        self.assertIn("'计划': 'think-indent-2'", js)
        self.assertIn("'行动': 'think-indent-3'", js)

    def test_stage_styles_in_index_html(self):
        """index.html 阶段样式：徽章三色（[思考] 蓝 #3b82f6 / [计划] 绿
        #2fa24c / [行动] 橙 #d96f2b）+ 缩进三档；淡入动画保留。"""
        html = self.index_html
        self.assertIn(".think-line-tag.think-tag-think", html)
        self.assertIn(".think-line-tag.think-tag-plan", html)
        self.assertIn(".think-line-tag.think-tag-action", html)
        for color in ("#3b82f6", "#2fa24c", "#d96f2b"):
            self.assertIn(color, html)
        self.assertIn(".think-line.think-indent-2", html)
        self.assertIn(".think-line.think-indent-3", html)
        # 整体淡入动效保留（所有行同时浮现，非逐行错峰）
        start = html.index(".think-line {")
        line_css = html[start:html.index("}", start)]
        self.assertIn("animation: thinkLineFadeIn", line_css)
        self.assertIn("@keyframes thinkLineFadeIn", html)

    def test_no_marker_degradation_kept(self):
        """降级链零回退：无阶段标记的思考文本沿用原逐字打字机
        （THINK_TYPE_MS 口径、textContent 切片注入）。"""
        js = self.console_js
        self.assertIn("const THINK_TYPE_MS = 15;", js)
        body = self._typewriter_body()
        self.assertIn("body.textContent = text.slice(0, shown)", body)


# ---------------------------------------------------------------------------
# 任务 2：1.5s 延迟折叠 + 300ms 过渡 + 点击再展开
# ---------------------------------------------------------------------------

class CotCollapseRhythmTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _collapse_helpers(self):
        """console.js 折叠辅助区（气泡显隐 + 动画折叠 + 调度器）。"""
        return _extract_span(self.console_js,
                             "function hideBubbleUntilThinkDone",
                             "function startThinkTypewriter")

    def test_collapse_delay_constants(self):
        """折叠节奏常量：渲染完等 1.5s（THINK_COLLAPSE_DELAY_MS = 1500）、
        过渡约 300ms（THINK_COLLAPSE_MS = 300，兜底收尾定时器取值）。"""
        js = self.console_js
        self.assertIn("const THINK_COLLAPSE_DELAY_MS = 1500;", js)
        self.assertIn("const THINK_COLLAPSE_MS = 300;", js)

    def test_css_transition_300ms(self):
        """index.html 折叠动画 CSS：.think-anim 态下正文 max-height 过渡
        0.3s ease（300ms），由 console.js 挂/摘类启用。"""
        html = self.index_html
        start = html.index(".think-card.think-anim .think-card-body")
        css = html[start:html.index("}", start)]
        self.assertIn("transition: max-height 0.3s ease", css)

    def test_js_collapse_sequence(self):
        """JS 折叠序列：先写实测可视高度（clientHeight，避免超限滚动态
        视觉跳动）→ 挂 .think-anim → 强制回流 → 归零触发过渡 → transitionend
        /兜底定时器收尾（落回 .think-collapsed、清内联样式、放行正文）。"""
        helpers = self._collapse_helpers()
        self.assertIn("function animateThinkCollapse", helpers)
        self.assertIn("body.style.maxHeight = body.clientHeight + 'px';", helpers)
        self.assertIn("classList.add('think-anim')", helpers)
        self.assertIn("void body.offsetHeight;", helpers)          # 强制回流
        self.assertIn("body.style.maxHeight = '0px';", helpers)
        self.assertIn("addEventListener('transitionend', finish)", helpers)
        self.assertIn("setTimeout(finish, THINK_COLLAPSE_MS + 150)", helpers)
        finish_at = helpers.index("const finish = function () {")
        finish_body = helpers[finish_at:helpers.index("};", finish_at)]
        self.assertIn("card.classList.add('think-collapsed')", finish_body)
        self.assertIn("classList.remove('think-anim')", finish_body)
        self.assertIn("body.style.maxHeight = '';", finish_body)
        self.assertIn("showBubbleNow(msgEl)", finish_body)

    def test_delay_then_collapse_scheduled(self):
        """渲染完成 → 延迟调度：setTimeout(…, THINK_COLLAPSE_DELAY_MS)；
        两条渲染路径（一次性列表 / 逐字打字机降级）完成后都走同一调度器。"""
        js = self.console_js
        self.assertIn("function scheduleThinkCollapse", js)
        sched = _extract_span(js, "function scheduleThinkCollapse",
                              "function startThinkTypewriter")
        self.assertIn("THINK_COLLAPSE_DELAY_MS", sched)
        body = _extract_span(js, "function startThinkTypewriter",
                             "window.toggleThinkCard")
        self.assertEqual(body.count("scheduleThinkCollapse(card, msgEl)"), 2)

    def test_bubble_hidden_until_collapse_done(self):
        """正文气泡放行节奏：展示开始即挂 .think-pending（index.html 隐藏
        .bubble-content/.source-badge/.msg-tools），折叠完成（或任何提前
        退出）才摘类放行；历史回放早退分支不隐藏。"""
        js = self.console_js
        html = self.index_html
        self.assertIn("function hideBubbleUntilThinkDone", js)
        self.assertIn("function showBubbleNow", js)
        self.assertIn(".classList.add('think-pending')", js)
        self.assertIn(".classList.remove('think-pending')", js)
        for sel in (".message.think-pending .bubble-content",
                    ".message.think-pending .source-badge",
                    ".message.think-pending .msg-tools"):
            self.assertIn(sel, html)
        body = _extract_span(js, "function startThinkTypewriter",
                             "window.toggleThinkCard")
        # 历史回放早退在前、隐藏在后：animate=false 永不隐藏气泡
        self.assertIn("if (!animate || !text) {", body)
        self.assertLess(body.index("if (!animate || !text) {"),
                        body.index("hideBubbleUntilThinkDone(msgEl)"))

    def test_re_expand_on_click(self):
        """点击折叠卡片标题可再展开：toggleThinkCard 类切换保留；展开态
        .think-card-body 既有 max-height: 260px + overflow-y: auto 保留
        （内容完整可见、超限滚动）。"""
        js = self.console_js
        html = self.index_html
        self.assertIn("window.toggleThinkCard", js)
        self.assertIn("classList.toggle('think-collapsed')", js)
        self.assertIn(".think-card.think-collapsed .think-card-body", html)
        start = html.index(".think-card-body {")
        css = html[start:html.index("}", start)]
        self.assertIn("max-height: 260px", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("border-left: 3px solid", css)

    def test_history_replay_direct_collapsed(self):
        """历史回放直接折叠态：共用 appendBotMessage 入口 + animateThink:
        false，不打字不动画、完整填充保持折叠、正文气泡立即可见。"""
        js = self.console_js
        self.assertIn(
            "appendBotMessage(m.content, m.source || '', lastUser, { animateThink: false })",
            js)
        body = _extract_span(js, "function startThinkTypewriter",
                             "window.toggleThinkCard")
        self.assertIn("body.textContent = text;", body)
        self.assertIn("return;", body)


# ---------------------------------------------------------------------------
# 任务 4：桌宠下线只留加速球
# ---------------------------------------------------------------------------

class PetOfflineBallOnlyTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.index_html = _read("index.html")
        cls.console_js = _read("console.js")
        cls.pet_js = _read("desktop-pet.js")

    def test_desktop_pet_script_disabled(self):
        """desktop-pet.js 停止加载：去掉 HTML 注释后（浏览器实际加载面）
        不存在任何指向 desktop-pet.js 的 script 标签；console.js 仍正常加载。"""
        stripped = _strip_html_comments(self.index_html)
        self.assertIsNone(re.search(r"<script[^>]*desktop-pet\.js", stripped))
        self.assertIn('<script src="/console/console.js"></script>', stripped)

    def test_disabled_tag_commented_with_reason(self):
        """下线方式为注释而非删除：原 script 标签原文保留在 HTML 注释中
        （未来恢复只需取消注释），并注明下线原因（桌宠下线字样）。"""
        html = self.index_html
        self.assertIn("<!-- <script src=\"/console/desktop-pet.js\"></script> -->",
                      html)
        self.assertIn("桌宠下线", html)          # 原因注明
        self.assertIn("取消下一行注释", html)     # 恢复方式注明

    def test_pet_file_kept_on_disk_with_fallback_chain(self):
        """桌宠文件本体保留在仓库不删除：IIFE 单例哨兵、双版本状态图常量、
        官方素材兜底与 onerror 裂图回退链（状态图→半身→JPG→SVG 气泡）
        原样保留——仅前端停止加载，文件零回退。"""
        self.assertTrue(os.path.exists(os.path.join(PROJECT_ROOT, "desktop-pet.js")))
        js = self.pet_js
        self.assertIn("window.__xiaoju3Pet", js)
        self.assertIn("PET_STATE_IMAGES", js)
        self.assertIn("PET_FALLBACK_IMAGE = '/assets/DSniang1.jpg'", js)
        self.assertIn("addEventListener('error'", js)   # 裂图回退链入口
        self.assertIn("failedStateUrls", js)
        self.assertIn("refreshImgMode", js)

    def test_ball_kept_in_html(self):
        """加速球保留（index.html 静态节点）：60px 圆形 #xiaoju3-ball、
        小橘头像 /assets/DSniang1.jpg、最小化态显示规则原样。"""
        html = self.index_html
        self.assertIn('id="xiaoju3-ball"', html)
        self.assertIn('src="/assets/DSniang1.jpg"', html)
        self.assertIn("#xiaoju3-ball {", html)
        self.assertIn("body.xiaoju3-minimized #xiaoju3-ball", html)
        self.assertIn('id="console-minimize"', html)      # 缩球入口按钮

    def test_ball_logic_kept_in_console_js(self):
        """加速球交互逻辑不动（console.js）：可拖拽（位移平方>9 阈值、
        setPointerCapture）、localStorage 位置记忆、点击展开/收回互切。"""
        js = self.console_js
        section = _extract_span(js, "缩成加速球", "initConsoleBall();") \
            + js[js.index("initConsoleBall();"):]
        self.assertIn("function initConsoleBall", section)
        self.assertIn("const BALL_SIZE = 60", section)
        self.assertIn("const BALL_POS_KEY = 'xiaoju3_ball_pos'", section)
        self.assertIn("if (dx * dx + dy * dy > 9) moved = true;", section)
        self.assertIn("setPointerCapture", section)
        self.assertIn("localStorage.setItem(BALL_POS_KEY, JSON.stringify(pos))",
                      section)
        self.assertIn("setConsoleMinimized(false);   // 未拖动＝点击展开回完整控制台",
                      section)
        self.assertIn("getElementById('console-minimize')", section)

    def test_no_other_floating_pet_elements(self):
        """右下角只允许一个悬浮元素：页面 img 仅剩加速球头像一张（桌宠
        形象无任何残留节点）；挂件容器 #xiaoju3-root 为空 div（无视觉）。"""
        html = self.index_html
        stripped = _strip_html_comments(html)
        imgs = re.findall(r'<img[^>]*src="([^"]+)"', stripped)
        self.assertEqual(imgs, ["/assets/DSniang1.jpg"])   # 唯一图片=球头像
        self.assertIn('<div id="xiaoju3-root"></div>', stripped)
        # 加速球元素仍引用头像（资产保留在仓库且前端仍用）
        ball = re.search(r'<div id="xiaoju3-ball".*?</div>', html, flags=re.S)
        self.assertIsNotNone(ball)
        self.assertIn("/assets/DSniang1.jpg", ball.group(0))


# ---------------------------------------------------------------------------
# 零回退哨兵：splitThinkBlock 容错/兜底/诊断链一律保留
# ---------------------------------------------------------------------------

class ZeroRegressionSentinelTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def test_split_think_block_chain_intact(self):
        """统一入口 splitThinkBlock 全链保留：<think> 非锚定正则、裸标记
        扫描（[思考]/[计划] 并卡）、[行动]+JSON 剥离、剥空占位、孤儿/
        未配对容错、try/catch 安全降级。"""
        js = self.console_js
        for token in (
            "const THINK_BLOCK_RE = /<think>([\\s\\S]*?)<\\/think>/;",
            "BARE_THINK_RE", "BARE_PLAN_RE", "BARE_ACTION_RE",
            "bareParts", "（操作已执行）",
            "const openIdx = body.indexOf('<think>')",
            'console.error("CoT Render Error: ", e)',
            "return { think: think, body: body }",
            "return { think: think, body: raw }",
        ):
            self.assertIn(token, js)

    def test_forced_fallback_card_and_dark_block_kept(self):
        """强制兜底卡片（createElement + classList.add + prepend）与深色
        纯文本降级块（buildThinkFallbackBlock）零回退。"""
        js = self.console_js
        self.assertIn("function buildThinkFallbackBlock", js)
        self.assertIn("classList.add('think-card')", js)
        self.assertIn("botMsg.prepend(", js)
        self.assertIn("#1f2937", js)                       # 深色兜底块背景
        self.assertIn('console.log("RENDERING_THINK_CARD...")', js)
        self.assertIn('console.log("RAW_REPLY:", res.data.reply)', js)
        self.assertIn('console.log("PARSED_THINK:"', js)

    def test_render_entry_guard_untouched(self):
        """渲染入口仅由 think !== null 守卫（三条路径不变）：实时回复、
        刷新重生成（syncThinkCard）、历史回放。"""
        js = self.console_js
        self.assertIn("if (thinkParts.think !== null)", js)
        self.assertIn("syncThinkCard(msgEl, thinkParts.think)", js)
        self.assertIn("if (thinkText === null) return;", js)
        self.assertIn("options.animateThink !== false", js)

    def test_no_new_external_dependency(self):
        """零新依赖、零外部 CDN：index.html 无外链 script；改动未引入新
        第三方资源。"""
        stripped = _strip_html_comments(self.index_html).lower()
        self.assertNotIn("<script src=\"http", stripped)
        self.assertNotIn("https://", stripped)
        self.assertNotIn("http://", stripped)


# ---------------------------------------------------------------------------
# node 语法门（环境无 node 时跳过，静态断言仍全量生效）
# ---------------------------------------------------------------------------

class NodeSyntaxGateTests(unittest.TestCase):

    def test_console_js_and_pet_js_syntax_valid(self):
        """node --check：console.js 与 desktop-pet.js 语法合法（改动不破坏
        整个前端；desktop-pet.js 文件本体零改动仍需可解析）。"""
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过 JS 语法门（静态断言已覆盖）")
        for name in ("console.js", "desktop-pet.js"):
            proc = subprocess.run(
                ["node", "--check", os.path.join(PROJECT_ROOT, name)],
                capture_output=True, timeout=60)
            self.assertEqual(proc.returncode, 0,
                             "%s: %s" % (name, proc.stderr.decode("utf-8", "replace")))


if __name__ == "__main__":
    unittest.main()
