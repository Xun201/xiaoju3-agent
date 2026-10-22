# -*- coding: utf-8 -*-
"""直出思维流静态锚（2026-10-22 二轮拍板，替代流式思维卡折叠契约）。

契约（对标 DeepSeek，队长口述）：
- 废弃折叠卡：无箭头无折叠无二次点击；think 以灰色小号 🧠 标签+小字行直接
  外冒；answer 换行以正常黑字粗体续流；
- 严格分流：event: think 只进思维流块（renderThinkProgressive），event:
  answer 只进正文气泡（ensureAnswerEl）——绝不互相沾；
- 首字零等待：发送同一 tick 乐观挂骨架（呼吸标签+占位线），首帧无缝接管；
- 看门狗：首帧前 30s / 帧间 90s 无帧 → 中断就地报错（不转 legacy），UI 永不
  死锁；后端 180s 硬超时仍在内层；
- done：思维流块按净化全文定稿后原地移动进最终消息（thinkLiveEl 收养），
  标签换耗时；正文/工具栏/落盘走 appendBotMessage 单管线；
- 运行时防线：本轮新增 node 运行时烟雾（test_streamcard_runtime_smoke）——
  757f321 作用域雷（调用提出外层/声明留内层 → ReferenceError 假死）由
  node --check 与静态锚均无法查出，真跑烟雾是本类事故的唯一可靠门。
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


class DirectOutStructureTests(unittest.TestCase):
    """直出思维流骨架与构建器。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def _stream_block(self):
        return _extract_span(self.js, "function sendMessageStream",
                             "function sendMessageLegacy")

    def test_live_block_builder(self):
        """buildThinkLiveBlock：🧠 标签行 + 灰色思考行（前缀剥除），全
        textContent 注入免 XSS。"""
        js = self.js
        start = js.index("function buildThinkLiveBlock")
        body = js[start:js.index("function buildThinkFallbackBlock", start)]
        self.assertIn("className = 'think-live'", body)
        self.assertIn("className = 'think-live-label'", body)
        self.assertIn("textContent = '🧠 思考过程'", body)
        self.assertIn("className = 'think-live-line'", body)
        self.assertIn("splitThinkStageLines(thinkText)", body)

    def test_stream_skeleton_mounted_same_scope_and_tick(self):
        """首字零等待：ensureThinkCard 声明与乐观挂载调用同在 sendMessageStream
        顶层（757f321 作用域雷静态代理锚；运行时由烟雾测试真锁）；挂载先于
        fetch。"""
        block = self._stream_block()
        # 声明与调用同层（函数声明提升，顺序无关）——757f321 作用域雷的静态
        # 代理锚；真锁由 test_streamcard_runtime_smoke 运行时烟雾承担
        self.assertIn("function ensureThinkCard", block)
        call_at = block.index("ensureThinkCard();   // ⚡ 乐观挂载骨架（点击发送同一 tick，零等待）")
        fetch_at = block.index("return fetch('/api/chat/stream'")
        self.assertLess(call_at, fetch_at)
        self.assertIn("className = 'think-live'", block)
        self.assertIn("classList.add('think-live-waiting')", block)
        self.assertIn("think-skeleton-line' + (sk ? ' think-skeleton-short' : '')", block)
        self.assertIn("textContent = '🧠 小橘正在思考…'", block)

    def test_seamless_takeover(self):
        """无缝接管：首段真文本到达——摘呼吸态+清骨架线后原块填充（零二次
        挂载零跳变）。"""
        block = self._stream_block()
        start = block.index("function renderThinkProgressive")
        body = block[start:block.index("function finalizeThinkCard", start)]
        self.assertIn("if (thinkCard.classList.contains('think-live-waiting')) {", body)
        self.assertLess(body.index("classList.remove('think-live-waiting')"),
                        body.index("const segs = splitThinkStageLines(thinkAcc);"))
        self.assertIn("querySelectorAll('.think-skeleton-line')", body)
        self.assertIn("history.scrollTop = history.scrollHeight;", body)

    def test_retired_family_gone(self):
        """折叠卡家族整体退役（反锚）：打字机/折叠链/开合/旧构建器/
        think-pending/徽章行构建器全不存在。"""
        js = self.js
        for token in ("startThinkTypewriter", "scheduleThinkCollapse",
                      "animateThinkCollapse", "toggleThinkCard",
                      "buildThinkCardEl", "buildThinkLineEl",
                      "hideBubbleUntilThinkDone", "showBubbleNow",
                      "THINK_TYPE_MS", "THINK_COLLAPSE_DELAY_MS",
                      "think-pending", "think-collapsed", "animateThink",
                      "RENDERING_THINK_CARD"):
            self.assertNotIn(token, js)


class DoneAdoptionTests(unittest.TestCase):
    """done 直出收尾：收养进最终消息、标签换耗时、严格分流。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_done_keeps_live_block(self):
        """done 不拆块：finalizeThinkCard 定稿 + appendBotMessage thinkLiveEl
        通道收养；无任何折叠调度。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("} else if (etype === 'done') {")
        done_body = block[start:block.index("} else if (etype === 'error') {", start)]
        self.assertIn("finalizeThinkCard(parts.think,", done_body)
        self.assertIn("appendBotMessage(data.reply, data.source, text,", done_body)
        self.assertIn("adopted ? { thinkLiveEl: adopted } : null", done_body)
        self.assertNotIn("scheduleThinkCollapse", done_body)
        # 先挂最终气泡再撤 answerEl（换屏零空白）
        self.assertLess(done_body.index("const botMsg = appendBotMessage("),
                        done_body.rindex("if (answerEl && answerEl.parentNode)"))

    def test_finalize_sets_duration_label(self):
        """finalizeThinkCard：按 done 净化全文重渲+标签换耗时（A1 口径）；
        无耗时（指令单帧 done）回落'🧠 思考过程'。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("function finalizeThinkCard")
        body = block[start:block.index("function ensureAnswerEl", start)]
        self.assertIn("thinkAcc = finalThink;", body)
        self.assertIn("renderThinkProgressive();", body)
        self.assertIn("st.textContent = label;", body)
        done_at = block.index("} else if (etype === 'done') {")
        done_body = block[done_at:block.index("} else if (etype === 'error') {", done_at)]
        self.assertIn("secs === null ? '🧠 思考过程' : '🧠 已思考（用时 ' + secs + ' 秒）'", done_body)
        self.assertIn("已思考（用时 ' + secs + ' 秒）", self.js)

    def test_append_bot_message_adopts_live_block(self):
        """appendBotMessage 收养分支：thinkLiveEl 校验后原块移动（insertBefore
        自动摘离旧父），非收养照旧 buildThinkLiveBlock 新建。"""
        js = self.js
        start = js.index("const thinkLive = (options.thinkLiveEl && options.thinkLiveEl.classList &&")
        body = js[start:js.index("} catch (e) {", start)]
        self.assertIn("options.thinkLiveEl.classList.contains('think-live')", body)
        self.assertIn("? options.thinkLiveEl : buildThinkLiveBlock(thinkParts.think);", body)
        self.assertIn("parentEl.insertBefore(thinkLive, bubbleEl);", body)

    def test_thinking_state_label_kept(self):
        """思考中状态标签（首增量置位，A1 锚原文形态）。"""
        js = self.js
        self.assertIn("const st = thinkCard && thinkCard.querySelector('.think-live-label');", js)
        self.assertIn("st.textContent = '🧠 思考中…';", js)

    def test_no_think_reply_drops_process_block(self):
        """边界：最终 reply 无 <think>（理论边角）→旧口径不保留过程块。"""
        block = _extract_span(self.js, "function sendMessageStream",
                              "function sendMessageLegacy")
        start = block.index("} else if (etype === 'done') {")
        done_body = block[start:block.index("} else if (etype === 'error') {", start)]
        self.assertIn("if (thinkCard && thinkCard.parentNode) thinkCard.parentNode.removeChild(thinkCard);",
                      done_body)


class StrictSeparationTests(unittest.TestCase):
    """think/answer 严格分流（队长拍板红线）。"""

    def test_think_never_touches_answer_and_vice_versa(self):
        js = _read("console.js")
        start = js.index("function handleEvent")
        end = js.index("function pump", start)
        body = js[start:end]
        think_block = body[body.index("etype === 'think'"):body.index("etype === 'tool'")]
        answer_block = body[body.index("etype === 'answer'"):body.index("} else if (etype === 'done')")]
        # think 分支只进思维流块
        self.assertIn("thinkAcc += (data.delta || '')", think_block)
        self.assertIn("renderThinkProgressive()", think_block)
        self.assertNotIn("answerAcc", think_block)
        self.assertNotIn("ensureAnswerEl", think_block)
        # answer 分支只进正文气泡
        self.assertIn("answerAcc += (data.delta || '')", answer_block)
        self.assertIn("ensureAnswerEl()", answer_block)
        self.assertNotIn("thinkAcc", answer_block)
        self.assertNotIn("renderThinkProgressive()", answer_block)

    def test_answer_bold_black_streaming(self):
        """answer 正常黑字粗体：流式气泡与最终消息同一 CSS 口径。"""
        html = _read("index.html")
        self.assertIn(".message.bot-message .bubble-content {", html)
        self.assertIn("font-weight: 600;", html)


class WatchdogTests(unittest.TestCase):
    """SSE 超时中断保护（救火拍板）：任何底层卡死 UI 都不死锁。"""

    def test_first_frame_and_idle_watchdog(self):
        """首帧前 30s / 帧间 90s 无帧 → fireWatchdog 中断；handleEvent 每帧
        喂狗。"""
        js = _read("console.js")
        self.assertIn("let watchdog = setTimeout(fireWatchdog, 30000);", js)
        self.assertIn("watchdog = setTimeout(fireWatchdog, 90000);", js)
        self.assertIn("patWatchdog();   // 每帧喂狗", js)
        block = _extract_span(js, "function sendMessageStream",
                              "function sendMessageLegacy")
        catch_at = block.index(".catch(function (err) {")
        catch_body = block[catch_at:]
        self.assertIn("clearTimeout(watchdog);", catch_body)

    def test_watchdog_error_inline_no_legacy(self):
        """看门狗中断就地报错（红字提示+统一工具栏），不转 legacy（同源后端
        会同样卡死）；普通错误仍转 legacy 重答。"""
        js = _read("console.js")
        block = _extract_span(js, "function sendMessageStream",
                              "function sendMessageLegacy")
        catch_body = block[block.index(".catch(function (err) {"):]
        self.assertIn("if (watchdogFired) {", catch_body)
        self.assertIn("mountSystemToolbar(errMsg)", catch_body)
        self.assertLess(catch_body.index("if (watchdogFired) {"),
                        catch_body.rindex("throw err;"))

    def test_backend_hard_timeout_untouched(self):
        """后端 180s 硬超时防线不动（看门狗在其内层，双保险）。"""
        py = _read("xiaoju3_dashboard.py")
        self.assertIn("_STREAM_HARD_TIMEOUT = 180", py)


class LegacyAndHistoryUntouchedTests(unittest.TestCase):
    """零回退哨兵：非流式路径与既有契约不受本轮影响。"""

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
        self.assertIn("function splitThinkBlock", js)     # 切分管线未动
        self.assertIn("function buildThinkFallbackBlock", js)  # 深色兜底未动

    def test_history_stagger_only_non_streaming(self):
        """错开淡入仅历史批渲染（loadHistory 挂 .msg-enter+延时），流式路径
        零此类。"""
        js = self.js
        hist = js[js.index("function loadHistory"):js.index("// ==================== 4.")]
        self.assertIn("msg-enter", hist)
        self.assertIn("animationDelay = Math.min(idx * 45, 400) + 'ms';", hist)
        block = _extract_span(js, "function sendMessageStream",
                              "function sendMessageLegacy")
        self.assertNotIn("msg-enter", block)


class UiMicroPolishTests(unittest.TestCase):
    """UI 质感微操四件（2026-10-22 队长口述）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")

    def test_concentric_radius(self):
        """同心圆角：内层（徽章/工具按钮）=外层卡片圆角-内边距（calc 派生）。"""
        html = self.html
        self.assertIn("--radius-inner: calc(var(--radius-card) - 6px);", html)
        self.assertGreaterEqual(html.count("border-radius: var(--radius-inner);"), 2)  # 徽章+工具按钮+同族

    def test_layered_soft_shadow(self):
        """多层柔和阴影：--shadow-card 三层叠加（细锐+中景+大模糊光感），
        双主题各一份。"""
        html = self.html
        self.assertEqual(html.count("0 10px 28px rgba("), 2)
        self.assertIn("0 1px 2px rgba(31, 41, 55, 0.05), 0 2px 6px rgba(31, 41, 55, 0.04)",
                      html)

    def test_balance_and_pretty_wrap(self):
        """标题平衡换行 balance / 正文 pretty（防末行孤字）。"""
        html = self.html
        self.assertIn("text-wrap: balance;", html)
        self.assertIn("text-wrap: pretty;", html)

    def test_reduced_motion_fallback(self):
        """动效降级：prefers-reduced-motion 下呼吸/占位线动画全关。"""
        html = self.html
        start = html.index("@media (prefers-reduced-motion: reduce) {")
        block = html[start:html.index("}", start)]
        self.assertIn("animation: none", block)


if __name__ == "__main__":
    unittest.main()
