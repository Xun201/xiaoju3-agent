# -*- coding: utf-8 -*-
"""前端体验三件套单元测试（S4，全部离线；独立文件，不动 test_dashboard.py）。

覆盖（并行组 S4 任务 5/6/7，只动 console.js 与 index.html）：
- 任务 5 自动朗读开关：聊天头部工具区新增 🔊/🔇 开关按钮（与既有 🔔/🔕
  音效开关视觉同款但相互独立——音效≠朗读，键名区分：音效 xiaoju3_sound
  在 desktop-pet.js，朗读 xiaoju3_autotts）；开启后 AI 每次回复自动朗读
  （sendMessage 实时回复与 refreshMsg 重新生成共用 speakMessageEl 链路 =
  playMsg 既有逻辑：emoji 剔除 → Edge-TTS 优先 → 浏览器 speechSynthesis
  自动降级）；关闭时仅手动点播放朗读；状态 localStorage 记忆、刷新保持、
  默认关闭（getItem === '1' 才算开、关闭清键）；
- 任务 6 CoT 逐行展示（DeepSeek 风格）：思维链卡片展开时 [思考]/[计划]/
  [行动] 每段单独成行、按顺序逐个淡入（每行间隔约 200ms
  THINK_LINE_STEP_MS），不再整段一次性弹出；保留折叠功能（打完/播完自动
  折叠 + 点击标题展开/收起零回退）；展开态内容完整可见、可滚动
  （.think-card-body max-height + overflow-y: auto）；样式：左侧竖线
  （border-left）+ 灰色文字（#6b7280）+ 淡蓝色阶段标签小徽章（#3b82f6
  on #eff6ff）；无阶段标记的思考文本降级沿用原逐字打字机（THINK_TYPE_MS
  口径零回退，既有断言零回退）；历史回放（animateThink=false）不打字；
- 任务 7 缩成加速球：聊天头部 ⌄ 最小化按钮，点击后整个控制台收成直径
  60px 圆形小挂件（右下角悬浮、小橘半身像 /assets/pet/normal_half.png、
  橘色 Q 版
  圆形边框）；点击小球展开回完整控制台；小球支持拖拽移动（拖拽阈值与桌宠
  同口径：位移平方>9），位置存 localStorage（xiaoju3_ball_pos）刷新保持、
  resize 重钳制；实现 = body 根容器 class 切换（.xiaoju3-minimized）+ CSS
  （控制台主体 display:none、球体 display:block），互切幂等、球体挂载点
  缺失静默跳过（无 JS 报错路径）；与本地桌宠（desktop-pet.js）不同功能、
  两者共存——desktop-pet.js 零改动（哨兵断言）。

测试方式：静态断言（test_dashboard.FrontendStaticTests 风格）+ node 实跑
（提取真实源码片段喂桩：splitThinkStageLines 分段行为、加速球互切幂等与
位置钳制、node --check 语法门；无 node 环境自动跳过，静态断言仍全量生效）。
"""

import json
import os
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


def _node_available():
    return shutil.which("node") is not None


def js_index_of(source, token, start=0):
    """str.index 的模块级薄封装（保持用例主体简洁）。"""
    return source.index(token, start)


# ---------------------------------------------------------------------------
# 任务 5：自动朗读开关（🔊/🔇，localStorage xiaoju3_autotts，默认关闭）
# ---------------------------------------------------------------------------

class AutoTTSFrontendTests(unittest.TestCase):
    """自动朗读开关静态断言：独立键名、默认关闭、自动链路复用 playMsg 逻辑。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _header_actions(self):
        """提取 index.html 聊天头部工具区（.header-actions）内部片段。"""
        html = self.index_html
        start = html.index('<span class="header-actions">')
        return html[start:html.index("</span>", start)]

    # ---------- 开关按钮（与音效开关同款视觉、相互独立） ----------

    def test_toggle_button_in_header_actions(self):
        """index.html 聊天头部工具区新增自动朗读按钮：🔊/🔇、header-btn 同款
        样式、初始 🔇（默认关闭态与 console.js 回显一致）。"""
        actions = self._header_actions()
        self.assertIn('id="auto-tts-toggle"', actions)
        self.assertIn("class=\"header-btn\"", actions)
        self.assertIn("🔇", actions)          # 默认关闭图标
        js = self.console_js
        self.assertIn("autoTTSEnabled() ? '🔊' : '🔇'", js)   # 开/关双态回显
        self.assertIn("refreshAutoTTSBtn();", js)              # 载入即回显（刷新保持）

    def test_independent_from_sound_toggle(self):
        """与音效开关独立（音效≠朗读）：🔔/🔕 音效按钮与逻辑零改动并存，
        localStorage 键名区分（autotts / tts_voice），不共用。"""
        js = self.console_js
        self.assertIn("window.xiaoju3Sound.enabled() ? '🔔' : '🔕'", js)  # 音效开关原样
        self.assertIn("getElementById('sound-toggle')", js)
        keys = ("xiaoju3_autotts", "xiaoju3_tts_voice")
        for key in keys:
            self.assertIn(key, js)
        self.assertNotEqual(keys[0], keys[1])

    # ---------- localStorage 状态记忆（默认关闭、刷新保持） ----------

    def test_localstorage_key_default_off(self):
        """状态记忆：const 键 xiaoju3_autotts；getItem === '1' 才算开（缺键/
        损坏一律关闭=默认关闭）；关闭清键不残留；读写包 try/catch（localStorage
        不可用时不崩、仅本次会话生效）。"""
        js = self.console_js
        self.assertIn("const AUTO_TTS_KEY = 'xiaoju3_autotts'", js)
        self.assertIn("localStorage.getItem(AUTO_TTS_KEY) === '1'", js)
        start = js.index("function setAutoTTS")
        body = js[start:js.index("const autoTTSBtn", start)]
        self.assertIn("localStorage.setItem(AUTO_TTS_KEY, '1')", body)
        self.assertIn("localStorage.removeItem(AUTO_TTS_KEY)", body)   # 关闭清键
        self.assertIn("try {", body)
        self.assertIn("} catch (e)", body)

    # ---------- 自动朗读链路（复用 playMsg 既有 Edge-TTS 逻辑） ----------

    def test_auto_speak_wired_into_send_message(self):
        """sendMessage 成功分支：AI 回复到达且开关开启时自动播报（捕获
        appendBotMessage 返回的消息元素交给 speakMessageEl）。"""
        js = self.console_js
        start = js.index("window.sendMessage")
        end = js.index("==================== 5.", start)
        body = js[start:end]
        self.assertIn("const botMsg = appendBotMessage(res.data.reply, res.data.source, text)",
                      body)
        self.assertIn("if (autoTTSEnabled()) speakMessageEl(botMsg);", body)

    def test_auto_speak_wired_into_refresh_msg(self):
        """refreshMsg：重新生成的回复同样是 AI 回复，开关开启时一并自动播报。"""
        js = self.console_js
        start = js.index("window.refreshMsg")
        end = js.index("window.forwardMsg", start)
        body = js[start:end]
        self.assertIn("if (autoTTSEnabled()) speakMessageEl(msgEl);", body)

    def test_speak_message_el_shares_playmsg_pipeline(self):
        """共用链路（playMsg 既有逻辑零回退）：playMsg 转发 speakMessageEl；
        	speakMessageEl 含 emoji 剔除（stripEmojiForTTS 用法仅定义+链路一处，
        test_cot_frontend 口径锁定）、Edge 优先（resolveTTSMode / plan.mode
        判定 / requestEdgeTTS 携 voice）与浏览器自动降级（.catch 回退链）；
        关闭时仅手动点播放朗读（自动链路全部经 autoTTSEnabled() 守卫）。"""
        js = self.console_js
        self.assertEqual(js.count("if (autoTTSEnabled()) speakMessageEl("), 2,
                         msg="自动播报仅 sendMessage/refreshMsg 两处接线")
        start = js.index("window.playMsg = function")
        end = js.index("const EDGE_TTS_TIMEOUT_MS", start)
        body = js[start:end]
        self.assertIn("speakMessageEl(el)", body)                       # playMsg 转发
        self.assertIn("stripEmojiForTTS(text)", body)                   # emoji 剔除
        self.assertIn("resolveTTSMode()", body)                         # 链路解析
        self.assertIn("plan.mode !== 'edge'", body)                     # Edge 判定
        self.assertIn("requestEdgeTTS(speakText, plan.voice)", body)    # Edge 合成
        self.assertIn(".catch(() => speakWithBrowserTTS(speakText))", body)  # 自动降级


# ---------------------------------------------------------------------------
# 任务 6：CoT 逐行展示（DeepSeek 风格：单独成行、逐个淡入、约 200ms）
# ---------------------------------------------------------------------------

class ThinkLineRevealTests(unittest.TestCase):
    """思维链逐行淡入静态断言：分段、节奏、折叠保留、降级零回退。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _typewriter_body(self):
        js = self.console_js
        start = js.index("function startThinkTypewriter")
        return js[start:js.index("window.toggleThinkCard", start)]

    def test_all_lines_render_at_once_then_collapsed(self):
        """2026-10-01 用户口径升级：一次性渲染全部行（同帧插入，非逐行
        setTimeout 错峰）；渲染完延迟折叠、正文延迟显示（DeepSeek 节奏）。"""
        body = self._typewriter_body()
        # 一次性渲染：全部行同帧插入（函数式回调形态），无逐行 setTimeout 链
        self.assertIn("segs.forEach(function (seg) { body.appendChild(buildThinkLineEl(seg)); });", body)
        self.assertNotIn("THINK_LINE_STEP_MS", body)   # 逐行链已废止
        # 折叠节奏：调度调用在打字函数内；延迟常量与 300ms 过渡 CSS 在
        # console.js 调度函数与 index.html 样式（_typewriter_body 切片之外）
        self.assertIn("scheduleThinkCollapse(card, msgEl);", body)
        self.assertIn("const THINK_COLLAPSE_DELAY_MS = 1500;", self.console_js)
        self.assertIn("maxHeight = body.clientHeight", self.console_js)
        self.assertIn("0.3s ease", self.index_html)

    def test_stage_split_function_present(self):
        """分段函数：[思考]/[计划]/[行动] 半角方括号阶段标记起新段（与后端
        协议同口径），buildThinkLineEl 构建单行段元素。"""
        js = self.console_js
        self.assertIn("function splitThinkStageLines", js)
        self.assertIn("function buildThinkLineEl", js)
        self.assertIn(r"/^\[(思考|计划|行动)\]/", js)

    def test_lines_rendered_at_once_textcontent_only(self):
        """一次性渲染主链路：先清空正文（强制兜底卡片预填场景），全部段同帧
        插入（淡入动画由 CSS 承担）；阶段标签与正文全部 textContent 注入免
        XSS；渲染完延迟折叠（点击标题可再展开，折叠零回退）。"""
        body = self._typewriter_body()
        self.assertIn("body.textContent = '';", body)              # 清空后一次性插入
        self.assertIn("body.appendChild(buildThinkLineEl(seg))", body)
        # 折叠调度存在即可（渲染为同步同帧完成，1.5s 定时器随后触发折叠动画）
        self.assertIn("scheduleThinkCollapse(card, msgEl);", body)
        self.assertIn("segs.forEach(function (seg)", body)
        # 阶段标签/正文构建位于 buildThinkLineEl：textContent 注入免 XSS
        el_start = js_index_of(self.console_js, "function buildThinkLineEl")
        el_body = self.console_js[el_start:
                                  js_index_of(self.console_js, "function startThinkTypewriter",
                                              el_start)]
        self.assertIn("tag.textContent = seg.tag", el_body)
        self.assertIn("text.textContent = seg.text", el_body)
        self.assertIn("className = 'think-line'", el_body)
        self.assertIn("className = 'think-line-tag'", el_body)
        self.assertIn("className = 'think-line-text'", el_body)
        # 卡片被移除即停（清空历史等场景不悬挂计时器；R2 改造后为
        # clearInterval + return 复合形态）
        self.assertIn("if (!card.isConnected)", body)

    def test_collapse_and_history_replay_zero_regression(self):
        """零回退哨兵：历史回放不打字（完整填充+保持折叠）、无阶段标记降级
        沿用原逐字打字机（THINK_TYPE_MS 口径）、点击标题展开/收起保留。"""
        js = self.console_js
        body = self._typewriter_body()
        self.assertIn("if (!animate || !text) {", body)
        self.assertIn("body.textContent = text;", body)              # 历史回放整段填充
        self.assertIn("const THINK_TYPE_MS = 15;", js)               # 逐字打字间隔保留
        self.assertIn("body.textContent = text.slice(0, shown)", body)  # 打字机降级
        self.assertIn("window.toggleThinkCard", js)                  # 点击展开/收起
        self.assertIn("classList.toggle('think-collapsed')", js)

    # ---------- index.html 样式：竖线 / 灰字 / 淡蓝徽章 / 可滚动 ----------

    def _think_body_css(self):
        html = self.index_html
        start = html.index(".think-card-body {")
        return html[start:html.index("}", start)]

    def test_body_scrollable_with_left_border(self):
        """展开态内容完整可见、可滚动：.think-card-body max-height +
        overflow-y: auto；左侧竖线 border-left。"""
        css = self._think_body_css()
        self.assertIn("max-height: 260px", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("border-left: 3px solid", css)

    def test_line_styles_fade_and_badge(self):
        """逐行样式：.think-line 淡入动画（thinkLineFadeIn keyframes）、
        淡蓝色阶段标签小徽章（#3b82f6 on #eff6ff）、灰色正文（#6b7280）。"""
        html = self.index_html
        start = html.index(".think-line {")
        line_css = html[start:html.index("}", start)]
        self.assertIn("animation: thinkLineFadeIn", line_css)
        self.assertIn("@keyframes thinkLineFadeIn", html)
        tag_start = html.index(".think-line-tag {")
        tag_css = html[tag_start:html.index("}", tag_start)]
        self.assertIn("#3b82f6", tag_css)          # 淡蓝阶段标签
        self.assertIn("#eff6ff", tag_css)          # 淡蓝底
        text_start = html.index(".think-line-text {")
        text_css = html[text_start:html.index("}", text_start)]
        self.assertIn("#6b7280", text_css)         # 灰色思考文字

    def test_think_card_style_zero_regression(self):
        """思维链卡片既有样式零回退：.think-card 显式 display: block（整卡
        永远可见，折叠只藏正文）、浅灰背景等既有规格保留。"""
        html = self.index_html
        start = html.index(".think-card {")
        block = html[start:html.index("}", start)]
        self.assertIn("display: block", block)
        self.assertNotIn("display: none", block)
        self.assertIn("#f3f4f6", block)
        self.assertIn("border-radius: 10px", block)


# ---------------------------------------------------------------------------
# 任务 7：缩成加速球（60px 圆形、橘色边框、头像、拖拽、位置记忆、互切幂等）
# ---------------------------------------------------------------------------

class BallWidgetTests(unittest.TestCase):
    """加速球静态断言：样式、挂载点、开关接线、拖拽与位置记忆、共存哨兵。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")
        cls.pet_js = _read("desktop-pet.js")

    def _ball_section(self):
        """console.js 加速球整节（第 8 节到 IIFE 收尾）。"""
        js = self.console_js
        start = js.index("==================== 8.")
        return js[start:]

    def _ball_css(self):
        html = self.index_html
        start = html.index("#xiaoju3-ball {")
        return html[start:html.index("}", start)]

    def test_minimize_button_in_header(self):
        """index.html 聊天头部工具区新增最小化按钮 ⌄（header-btn 同款样式）。"""
        html = self.index_html
        start = html.index('<span class="header-actions">')
        actions = html[start:html.index("</span>", start)]
        self.assertIn('id="console-minimize"', actions)
        self.assertIn("⌄", actions)
        self.assertIn("class=\"header-btn\"", actions)
        # console.js 接线：点击最小化
        js = self.console_js
        self.assertIn("getElementById('console-minimize')", js)
        section = self._ball_section()
        btn_idx = section.index("getElementById('console-minimize')")
        self.assertLess(btn_idx, section.index("setConsoleMinimized(true)"))

    def test_ball_markup_with_mascot(self):
        """球体挂载点：index.html 静态节点 #xiaoju3-ball，小橘半身像
        /assets/pet/normal_half.png（非桌宠 DSniang1 素材，用户口径）。"""
        html = self.index_html
        self.assertIn('id="xiaoju3-ball"', html)
        start = html.index('id="xiaoju3-ball"')
        block = html[start:html.index("</div>", start)]
        self.assertIn('src="/assets/pet/normal_half.png"', block)
        self.assertNotIn("DSniang1", block)   # 球头像不再引用桌宠素材

    def test_ball_avatar_fallback_chain(self):
        """头像兜底链（用户口径：normal_half.png 不存在时退化为 🦊 emoji）：
        console.js 对球内 img 挂 error 监听——裂图移除 img、球体文字退化
        🦊（不改显隐类控制，最小化态永不出现空球/裂图图标）。"""
        js = self.console_js
        self.assertIn("bindBallImgFallback", js)
        section = js[js.index("bindBallImgFallback"):]
        self.assertIn("addEventListener('error'", section)
        self.assertIn("🦊", section)

    def test_ball_css_round_60px_hidden_by_default(self):
        """球体样式：直径 60px 圆形（border-radius: 50%）、右下角悬浮
        （position: fixed + right/bottom）、橘色 Q 版边框；默认 display:none，
        仅最小化态显示；控制台主体互斥显隐（body 根容器 class 切换）。"""
        css = self._ball_css()
        for token in ("display: none", "position: fixed", "width: 60px",
                      "height: 60px", "border-radius: 50%", "right: 24px",
                      "bottom: 24px", "border: 3px solid #d96f2b"):
            self.assertIn(token, css)
        html = self.index_html
        self.assertIn("body.xiaoju3-minimized #xiaoju3-ball { display: block; }", html)
        # 控制台主体（侧栏+聊天区）最小化时隐藏：根容器 class + CSS
        self.assertIn("body.xiaoju3-minimized > .sidebar", html)
        self.assertIn("body.xiaoju3-minimized > .chat-area", html)
        self.assertIn("body.xiaoju3-minimized > .chat-area { display: none; }", html)

    def test_toggle_class_and_idempotency(self):
        """互切幂等：class 切换（classList.toggle 带显式布尔）+ 已是目标状态
        直接返回；球体挂载点缺失静默跳过（无 JS 报错路径）。"""
        section = self._ball_section()
        self.assertIn("const MINIMIZE_CLASS = 'xiaoju3-minimized'", section)
        self.assertIn("function setConsoleMinimized", section)
        self.assertIn("document.body.classList.toggle(MINIMIZE_CLASS, minimized)",
                      section)
        self.assertIn("if (isMin === minimized) return;", section)   # 幂等守卫
        self.assertIn("if (!ball) return;", section)                 # 缺挂载点静默
        self.assertIn("if (isMin === minimized) return;", section)

    def test_ball_drag_and_position_memory(self):
        """拖拽与位置记忆：拖拽阈值与桌宠同口径（位移平方>9）、松手存
        localStorage（xiaoju3_ball_pos）、载入/最小化恢复记忆位置并钳制在
        视口内、resize 重钳制。"""
        section = self._ball_section()
        self.assertIn("const BALL_POS_KEY = 'xiaoju3_ball_pos'", section)
        self.assertIn("const BALL_SIZE = 60", section)
        self.assertIn("if (dx * dx + dy * dy > 9) moved = true;", section)
        self.assertIn("localStorage.setItem(BALL_POS_KEY, JSON.stringify(pos))",
                      section)
        self.assertIn("JSON.parse(localStorage.getItem(BALL_POS_KEY)", section)
        self.assertIn("function clampBallPos", section)
        self.assertIn("window.addEventListener('resize'", section)   # resize 重钳制
        # 点击（未拖动）展开回完整控制台
        self.assertIn("setConsoleMinimized(false);   // 未拖动＝点击展开回完整控制台",
                      section)

    def test_coexists_with_desktop_pet(self):
        """共存哨兵：加速球节不注入/不修改桌宠任何节点（无 __xiaoju3Pet/
        xiaoju3-root 引用），desktop-pet.js 桌宠规格标记原样保留（零改动）。"""
        section = self._ball_section()
        for pet_token in ("__xiaoju3Pet", "xiaoju3-root", "PET_LINES",
                          "xiaoju3Sound", "xiaoju3SetPetState"):
            self.assertNotIn(pet_token, section)
        for pet_token in ("window.__xiaoju3Pet", "PET_STATE_IMAGES",
                          "snapToEdge", "PET_LINES"):
            self.assertIn(pet_token, self.pet_js)   # 桌宠本体零改动哨兵


# ---------------------------------------------------------------------------
# 终端记录标签页（对话窗口 / 终端记录切换，GET /api/history?source=terminal）
# ---------------------------------------------------------------------------

class TerminalTabTests(unittest.TestCase):
    """终端记录标签页静态断言：标签栏结构、内容区互斥、只读语义、取数契约。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _tab_section(self):
        """console.js 终端记录整节（7.5 节，到第 8 节之前）。"""
        js = self.console_js
        start = js.index("==================== 7.5 ")
        return js[start:js.index("==================== 8.")]

    def test_tab_bar_markup(self):
        """标签栏标记：对话窗口 / 终端记录两个标签位于聊天头部与记录区之间；
        终端面板缺省隐藏（hidden 属性）；含刷新按钮与记录挂载点。"""
        html = self.index_html
        self.assertIn('<div class="chat-tabs">', html)
        self.assertIn(
            '<button id="tab-console" class="chat-tab active" type="button">对话窗口</button>',
            html)
        self.assertIn(
            '<button id="tab-terminal" class="chat-tab" type="button">终端记录</button>',
            html)
        # 标签栏在聊天头部之后、聊天记录区之前
        self.assertLess(html.index('class="chat-tabs"'),
                        html.index('id="chat-history"'))
        self.assertGreater(html.index('class="chat-tabs"'),
                           html.index('class="chat-header"'))
        # 终端面板缺省隐藏（hidden），由 console.js 切换显隐
        self.assertIn('<div class="terminal-pane" id="terminal-pane" hidden>', html)
        self.assertIn('id="terminal-history"', html)
        self.assertIn('id="terminal-refresh"', html)

    def test_tab_css_and_hidden_rule(self):
        """样式：全局 [hidden] 显隐兜底（display:flex 类会盖掉 hidden 属性）、
        标签激活态、禁用清空按钮、终端面板样式齐备。"""
        html = self.index_html
        self.assertIn("[hidden] { display: none !important; }", html)
        self.assertIn(".chat-tab.active", html)
        self.assertIn(".header-btn:disabled", html)
        self.assertIn(".terminal-pane", html)
        self.assertIn(".terminal-history", html)
        self.assertIn(".terminal-empty", html)

    def test_fetch_contract(self):
        """取数契约：GET /api/history?source=terminal（R3 后端契约，文件缺失
        恒 200 空列表）；响应形状校验（code/data.messages 数组）；空列表与
        失败各有占位文案；竞态守卫（请求序号）丢弃慢响应。"""
        section = self._tab_section()
        self.assertIn("'/api/history?source=terminal'", section)
        self.assertIn("Array.isArray(res.data.messages)", section)
        self.assertIn("terminalFetchSeq", section)
        self.assertIn("暂无终端记录", section)
        self.assertIn("（终端记录读取失败：", section)

    def test_readonly_semantics(self):
        """只读语义：终端页隐藏输入框、清空按钮禁用、消息不带任何操作
        工具栏（无 msg-tools / buildSystemMsgTools / startThinkTypewriter）。"""
        section = self._tab_section()
        self.assertIn("chatInputAreaEl.hidden = isTerminal", section)
        self.assertIn("clearBtnEl.disabled = isTerminal", section)
        self.assertNotIn("msg-tools", section)
        self.assertNotIn("buildSystemMsgTools", section)
        self.assertNotIn("startThinkTypewriter", section)

    def test_tab_switching_and_autorefresh(self):
        """切换接线：两个标签点击 ↔ switchChatTab('terminal'/'console')；
        内容区互斥显隐；切入拉最新 + 停留期间定时自动刷新、切走清定时器。"""
        section = self._tab_section()
        self.assertIn("function switchChatTab", section)
        self.assertIn("tabTerminalBtn.addEventListener('click'", section)
        self.assertIn("switchChatTab('terminal')", section)
        self.assertIn("switchChatTab('console')", section)
        self.assertIn("chatHistoryPaneEl.hidden = isTerminal", section)
        self.assertIn("terminalPaneEl.hidden = !isTerminal", section)
        self.assertIn("setInterval(loadTerminalHistory, TERMINAL_REFRESH_MS)",
                      section)
        self.assertIn("clearInterval(terminalRefreshTimer)", section)

    def test_think_card_readonly_render(self):
        """终端 AI 消息：沿用 splitThinkBlock 切分 + 折叠卡片（不打字、直接
        折叠展示）；正文 renderRich 转义、思考文本 renderCQFace 净化后
        textContent 注入——与聊天视图同口径免 XSS。"""
        section = self._tab_section()
        self.assertIn("splitThinkBlock(msg.content)", section)
        self.assertIn("buildThinkCardEl()", section)
        self.assertIn("renderRich(parts.body)", section)
        self.assertIn("renderCQFace(parts.think)", section)


# ---------------------------------------------------------------------------
# node 实跑（可选）：语法门 + 分段行为 + 加速球互切幂等/位置钳制
# ---------------------------------------------------------------------------

@unittest.skipUnless(_node_available(), "环境无 node，跳过 JS 实跑（静态断言已覆盖）")
class WebUxNodeLiveRunTests(unittest.TestCase):
    """node 实跑：提取真实源码片段喂桩验证行为（无网络、无临时文件）。"""

    def _run_node(self, script):
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return json.loads(proc.stdout.decode("utf-8"))

    def test_console_js_syntax_gate(self):
        """node --check：console.js 语法合法（非法 JS 会让整个前端瘫痪）。"""
        proc = subprocess.run(["node", "--check",
                               os.path.join(PROJECT_ROOT, "console.js")],
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))

    def test_split_think_stage_lines_behavior(self):
        """分段行为（提取真实 splitThinkStageLines + THINK_STAGE_RE）：
        [思考]/[计划]/[行动] 各自成段、标记文字入 tag、标记前缀从正文剥离；
        续行并入当前段（保留换行）；无标记单行 → 无 tag 单段（前端据此降级
        逐字打字机）；空串安全。"""
        js = _read("console.js")
        chunk = js[js.index("const THINK_STAGE_RE"):
                   js.index("function buildThinkLineEl")]
        script = (chunk + "\n"
                  "var r = splitThinkStageLines("
                  "'[思考] 需要点WLAN，先定位控件。\\n"
                  "[计划] 1. UI解析 2. 失败转视觉\\n"
                  "[行动] {\"tool\": \"ui_tap_element\"}');\n"
                  "var r2 = splitThinkStageLines('[思考] 第一行\\n续行内容\\n"
                  "[计划] 计划正文');\n"
                  "var r3 = splitThinkStageLines('纯文本思考一行');\n"
                  "var r4 = splitThinkStageLines('');\n"
                  "console.log(JSON.stringify({\n"
                  "  n: r.length,\n"
                  "  tags: r.map(function (s) { return s.tag; }),\n"
                  "  t0: r[0].text, t2: r[2].text,\n"
                  "  r2n: r2.length, r2t0: r2[0].text, r2t1: r2[1].text,\n"
                  "  r3tag: r3[0].tag, r3n: r3.length,\n"
                  "  r4n: r4.length\n"
                  "}));\n")
        out = self._run_node(script)
        self.assertEqual(out["n"], 3)                       # 三段各自成行
        self.assertEqual(out["tags"], ["思考", "计划", "行动"])
        self.assertEqual(out["t0"], "需要点WLAN，先定位控件。")   # 标记前缀剥离
        self.assertIn('"tool"', out["t2"])                  # [行动] 段正文原样（think 内容）
        self.assertEqual(out["r2n"], 2)
        self.assertEqual(out["r2t0"], "第一行\n续行内容")    # 续行并入当前段
        self.assertEqual(out["r2t1"], "计划正文")
        self.assertEqual(out["r3tag"], "")                  # 无标记 → 无 tag 单段
        self.assertEqual(out["r3n"], 1)
        self.assertEqual(out["r4n"], 0)                     # 空串安全

    def test_ball_toggle_idempotent_and_clamped(self):
        """加速球互切（提取真实 setConsoleMinimized 等整组函数 + 桩替代
        DOM/localStorage）：重复最小化/展开幂等（class 恰切换一次）；记忆
        位置越界时钳制在视口内；挂载点缺失静默跳过（不抛错=无 JS 报错路径）。"""
        js = _read("console.js")
        chunk = js[js.index("const MINIMIZE_CLASS"):
                   js.index("function initConsoleBall")]
        script = (
            "var __store = {};\n"
            "var localStorage = {\n"
            "  getItem: function (k) { return (k in __store) ? __store[k] : null; },\n"
            "  setItem: function (k, v) { __store[k] = String(v); },\n"
            "  removeItem: function (k) { delete __store[k]; }\n"
            "};\n"
            "var __ball = { style: {}, dataset: {} };\n"
            "var __minCls = {};\n"
            "var document = {\n"
            "  body: { classList: {\n"
            "    contains: function (c) { return !!__minCls[c]; },\n"
            "    toggle: function (c, f) { if (f) { __minCls[c] = true; } "
            "else { delete __minCls[c]; } }\n"
            "  } },\n"
            "  documentElement: { clientWidth: 800, clientHeight: 600 },\n"
            "  getElementById: function (id) { "
            "return id === 'xiaoju3-ball' ? __ball : null; }\n"
            "};\n"
            + chunk + "\n"
            "setConsoleMinimized(true);\n"
            "setConsoleMinimized(true);          // 重复最小化：幂等无操作\n"
            "var minOnce = document.body.classList.contains('xiaoju3-minimized');\n"
            "setConsoleMinimized(false);\n"
            "setConsoleMinimized(false);          // 重复展开：幂等无操作\n"
            "var expanded = !document.body.classList.contains('xiaoju3-minimized');\n"
            "saveBallPos({ x: 900, y: -20 });    // 越界位置 → 钳制在视口内\n"
            "setConsoleMinimized(true);\n"
            "var left = __ball.style.left, top = __ball.style.top;\n"
            "document = { getElementById: function () { return null; } };  // 缺挂载点\n"
            "var noThrow = true;\n"
            "try { setConsoleMinimized(true); setConsoleMinimized(false); } "
            "catch (e) { noThrow = false; }\n"
            "console.log(JSON.stringify({ minOnce: minOnce, expanded: expanded,\n"
            "  left: left, top: top, right: __ball.style.right,\n"
            "  noThrow: noThrow }));\n")
        out = self._run_node(script)
        self.assertTrue(out["minOnce"])                       # 幂等：最小化恰好生效
        self.assertTrue(out["expanded"])                      # 幂等：展开恰好生效
        self.assertEqual(out["left"], "740px")                # 800-60 钳制
        self.assertEqual(out["top"], "0px")                   # 负值钳到 0
        self.assertEqual(out["right"], "auto")                # 定位切换到 left/top
        self.assertTrue(out["noThrow"])                       # 缺挂载点不抛错


if __name__ == "__main__":
    unittest.main()
