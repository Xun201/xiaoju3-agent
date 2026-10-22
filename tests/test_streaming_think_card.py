# -*- coding: utf-8 -*-
"""流式思维卡静态锚（2026-10-22 #349，答辩演示加分项）。

契约（_dev/design_streaming_think_card.md）：
- 流式态=最终态预览：ensureThinkCard 卡头解剖与 buildThinkCardEl 同构
  （图标/标题 span/箭头/onclick 开合），徽章分色/缩进走同一 buildThinkLineEl；
- 保留式收尾：done 后流式卡原地转正（finalizeThinkCard 按 done 净化全文重渲
  一次），经 appendBotMessage thinkCardEl 通道收养进最终消息——不拆卡不重建
  不重放打字机；收养路径跳过 startThinkTypewriter（防双卡双动画）；
- 三状态：思考中（卡头"思考中…"）→ 已完成（"已思考（用时 X 秒）"标题+
  scheduleThinkCollapse 自动收起，点击可再展开）→ error（既有 catch 清过程件
  →legacy 红字，零改动锁存）；
- 正文零干扰：answer 增量通道不动；done 先挂最终气泡再撤 answerEl（换屏零空白）；
- 边界：无流式卡走原重建路径零变化；最终 reply 无 <think> 不保留过程卡。

全部静态断言离线可跑（node 在位时 NodeSyntaxGateTests 另行语法门）。
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


class StreamingCardStructureTests(unittest.TestCase):
    """流式卡骨架与最终卡同构。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def _stream_block(self):
        return _extract_span(self.js, "function sendMessageStream",
                             "function sendMessageLegacy")

    def test_header_anatomy_matches_final_card(self):
        """ensureThinkCard 卡头：onclick 开合 + title span + 箭头（与
        buildThinkCardEl 同构件，折叠/悬停/箭头过渡样式零新增复用）。"""
        block = self._stream_block()
        start = block.index("function ensureThinkCard")
        body = block[start:block.index("function renderThinkProgressive", start)]
        self.assertIn("head.setAttribute('onclick', 'toggleThinkCard(this)')", body)
        self.assertIn("title.className = 'think-card-title'", body)
        self.assertIn("arrow.className = 'think-card-arrow'", body)
        self.assertIn("textContent = '小橘正在思考…'", body)   # 骨架态标题（首字零等待）

    def test_progressive_render_reuses_final_builder(self):
        """渐进渲染复用最终卡构建器：buildThinkLineEl 建行（徽章+缩进同源）；
        文本变化才写 textContent；段标签长全整行重建（半截 [思考] 逐字长全
        场景）。"""
        block = self._stream_block()
        start = block.index("function renderThinkProgressive")
        body = block[start:block.index("function finalizeThinkCard", start)]
        self.assertIn("const segs = splitThinkStageLines(thinkAcc);", body)
        self.assertIn("const row = buildThinkLineEl(segs[segRows.length]);", body)
        self.assertIn("textEl.textContent !== seg.text", body)
        self.assertIn("row.parentNode.replaceChild(fresh, row)", body)
        self.assertIn("history.scrollTop = history.scrollHeight;", body)  # 跟随滚动

    def test_finalize_aligns_to_sanitized_fulltext(self):
        """finalizeThinkCard：按 done 帧净化全文重渲一次（thinkAcc 换源），
        卡头换完成态标题（A1 耗时口径）。"""
        block = self._stream_block()
        start = block.index("function finalizeThinkCard")
        body = block[start:block.index("function ensureAnswerEl", start)]
        self.assertIn("thinkAcc = finalThink;", body)
        self.assertIn("renderThinkProgressive();", body)
        self.assertIn("st.textContent = titleText;", body)


class DoneAdoptionTests(unittest.TestCase):
    """done 保留式收尾：收养进最终消息、跳过打字机、自动收起。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_done_keeps_card_via_adoption(self):
        """done 不再拆卡重放：finalizeThinkCard 转正 + appendBotMessage
        thinkCardEl 通道收养；scheduleThinkCollapse 自动收起（点击可再展开）。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("} else if (etype === 'done') {")
        done_body = block[start:block.index("} else if (etype === 'error') {", start)]
        self.assertIn("finalizeThinkCard(parts.think,", done_body)
        self.assertIn("appendBotMessage(data.reply, data.source, text,", done_body)
        self.assertIn("adopted ? { thinkCardEl: adopted } : null", done_body)
        self.assertIn("scheduleThinkCollapse(adopted, botMsg);", done_body)
        # 旧拆卡重放已退役：done 分支不再无条件 removeChild 流式卡
        self.assertNotIn(
            "if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);\n"
            "                    if (toolEl", done_body)

    def test_no_think_reply_drops_process_card(self):
        """边界：最终 reply 无 <think>（理论边角）→旧口径不保留过程卡。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("} else if (etype === 'done') {")
        done_body = block[start:block.index("} else if (etype === 'error') {", start)]
        self.assertIn("if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);",
                      done_body)

    def test_adoption_skips_typewriter(self):
        """收养路径跳过打字机/折叠链（流式卡已定稿，防双卡双动画）；非收养
        路径（含指令单帧 done/历史回放/legacy）打字机原样保留。"""
        js = self.js
        self.assertIn("if (!options.thinkCardEl) {", js)
        guard_at = js.index("if (!options.thinkCardEl) {")
        self.assertIn(
            "startThinkTypewriter(botMsg, thinkParts.think, options.animateThink !== false)",
            js[guard_at:guard_at + 300])

    def test_append_bot_message_adopts_existing_card(self):
        """appendBotMessage 收养分支：thinkCardEl 校验后原卡移动（insertBefore
        自动摘离旧父），非收养照旧 buildThinkCardEl 新建。"""
        js = self.js
        start = js.index("const thinkCard = (options.thinkCardEl && options.thinkCardEl.classList &&")
        body = js[start:js.index("} catch (e) {", start)]
        self.assertIn("options.thinkCardEl.classList.contains('think-card')", body)
        self.assertIn("? options.thinkCardEl : buildThinkCardEl();", body)
        self.assertIn("parentEl.insertBefore(thinkCard, bubbleEl);", body)

    def test_answer_swap_without_blank_gap(self):
        """正文零干扰：done 先挂最终气泡（appendBotMessage）再撤 answerEl——
        换屏零空白；answer 增量通道原样。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("} else if (etype === 'done') {")
        done_body = block[start:block.index("} else if (etype === 'error') {", start)]
        self.assertLess(done_body.index("const botMsg = appendBotMessage("),
                        done_body.rindex("if (answerEl && answerEl.parentNode)"))

    def test_fallback_duration_title_kept(self):
        """A1 耗时锚双保险：未走收养的兜底分支仍查 botMsg 卡头写耗时标题。"""
        js = self.js
        self.assertIn("已思考（用时 ' + secs + ' 秒）", js)
        self.assertIn("botMsg.querySelector('.think-card-title')", js)


class ErrorStateTests(unittest.TestCase):
    """error 状态：既有清理链与 legacy 回退零改动锁存。"""

    def test_error_cleans_process_elements_then_rethrow(self):
        js = _read("console.js")
        self.assertIn("} else if (etype === 'error') {\n"
                      "                    throw new Error(data.error || 'stream error');",
                      js)
        self.assertIn("return pump().catch", js)         # 内层清过程件再 rethrow
        self.assertIn("if (thinkCard && thinkCard.parentNode)", js)
        self.assertIn(".catch(() => sendMessageLegacy", js)   # 转红字提示重答


class RegressionSentinelTests(unittest.TestCase):
    """零回退哨兵：非流式路径与既有契约不受本轮改动影响。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_legacy_and_history_paths_untouched(self):
        js = self.js
        self.assertIn("appendBotMessage(res.data.reply, res.data.source, text)",
                      js)                                 # legacy 同步链调用形态未变
        self.assertIn("appendBotMessage(m.content, m.source || '', lastUser,",
                      js)                                 # 历史回放入口未变
        self.assertIn("function syncThinkCard", js)       # 刷新重生成链未动
        self.assertIn("const THINK_COLLAPSE_DELAY_MS = 1500;", js)

    def test_thinking_state_title_kept(self):
        """思考中状态标题（首增量置位）保留——A1 锚原文形态。"""
        js = self.js
        self.assertIn("const st = thinkCard && thinkCard.querySelector('.think-card-title');",
                      js)
        self.assertIn("st.textContent = '思考中…';", js)

    def test_tool_line_removed_at_done(self):
        """tool 行随 done 移除（与最终卡同形）；tool 事件建卡通道保留。"""
        js = self.js
        self.assertIn("ensureThinkCard();   // C3b：无卡也建", js)
        self.assertIn("toolEl.textContent = '🔧 正在执行工具：' + (data.name || '');",
                      js)


class UiSpecTests(unittest.TestCase):
    """AI 客户端高质感 UI 规范（2026-10-22 队长口述）四件锚。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")
        cls.html = _read("index.html")

    def test_ink_wash_animation(self):
        """水墨晕染：thinkLineFadeIn 关键帧含 blur 消散（取消单字硬蹦）；
        时长 0.45s ease-out；流式在写行 .think-line-streaming 半透明水墨态。"""
        html = self.html
        self.assertIn("animation: thinkLineFadeIn 0.45s ease-out forwards", html)
        kf = html[html.index("@keyframes thinkLineFadeIn"):]
        kf = kf[:kf.index(".think-line.think-indent-1")]   # 取到下一规则为止（内含双花括号）
        self.assertIn("filter: blur(4px)", kf)
        self.assertIn("filter: blur(0)", kf)
        self.assertIn(".think-line-streaming { opacity: 0.66; }", html)
        # JS 侧挂/摘：渐进渲染给末行挂水墨态，转正后全行摘
        self.assertIn("row.classList.add('think-line-streaming')", self.js)
        self.assertIn("el.classList.remove('think-line-streaming')", self.js)

    def test_tabular_nums_for_dynamic_digits(self):
        """动态数字等宽：卡头标题 tabular-nums（用时 X 秒）防左右抖动。"""
        self.assertIn(".think-card-title { flex: 1; font-variant-numeric: tabular-nums; }",
                      self.html)

    def test_container_hierarchy_no_solid_border(self):
        """容器层级：.think-card 无实体边框（border: none），3.5% 中性微对比
        色阶 + 细微阴影分层；左侧竖线降半透明。"""
        html = self.html
        start = html.index(".think-card {")
        css = html[start:html.index("}", start)]
        self.assertIn("border: none;", css)
        self.assertIn("background-color: rgba(31, 41, 55, 0.035)", css)
        self.assertIn("box-shadow: 0 1px 3px rgba(31, 41, 55, 0.07)", css)
        self.assertIn("border-left: 3px solid rgba(32, 49, 112, 0.16)", html)

    def test_swift_out_collapse_easing(self):
        """交互动效干脆顺滑：折叠过渡 swift-out（cubic-bezier(0.4,0,0.2,1)）。"""
        html = self.html
        start = html.index(".think-card.think-anim .think-card-body")
        css = html[start:html.index("}", start)]
        self.assertIn("transition: max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1)", css)


class SkeletonInstantTests(unittest.TestCase):
    """首字零等待骨架屏（2026-10-22 队长拍板，消灭 TTFT 干等）。

    诊断定案：指令链（不走模型）TTFB 仅 21ms，闲聊首帧 1.37s≈全部为模型
    首字延迟——旧前端在首个 think 帧才挂卡，把整个 TTFT 暴露成干等。
    修法：发送同一 tick 同步挂骨架卡（呼吸灯+占位线），首帧真文本无缝接管。
    """

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")
        cls.html = _read("index.html")

    def test_skeleton_mounted_synchronously_before_fetch(self):
        """乐观挂载在 fetch 之前（点击发送同一 tick，零异步等待）；流式状态
        变量一并提升到 fetch 之前（骨架卡挂载依赖这些闭包声明）。"""
        js = self.js
        mount_at = js.index("ensureThinkCard();   // ⚡ 乐观挂载骨架卡")
        fetch_at = js.index("return fetch('/api/chat/stream'")
        decl_at = js.index("let thinkCard = null;")
        self.assertLess(decl_at, mount_at)
        self.assertLess(mount_at, fetch_at)

    def test_skeleton_anatomy_built_in_ensure_think_card(self):
        """骨架解剖：呼吸态类 + 两根占位线（第二根短款）+ 骨架态标题。"""
        block = _extract_span(self.js, "function ensureThinkCard",
                              "function renderThinkProgressive")
        self.assertIn("thinkCard.classList.add('think-card-waiting')", block)
        self.assertIn("think-skeleton-line' + (sk ? ' think-skeleton-short' : '')", block)
        self.assertIn("title.textContent = '小橘正在思考…';", block)
        self.assertNotIn("思考过程（实时）", self.js)   # 旧实时标题退役（反锚）

    def test_seamless_takeover_on_first_think(self):
        """无缝接管：首段真文本到达——摘呼吸态+清骨架线后原卡填充
        （renderThinkProgressive 开头，先于分段渲染）；零二次挂载。"""
        block = _extract_span(self.js, "function renderThinkProgressive",
                              "function finalizeThinkCard")
        self.assertIn("if (thinkCard.classList.contains('think-card-waiting')) {", block)
        self.assertLess(block.index("classList.remove('think-card-waiting')"),
                        block.index("const segs = splitThinkStageLines(thinkAcc);"))
        self.assertIn("querySelectorAll('.think-skeleton-line')", block)
        self.assertIn("el.remove();", block)

    def test_instant_done_title_fallback(self):
        """指令单帧 done（骨架态直接转正、无耗时）：标题回落'思考过程'
        （与最终卡默认标题同口径），不得残留'小橘正在思考…'。"""
        block = _extract_span(self.js, "} else if (etype === 'done') {",
                              "} else if (etype === 'error') {")
        self.assertIn("secs === null ? '思考过程' : '已思考（用时 ' + secs + ' 秒）'", block)

    def test_skeleton_css_breath_and_shimmer(self):
        """CSS：卡头呼吸灯 thinkBreath + 占位线 shimmer + reduced-motion 降级；
        呼吸态选择器与 JS 挂的类名成对。"""
        html = self.html
        self.assertIn(".think-card.think-card-waiting .think-card-header {", html)
        self.assertIn("@keyframes thinkBreath", html)
        self.assertIn(".think-skeleton-line {", html)
        self.assertIn("@keyframes thinkSkeletonShimmer", html)
        self.assertIn(".think-skeleton-line.think-skeleton-short { width: 55%; }", html)
        self.assertIn("@media (prefers-reduced-motion: reduce) {", html)


if __name__ == "__main__":
    unittest.main()
