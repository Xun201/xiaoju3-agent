# -*- coding: utf-8 -*-
r"""console.js 前端体验优化（并行组 B）单元测试（全部离线，静态断言为主）。

覆盖三块改动（只动 console.js，index.html 零改动）：
- 任务 4 TTS 音色选择：回退链 localStorage(xiaoju3_tts_voice) → /api/status
  下发的 tts_voice（localStorage 为空时采用并写回 localStorage）→
  getVoices() 首个中文女声（lang 以 zh 开头且 name 含女性特征词）→
  首个 zh 音色 → 引擎默认音色；聊天头部纯 JS 动态构建音色下拉菜单
  （zh 过滤、选中项回显、切换写回 localStorage、voiceschanged 异步重建）；
- 任务 5 系统消息工具栏：首条系统欢迎语与系统提示类消息（清空历史后的
  欢迎语、请求失败提示）挂统一工具栏——复制/朗读/点赞/点踩行为与
  普通 AI 回复一致（正文包进 .bubble-content，全局工具函数零改动复用；
  已有 .msg-tools 的 AI 回复经 guard 跳过不重复挂载）；
- 任务 7 TTS 忽略 emoji：朗读前正则剔除 emoji（含修饰符与 ZWJ 序列，
  unicode 范围 \u{1F300}-\u{1FAFF}、\u2600-\u27BF 等），保留标点作为
  自然停顿，剔除后连续空白折叠为一个空格。

测试方式：静态断言（test_dashboard.FrontendStaticTests 风格）+ 用源码中
同一个 emoji 正则翻译为 Python 语义复跑剔除行为 + node 实跑校验正则
字面量合法性与 JS 侧剔除结果（无 node 环境自动跳过）。另附零回退
哨兵断言：思维链（splitThinkBlock / 打字机 / 折叠卡片 / RAW_REPLY 等
诊断日志）与 CQ 表情渲染在本轮改动中不受影响。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 任务 4：TTS 音色选择（回退链 + 下拉菜单）
# ---------------------------------------------------------------------------

class TTSVoiceSelectionTests(unittest.TestCase):
    """朗读音色回退链与音色下拉菜单（console.js 静态断言）。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def test_localstorage_key_present(self):
        """localStorage 记忆键固定为 xiaoju3_tts_voice（const 声明）。"""
        self.assertIn("const TTS_VOICE_KEY = 'xiaoju3_tts_voice'", self.console_js)

    def test_female_hints_present(self):
        """女性特征词表含任务指定的五个词：晓晓/小艺/悦/female/Xiaoxiao。"""
        js = self.console_js
        start = js.index("const TTS_FEMALE_HINTS")
        block = js[start:js.index("];", start)]
        for hint in ("晓晓", "小艺", "悦", "female", "Xiaoxiao"):
            self.assertIn("'" + hint + "'", block)

    def test_zh_voice_filter(self):
        """zh 音色过滤：lang 以 zh 开头（/^zh/i，兼容 zh-CN / zh-Hans-CN）。"""
        self.assertIn("/^zh/i.test(String(v.lang || ''))", self.console_js)

    def test_fallback_chain_order(self):
        """回退链顺序锁定：localStorage → /api/status tts_voice →
        首个中文女声（isFemaleZhVoice）→ 首个 zh 音色（zhVoices[0]）→
        无 zh 音色返回 null 交给引擎默认音色。"""
        js = self.console_js
        start = js.index("function pickTTSVoice")
        end = js.index("function adoptBackendTTSVoice", start)
        body = js[start:end]
        i_stored = body.index("getStoredTTSVoiceName()")
        i_backend = body.index("backendTTSVoice")
        i_female = body.index("isFemaleZhVoice")
        i_first = body.index("zhVoices[0]")
        self.assertLess(i_stored, i_backend)
        self.assertLess(i_backend, i_female)
        self.assertLess(i_female, i_first)
        # 首选与女声都落空：显式返回 null（引擎默认音色），绝不抛错
        self.assertIn("return null", body)
        # 指定音色在 zh 列表找不到时，再在全部音色里找（尊重显式配置）
        self.assertIn("all.find(v => v.name === wanted)", body)

    def test_status_tts_voice_adopted_and_written_back(self):
        """/api/status 契约字段 tts_voice：fetchStatus 消费；localStorage
        为空且字段非空时采用并写回 localStorage（已记忆则不接管）。"""
        js = self.console_js
        self.assertIn("adoptBackendTTSVoice(d.tts_voice)", js)
        start = js.index("function adoptBackendTTSVoice")
        end = js.index("let ttsVoiceSelect", start)
        body = js[start:end]
        self.assertIn("typeof val !== 'string'", body)        # 后端未升级时容错
        self.assertIn("!getStoredTTSVoiceName()", body)       # 仅 localStorage 为空时
        self.assertIn("localStorage.setItem(TTS_VOICE_KEY, val)", body)  # 写回

    def test_voice_selector_dynamic_build(self):
        """音色下拉纯 JS 动态构建（index.html 零改动）：挂聊天头部工具区
        .header-actions，createElement('select')，只列 zh 音色 + 默认项，
        切换写 localStorage，选中项按回退链回显。"""
        js = self.console_js
        start = js.index("function refreshVoiceSelector")
        end = js.index("if (window.speechSynthesis)", start)
        body = js[start:end]
        self.assertIn(".chat-header .header-actions", body)   # 挂载点：聊天头部工具区
        self.assertIn("createElement('select')", body)        # 纯 JS 构建
        self.assertIn("listZhVoices()", body)                 # 只列 zh 音色
        self.assertIn("addEventListener('change'", body)      # 切换监听
        self.assertIn("localStorage.setItem(TTS_VOICE_KEY, name)", body)
        self.assertIn("localStorage.removeItem(TTS_VOICE_KEY)", body)  # 默认项清除记忆
        self.assertIn("pickTTSVoice()", body)                 # 选中项回显按回退链
        # 不经 getElementById 引用新节点（index.html 无此 id，双向一致）
        self.assertNotIn("getElementById('tts-voice-select')", js)
        self.assertNotIn("tts-voice-select", self.index_html)

    def test_voiceschanged_async_handled(self):
        """音色列表异步到达：voiceschanged 事件重建下拉
        （addEventListener 与 onvoiceschanged 双保险）。"""
        js = self.console_js
        self.assertIn("addEventListener('voiceschanged', refreshVoiceSelector)", js)
        self.assertIn("onvoiceschanged = refreshVoiceSelector", js)

    def test_play_msg_uses_voice_chain(self):
        """朗读接线：playMsg 按回退链取音色并挂到 utterance；无音色时不设
        utter.voice（引擎默认兜底），保留 cancel 清队列防连点。"""
        js = self.console_js
        start = js.index("window.playMsg")
        end = js.index("window.toggleLike", start)
        body = js[start:end]
        self.assertIn("speechSynthesis.cancel()", body)       # 清队列防连点
        self.assertIn("pickTTSVoice()", body)
        self.assertIn("if (voice) utter.voice = voice;", body)


# ---------------------------------------------------------------------------
# 任务 5：系统消息统一工具栏
# ---------------------------------------------------------------------------

class SystemMessageToolbarTests(unittest.TestCase):
    """首条系统欢迎语与系统提示类消息的统一工具栏（静态断言）。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def test_mount_guard_and_bubble_restructure(self):
        """挂载函数：已有 .msg-tools 直接跳过（appendBotMessage 产物不重复
        挂）；正文迁入 .bubble-content（与 AI 回复气泡结构同构，全局工具
        函数 copyText/playMsg 取文本零改动复用）。"""
        js = self.console_js
        start = js.index("function mountSystemToolbar")
        end = js.index("document.querySelectorAll", start)
        body = js[start:end]
        self.assertIn("querySelector('.msg-tools')", body)         # 防重复挂载 guard
        self.assertIn("return;", body)                             # guard 早退
        self.assertIn("bubble.className = 'bubble-content'", body) # 同构气泡容器
        self.assertIn("buildSystemMsgTools()", body)

    def test_system_toolbar_buttons_match_ai_replies(self):
        """统一工具栏四键与普通 AI 回复同口径：复制 copyText / 朗读 playMsg /
        点赞 toggleLike / 点踩 toggleDislike（同一全局函数、同一类名）。"""
        js = self.console_js
        start = js.index("function buildSystemMsgTools")
        end = js.index("function mountSystemToolbar", start)
        body = js[start:end]
        self.assertIn('onclick="copyText(this)"', body)
        self.assertIn('onclick="playMsg(this)"', body)
        self.assertIn('onclick="toggleLike(this)"', body)
        self.assertIn('onclick="toggleDislike(this)"', body)
        self.assertIn('class="tool-btn like-btn"', body)
        self.assertIn('class="tool-btn dislike-btn"', body)
        self.assertIn("className = 'msg-tools'", body)   # 复用同一套样式类

    def test_static_welcome_mounted_on_load(self):
        """首条系统欢迎语（index.html 静态节点）：console.js 加载时扫描
        #chat-history 既有 bot-message 气泡统一挂工具栏。"""
        js = self.console_js
        self.assertIn("querySelectorAll('#chat-history .message.bot-message')", js)
        self.assertIn(".forEach(mountSystemToolbar)", js)
        # 欢迎语静态节点仍在 index.html（本任务未改 index.html）
        self.assertIn("你好！我是小橘3号，很高兴为你服务喵~", self.index_html)

    def test_clear_history_rebuilds_welcome_with_toolbar(self):
        """清空历史后的欢迎语：DOM 重建（不再是 innerHTML 字符串整体替换）
        并挂统一工具栏，与首条系统欢迎语同口径；欢迎语文案不变。"""
        js = self.console_js
        start = js.index("id='clear-history'") if "id='clear-history'" in js \
            else js.index("clear-history")
        end = js.index("==================== 7.", start)
        body = js[start:end]
        self.assertIn("createElement('div')", body)
        self.assertIn("className = 'message bot-message'", body)
        self.assertIn("你好！我是小橘3号，很高兴为你服务喵~", body)
        self.assertIn("mountSystemToolbar(welcome)", body)
        self.assertIn("appendChild(welcome)", body)

    def test_error_message_gets_toolbar(self):
        """系统提示类消息（请求失败提示）同样挂统一工具栏。"""
        js = self.console_js
        self.assertIn("mountSystemToolbar(errMsg)", js)

    def test_welcome_not_duplicated_by_append_bot(self):
        """appendBotMessage 自建 .msg-tools 的 AI 回复与系统消息互不干扰：
        appendBotMessage 工具栏模板保留（class=\"msg-tools\"），挂载 guard
        依据 .msg-tools 早退，历史回放/实时回复不会被二次挂工具栏。"""
        js = self.console_js
        self.assertIn('class="msg-tools"', js)
        self.assertLess(js.index("function mountSystemToolbar"),
                        js.index("function appendBotMessage"))


# ---------------------------------------------------------------------------
# 任务 7：TTS 忽略 emoji（朗读前剔除）
# ---------------------------------------------------------------------------

class TTSEmojiStripTests(unittest.TestCase):
    """朗读前 emoji 剔除正则与文本预处理（静态断言 + Python 复跑 + node 实跑）。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")

    def test_emoji_regex_ranges_present(self):
        r"""剔除正则含任务指定 unicode 范围：\u{1F300}-\u{1FAFF}（emoji 主体，
        肤色修饰符 1F3FB-1F3FF 在内）、\u2600-\u27BF（杂项+装饰）、ZWJ
        （\u200D）、变体选择符（\uFE00-\uFE0F）、键帽（\u20E3），/gu 全局
        + unicode 标志。"""
        js = self.console_js
        start = js.index("const TTS_EMOJI_RE")
        line_end = js.index(";", start)
        block = js[start:line_end]
        for token in (r"\u{1F300}-\u{1FAFF}",   # emoji 主体区（含修饰符）
                      r"\u{1F000}-\u{1F2FF}",   # 牌类/括号/旗帜扩展
                      r"\u2600-\u27BF",         # 杂项符号 + 装饰符号
                      r"\uFE00-\uFE0F",         # 变体选择符
                      r"\u200D",                # ZWJ 零宽连接符（组合序列）
                      r"\u20E3",                # 键帽组合符
                      "/gu"):                   # 全局 + unicode 标志
            self.assertIn(token, block)

    def test_strip_collapses_whitespace_keeps_punctuation(self):
        """剔除后连续空白折叠为一个空格（\\s+ → ' ' + trim）；标点不在
        emoji 区间内，保留作自然停顿。"""
        js = self.console_js
        start = js.index("function stripEmojiForTTS")
        end = js.index("// 朗读音色回退链", start)
        body = js[start:end]
        self.assertIn(".replace(TTS_EMOJI_RE, '')", body)
        self.assertIn(r".replace(/\s+/g, ' ')", body)
        self.assertIn(".trim()", body)

    @classmethod
    def _python_emoji_re(cls):
        """提取源码中的 TTS_EMOJI_RE 正则字面量，把 JS 专有 \\u{XXXX} 语法
        翻译为 Python 的 \\UXXXXXXXX 后编译（其余为公共子集，可直接复跑）。"""
        js = cls.console_js
        m = re.search(r"TTS_EMOJI_RE\s*=\s*/(.+?)/gu;", js)
        assert m, "console.js 缺少 TTS_EMOJI_RE 正则"
        py_src = re.sub(r"\\u\{([0-9A-Fa-f]+)\}",
                        lambda mm: "\\U%08x" % int(mm.group(1), 16),
                        m.group(1))
        return re.compile(py_src)

    def _python_strip(self, text):
        """按 JS 侧 stripEmojiForTTS 同一管线（剔 emoji → 折叠空白 → trim）
        在 Python 侧复跑。"""
        stripped = self._python_emoji_re().sub("", text)
        return re.sub(r"\s+", " ", stripped).strip()

    def test_strip_behavior_python_replay(self):
        """剔除行为（源码同一正则 Python 复跑锁定）：普通 emoji/肤色修饰符/
        ZWJ 家庭序列/键帽序号/旗帜/警示符号全部剔除；标点与数字保留；
        连续空白折叠为一个空格。"""
        cases = [
            ("你好😊，今天开心吗？", "你好，今天开心吗？"),   # 标点保留
            ("好的👍🏻收到", "好的收到"),                     # 肤色修饰符随主体剔除
            ("👨‍👩‍👧 全家福", "全家福"),                        # ZWJ 序列整体剔除
            ("第1️⃣名", "第1名"),                              # 键帽剔除、数字保留
            ("a 😊 😊 b", "a b"),                             # 连续空白折叠为一个空格
            ("🇨🇳中国加油", "中国加油"),                       # 地区指示符（旗帜）
            ("⚠️ 注意安全", "注意安全"),                       # 警示符号 + 变体选择符
            ("完成！💯💯", "完成！"),                          # 连续 emoji 剔除、标点保留
        ]
        for raw, expected in cases:
            self.assertEqual(self._python_strip(raw), expected, msg=raw)

    def test_strip_behavior_node_live_run(self):
        """node 实跑（环境无 node 时跳过，上一测试的复跑断言仍全量生效）：
        提取源码真实 TTS_EMOJI_RE + stripEmojiForTTS 喂给 node 运行——同时
        验证正则字面量在 JS 引擎下合法可编译（非法正则会在页面加载时抛错
        拖垮整个 console.js，此处提前现形）。纯计算子进程（stdin 管道、
        无网络、无临时文件）。"""
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过 JS 实跑（静态与复跑断言已覆盖）")
        js = self.console_js
        start = js.index("const TTS_EMOJI_RE")
        end = js.index("const TTS_VOICE_KEY")
        chunk = js[start:end]
        script = (chunk + "\n"
                  "var cases = [\n"
                  "  ['你好😊，今天开心吗？', '你好，今天开心吗？'],\n"
                  "  ['好的👍🏻收到', '好的收到'],\n"
                  "  ['👨‍👩‍👧 全家福', '全家福'],\n"
                  "  ['第1️⃣名', '第1名'],\n"
                  "  ['a 😊 😊 b', 'a b'],\n"
                  "  ['🇨🇳中国加油', '中国加油'],\n"
                  "  ['⚠️ 注意安全', '注意安全'],\n"
                  "  ['完成！💯💯', '完成！'],\n"
                  "];\n"
                  "var bad = cases.filter(function (c) "
                  "{ return stripEmojiForTTS(c[0]) !== c[1]; })\n"
                  "  .map(function (c) { return c[0] + ' => ' + stripEmojiForTTS(c[0]); });\n"
                  "console.log(JSON.stringify({ ok: bad.length === 0, bad: bad }));\n")
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        out = json.loads(proc.stdout.decode("utf-8"))
        self.assertTrue(out["ok"], msg=str(out["bad"]))

    def test_strip_applied_only_to_speech(self):
        """剔除只作用于朗读链路（playMsg），复制/转发仍保留原文 emoji。"""
        js = self.console_js
        self.assertEqual(js.count("stripEmojiForTTS("), 2,
                         msg="stripEmojiForTTS 应只出现在定义与 playMsg 两处")
        play_start = js.index("window.playMsg")
        self.assertLess(play_start, js.index("stripEmojiForTTS(text)", play_start))


# ---------------------------------------------------------------------------
# 零回退哨兵：思维链 / CQ 表情 / 诊断日志不受本轮改动影响
# ---------------------------------------------------------------------------

class FrontendNoRegressionSentinelTests(unittest.TestCase):
    """并行改动零回退哨兵（打字机/折叠卡片/CQ 表情/诊断日志/splitThinkBlock）。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")

    def test_cot_pipeline_untouched(self):
        js = self.console_js
        self.assertIn("function splitThinkBlock", js)
        self.assertIn("startThinkTypewriter", js)
        self.assertIn("syncThinkCard", js)
        self.assertIn("if (thinkParts.think !== null)", js)

    def test_diagnostic_logs_untouched(self):
        js = self.console_js
        self.assertIn('console.log("RAW_REPLY:", res.data.reply)', js)
        self.assertIn('console.log("PARSED_THINK:"', js)
        self.assertIn('console.log("RENDERING_THINK_CARD...")', js)

    def test_cq_face_render_untouched(self):
        js = self.console_js
        self.assertIn("CQ_FACE_EMOJI", js)
        self.assertIn("renderCQFace(escapeHtml(text))", js)

    def test_no_alert_placeholder(self):
        """工具栏/音色改动不得 reintroduce alert 占位（界面 §4.2 口径）。"""
        self.assertNotIn("alert(", self.console_js)


if __name__ == "__main__":
    unittest.main()
