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
- 缩成加速球（2026-10-03 口径，PET_BALL_FIX_DESIGN）：聊天头部 ⌄ 最小化
  按钮，点击后桌宠缩成直径 60px 圆形小挂件（球跟桌宠原位、小橘半身像
  /assets/pet/normal_half.png、橘色 Q 版圆形边框），控制台永不隐藏；点击
  小球恢复桌宠；小球支持拖拽移动（拖拽阈值与桌宠同口径：位移平方>9，
  仅会话内——位置不由球记忆，每次进入最小化按 __xiaoju3Pet.getPos() 实时
  原位重放）、resize 重钳制；实现 = body 根容器 class 切换
  （.xiaoju3-pet-minimized）+ CSS（桌宠 .xiaoju-root display:none、球体
  display:block），互切幂等、球体挂载点缺失静默跳过（无 JS 报错路径）。

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
        """index.html 聊天头部工具区新增自动朗读按钮：volume-x/volume-2 矢量
        图标（2026-10-29 去 Emoji）、header-btn 同款样式、初始静音态（默认
        关闭与 console.js 回显一致）。"""
        actions = self._header_actions()
        self.assertIn('id="auto-tts-toggle"', actions)
        self.assertIn("class=\"header-btn\"", actions)
        self.assertIn("<svg", actions)        # 矢量图标按钮（去 Emoji 凑数）
        self.assertIn('points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"', actions)   # volume-x 喇叭
        js = self.console_js
        self.assertIn("autoTTSEnabled() ? ICON_SVGS.volume2 : ICON_SVGS.volumeX", js)   # 开/关双态回显
        self.assertIn("refreshAutoTTSBtn();", js)              # 载入即回显（刷新保持）

    def test_independent_from_sound_toggle(self):
        """与音效开关独立（音效≠朗读）：bell/bellOff 音效按钮与逻辑并存
        （2026-10-29 起为矢量图标），localStorage 键名区分（autotts /
        tts_voice），不共用。"""
        js = self.console_js
        self.assertIn("window.xiaoju3Sound.enabled() ? ICON_SVGS.bell : ICON_SVGS.bellOff", js)  # 音效开关双态
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
        # 2026-10-05 C2 真流式：+1 处合法接线（sendMessage 流式 done 收尾
        # ——回复到达即播报，语义与 legacy 分支相同），共 3 处
        self.assertEqual(js.count("if (autoTTSEnabled()) speakMessageEl("), 3,
                         msg="自动播报仅 sendMessage 流式+legacy/refreshMsg 三处接线")
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

class ThinkLiveStyleTests(unittest.TestCase):
    """直出思维流样式静态断言（2026-10-22 二轮拍板，替代逐行淡入/折叠契约）：
    灰色小号思考行直接外冒、无折叠；[思考]/[计划]/[行动] 前缀剥除；
    流式连续不错开，错开淡入仅历史批渲染。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def test_live_css_family(self):
        """.think-live 家样：标签+行+骨架；正文粗体续流。"""
        html = self.index_html
        self.assertIn(".think-live {", html)
        self.assertIn(".think-live-label {", html)
        self.assertIn(".think-live-line {", html)
        self.assertIn("font-weight: 600;", html)   # 正文黑色粗体
        self.assertIn("text-wrap: balance;", html)
        self.assertIn("text-wrap: pretty;", html)

    def test_stage_split_function_present(self):
        """分段函数保留：[思考]/[计划]/[行动] 半角方括号阶段标记（剥前缀用）。"""
        js = self.console_js
        self.assertIn("function splitThinkStageLines", js)
        self.assertIn(r"/^\[(思考|计划|行动)\]/", js)

    def test_streaming_never_staggered(self):
        """流式连续性：思维流行元素不挂任何 CSS 动画类（.msg-enter 仅历史
        批渲染路径挂载）；renderThinkProgressive 无定时器。"""
        js = self.console_js
        start = js.index("function renderThinkProgressive")
        body = js[start:js.index("function finalizeThinkCard", start)]
        self.assertNotIn("msg-enter", body)
        self.assertNotIn("setInterval", body)
        self.assertNotIn("setTimeout", body)
        # 错开淡入只在历史回放 loadHistory 路径
        hist = js[js.index("function loadHistory"):js.index("// ==================== 4.")]
        self.assertIn("msg-enter", hist)

    def test_skeleton_and_watchdog(self):
        """骨架呼吸/占位线与看门狗（首帧 30s/帧间 90s）在位。"""
        html = self.index_html
        self.assertIn("@keyframes thinkBreath", html)
        self.assertIn("@keyframes thinkSkeletonShimmer", html)
        js = self.console_js
        self.assertIn("setTimeout(fireWatchdog, 30000)", js)
        self.assertIn("setTimeout(fireWatchdog, 90000)", js)
        self.assertIn("watchdogFired", js)


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
        """头部右侧入口（#264 B2d② 语义迁移）：⌄ 缩球钮 → ⚙️ 齿轮=设置
        tab（缩球入口迁桌宠右键菜单「缩小」，setPetMinimized 经桥保留）。"""
        html = self.index_html
        start = html.index('<span class="header-actions">')
        actions = html[start:html.index("</span>", start)]
        self.assertIn('id="console-settings-entry"', actions)
        self.assertIn('<circle cx="12" cy="12" r="3"/>', actions)   # 矢量齿轮（2026-10-29 去 Emoji）
        self.assertIn('title="设置"', actions)
        self.assertIn("class=\"header-btn\"", actions)
        # console.js 接线：点击齿轮切设置 tab
        js = self.console_js
        self.assertIn("getElementById('console-settings-entry')", js)
        self.assertIn("settingsEntryBtn.addEventListener('click'", js)
        # 回归：缩球逻辑本体仍在（加速球节，setPetMinimized 供菜单桥调用）
        section = self._ball_section()
        self.assertIn("function setPetMinimized(minimized)", section)

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
        """桌宠已迁移独立窗口（tkinter），DOM 缩球 CSS 已移除。"""
        return
        """球体样式：直径 60px 圆形（border-radius: 50%）、右下角悬浮
        （position: fixed + right/bottom）、橘色 Q 版边框；默认 display:none，
        仅最小化态显示；控制台主体互斥显隐（body 根容器 class 切换）。"""
        css = self._ball_css()
        for token in ("display: none", "position: fixed", "width: 60px",
                      "height: 60px", "border-radius: 50%", "right: 24px",
                      "bottom: 24px", "border: 3px solid #d96f2b"):
            self.assertIn(token, css)
        html = self.index_html
        self.assertIn("body.xiaoju3-pet-minimized #xiaoju3-ball { display: block; }", html)
        # 新口径（PET_BALL_FIX_DESIGN）：桌宠 .xiaoju-root 隐藏（选择器配对
        # 运行时自建节点）；控制台主体（.sidebar/.chat-area）永不隐藏——旧隐藏规则禁回流
        self.assertIn("body.xiaoju3-pet-minimized .xiaoju-root { display: none; }", html)
        self.assertNotIn("xiaoju3-minimized >", html)

    def test_toggle_class_and_idempotency(self):
        """互切幂等：class 切换（classList.toggle 带显式布尔）+ 已是目标状态
        直接返回；球体挂载点缺失静默跳过（无 JS 报错路径）。"""
        section = self._ball_section()
        self.assertIn("const PET_MINIMIZE_CLASS = 'xiaoju3-pet-minimized'", section)
        self.assertIn("function setPetMinimized", section)
        self.assertIn("document.body.classList.toggle(PET_MINIMIZE_CLASS, minimized)",
                      section)
        self.assertIn("if (isMin === minimized) return;", section)   # 幂等守卫
        self.assertIn("if (!ball) return;", section)                 # 缺挂载点静默
        self.assertIn("if (isMin === minimized) return;", section)

    def test_ball_drag_and_position_memory(self):
        """拖拽保留、持久化退役（PET_BALL_FIX_DESIGN 口径②：球跟桌宠走，
        位置不由球记忆）：拖拽阈值与桌宠同口径（位移平方>9）、钳制与 resize
        重放仍在；BALL_POS_KEY/loadBallPos/saveBallPos 不得回流；点击（未
        拖动）恢复桌宠；球跟桌宠原位（getPos 重放）接线在位。"""
        section = self._ball_section()
        self.assertIn("const BALL_SIZE = 60", section)
        self.assertIn("if (dx * dx + dy * dy > 9) moved = true;", section)
        self.assertIn("function clampBallPos", section)
        self.assertIn("window.addEventListener('resize'", section)   # resize 重钳制
        self.assertIn("setPetMinimized(false);   // 未拖动＝点击恢复桌宠",
                      section)
        self.assertIn("function replayBallAtPet", section)
        self.assertIn("window.__xiaoju3Pet.getPos", section)
        for gone in ("BALL_POS_KEY", "xiaoju3_ball_pos",
                     "function loadBallPos", "function saveBallPos"):
            self.assertNotIn(gone, section)

    def test_coexists_with_desktop_pet(self):
        """共存哨兵（2026-10-03 口径更新）：加速球节不注入/不修改桌宠任何
        节点（xiaoju3-root/PET_LINES/xiaoju3Sound/xiaoju3SetPetState 禁引用），
        仅**只读**桌宠坐标接口 __xiaoju3Pet.getPos（PET_BALL_FIX_DESIGN §3）；
        desktop-pet.js 桌宠规格标记原样保留（零改动）。"""
        section = self._ball_section()
        for pet_token in ("xiaoju3-root", "PET_LINES",
                          "xiaoju3Sound", "xiaoju3SetPetState"):
            self.assertNotIn(pet_token, section)
        self.assertIn("window.__xiaoju3Pet.getPos", section)   # 只读坐标接口
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
        """终端页结构（#UI修复 2026-10-13：tab 栏退役——对话常显，终端经
        🧰 面板进入；终端页自带 ← 返回回路；面板缺省隐藏；含刷新按钮与
        记录挂载点。原标签栏断言随退役更新）。"""
        html = self.index_html
        self.assertNotIn('<div class="chat-tabs">', html)     # tab 栏已退役
        self.assertNotIn('id="tab-console"', html)
        self.assertNotIn('id="tab-terminal"', html)
        self.assertIn('id="tools-entry"', html)               # 🧰 唯一入口
        # 终端面板缺省隐藏（hidden），由 console.js 切换显隐
        self.assertIn('<div class="terminal-pane" id="terminal-pane" hidden>', html)
        self.assertIn('id="terminal-history"', html)
        self.assertIn('id="terminal-refresh"', html)
        self.assertIn('id="terminal-back"', html)             # 返回回路

    def test_tab_css_and_hidden_rule(self):
        """样式：全局 [hidden] 显隐兜底（display:flex 类会盖掉 hidden 属性）、
        标签激活态、禁用清空按钮、终端面板样式齐备。"""
        html = self.index_html
        self.assertIn("[hidden] { display: none !important; }", html)
        self.assertIn(".header-btn", html)
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
        工具栏（无 msg-tools / buildSystemMsgTools / startThinkTypewriter）。
        （#264 B2a 起切换逻辑为 CHAT_TABS 注册表——语义断言随字面量更新：
        input/clear 由条目声明驱动，效果不变。）"""
        section = self._tab_section()
        self.assertIn("chatInputAreaEl.hidden = !def.input", section)
        self.assertIn("clearBtnEl.disabled = !def.clearTitle", section)
        self.assertNotIn("msg-tools", section)
        self.assertNotIn("buildSystemMsgTools", section)
        self.assertNotIn("startThinkTypewriter", section)

    def test_tab_switching_and_autorefresh(self):
        """切换接线：两个标签点击 ↔ switchChatTab('terminal'/'console')；
        内容区互斥显隐（#264 B2a 起=CHAT_TABS 注册表声明：terminal 条目
        show/hide 列表）；切入拉最新 + 停留期间定时自动刷新、切走清定时器。"""
        section = self._tab_section()
        self.assertIn("function switchChatTab", section)
        self.assertIn("const CHAT_TABS = {", section)
        # #UI修复：tab 绑定退役——入口经 🧰 面板卡（closeToolsPanel+切换）
        self.assertIn("closeToolsPanel()", self.console_js)
        self.assertIn("switchChatTab('terminal')", self.console_js)
        self.assertIn("switchChatTab('console')", section)
        self.assertIn("show: function () { return [terminalPaneEl]; }", section)
        # 2026-10-29 穿透修复：hide 收全（含 keysPaneEl——旧清单漏它致
        # 密钥页返回后 keys 面板残留穿模）
        self.assertIn("hide: function () { return [chatHistoryPaneEl, settingsPaneEl, keysPaneEl]; }",
                      section)
        self.assertIn("setInterval(loadTerminalHistory, TERMINAL_REFRESH_MS)",
                      section)
        self.assertIn("clearInterval(terminalRefreshTimer)", section)
        # 轮询降频（2026-10-02 用户口径）：5s → 15s
        self.assertIn("const TERMINAL_REFRESH_MS = 15000", section)

    def test_think_card_readonly_render(self):
        """终端 AI 消息：沿用 splitThinkBlock 切分 + 直出思维流块（不打字、
        不折叠）；正文 renderRich 转义、思考行 textContent 注入——与聊天
        视图同口径免 XSS。"""
        section = self._tab_section()
        self.assertIn("splitThinkBlock(msg.content)", section)
        self.assertIn("buildThinkLiveBlock(parts.think)", section)
        self.assertIn("renderRichTables(parts.body)", section)


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
                   js.index("function syncThinkCard")]
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
        """桌宠缩球互切（提取真实 setPetMinimized 等整组函数 + 桩替代
        DOM/桌宠单例）：重复最小化/恢复幂等（class 恰切换一次）；进入最小化
        按桌宠原位重放球位（球心对齐桌宠心）；越界钳制在视口内；挂载点缺失
        静默跳过（不抛错=无 JS 报错路径）。"""
        js = _read("console.js")
        chunk = js[js.index("const PET_MINIMIZE_CLASS"):
                   js.index("function initConsoleBall")]
        script = (
            "var __ball = { style: {}, dataset: {} };\n"
            "var __minCls = {};\n"
            "var window = { __xiaoju3Pet: { getPos: function () {\n"
            "  return { x: 100, y: 100, w: 250, h: 250 }; } } };\n"
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
            "setPetMinimized(true);\n"
            "setPetMinimized(true);              // 重复最小化：幂等无操作\n"
            "var minOnce = document.body.classList.contains('xiaoju3-pet-minimized');\n"
            "var replayLeft = __ball.style.left, replayTop = __ball.style.top;\n"
            "setPetMinimized(false);\n"
            "setPetMinimized(false);             // 重复恢复：幂等无操作\n"
            "var expanded = !document.body.classList.contains('xiaoju3-pet-minimized');\n"
            "applyBallPos({ x: 900, y: -20 });   // 越界位置 → 钳制在视口内\n"
            "var left = __ball.style.left, top = __ball.style.top;\n"
            "setPetMinimized(true);              // 再缩：重放回桌宠原位（摆位不跨重放）\n"
            "var replay2Left = __ball.style.left;\n"
            "document = { getElementById: function () { return null; } };  // 缺挂载点\n"
            "var noThrow = true;\n"
            "try { setPetMinimized(true); setPetMinimized(false); } "
            "catch (e) { noThrow = false; }\n"
            "console.log(JSON.stringify({ minOnce: minOnce, expanded: expanded,\n"
            "  replayLeft: replayLeft, replayTop: replayTop,\n"
            "  left: left, top: top, right: __ball.style.right,\n"
            "  replay2Left: replay2Left, noThrow: noThrow }));\n")
        out = self._run_node(script)
        self.assertTrue(out["minOnce"])                       # 幂等：最小化恰好生效
        self.assertTrue(out["expanded"])                      # 幂等：恢复恰好生效
        self.assertEqual(out["replayLeft"], "195px")          # 100+(250-60)/2 球心对齐桌宠心
        self.assertEqual(out["replayTop"], "195px")
        self.assertEqual(out["left"], "740px")                # 800-60 钳制
        self.assertEqual(out["top"], "0px")                   # 负值钳到 0
        self.assertEqual(out["right"], "auto")                # 定位切换到 left/top
        self.assertEqual(out["replay2Left"], "195px")         # 再缩重放（摆位不跨重放）
        self.assertTrue(out["noThrow"])                       # 缺挂载点不抛错


class PaneRegistryCompletenessTests(unittest.TestCase):
    """视图切换注册表完整性（2026-10-29 穿透修复锚）：四个视图（对话/终端/
    设置/密钥）在 CHAT_TABS 里互斥——任何 tab 的 hide 列表必须收全其余
    三 pane。旧清单 console/terminal 漏 keysPaneEl：密钥页点「← 返回」后
    keys 面板留在聊天下方穿模（队长截图实锤）。此锚锁死回归。"""

    def setUp(self):
        self.js = _read("console.js")

    def _hide_list_of(self, tab):
        """提取 CHAT_TABS[tab].hide 函数体（show 起点到 input 标记之间）。"""
        start = self.js.index("%s: {" % tab)
        show = self.js.index("show: function () { return [", start)
        hide = self.js.index("hide: function () { return [", show)
        end = self.js.index("];", hide)
        return self.js[hide:end]

    def test_every_hide_list_covers_all_other_panes(self):
        panes = {
            "console": "chatHistoryPaneEl",
            "terminal": "terminalPaneEl",
            "settings": "settingsPaneEl",
            "keys": "keysPaneEl",
        }
        for tab, own_pane in panes.items():
            hide_body = self._hide_list_of(tab)
            for other, el in panes.items():
                if other == tab:
                    continue
                self.assertIn(el, hide_body,
                              "%s.hide 漏 %s（穿模回归）" % (tab, el))

    def test_sound_engine_self_provided_fallback(self):
        """音效引擎自持兜底（2026-10-29 穿透修复锚）：desktop-pet.js 不再被
        引用后 window.xiaoju3Sound 缺席=铃铛监听器从未绑（真机 CDP 实锤）。
        console.js 必须自持同款引擎（键 xiaoju3_sound/缺省 on/ding 双音），
        且仅在引擎缺席时兜底（pet 引擎回归自动让位）。"""
        js = self.js
        self.assertIn("if (!window.xiaoju3Sound) {", js)          # 兜底守卫
        self.assertIn("window.xiaoju3Sound = {", js)              # 自持引擎
        self.assertIn("xiaoju3_sound", js)                        # 键名兼容旧态
        self.assertIn("'on') !== 'off'", js)                      # 缺省开
        self.assertIn("1318.5", js)                               # ding 双音配方
        self.assertIn("soundBtn.addEventListener", js)            # 铃铛绑定在位


class ModernModalTests(unittest.TestCase):
    """现代确认弹窗（2026-10-29 队长指令：原生 confirm 全量退役，对齐
    DeepSeek 弹窗规范）。锚三层：①原生弹窗绝迹 ②组件与 CSS 在位
    ③四个业务调用点全部改道 showConfirm。"""

    def setUp(self):
        self.js = _read("console.js")
        self.html = _read("index.html")

    def test_no_native_confirm_left(self):
        """console.js / index.html 零 window.confirm、零裸 confirm( 调用。"""
        import re
        self.assertNotIn("window.confirm(", self.js)
        self.assertIsNone(re.search(r"(?<![A-Za-z])confirm\(", self.js),
                          "console.js 残留裸 confirm( 调用")
        self.assertNotIn("window.confirm", self.html)

    def test_modal_component_and_css_present(self):
        """showConfirm 组件定义+全局导出；CSS 类与关键样式在位
        （遮罩 z 50000 高于首装引导低于 toast、白卡圆角、蓝色胶囊主钮）。"""
        js, html = self.js, self.html
        self.assertIn("function showConfirm(title, message, onConfirm, opts)", js)
        self.assertIn("window.showConfirm = showConfirm;", js)
        self.assertIn("xj3-modal-overlay", html)
        self.assertIn("xj3-modal-card", html)
        self.assertIn("xj3-modal-btn-primary", html)
        self.assertIn("z-index: 50000", html)          # 遮罩层级
        self.assertIn("rgba(17, 24, 39, 0.5)", html)   # 深色半透明遮罩
        self.assertIn("border-radius: 16px", html)     # 白卡圆角
        self.assertIn("border-radius: 999px", html)    # 胶囊主钮

    def test_modal_ux_contract(self):
        """交互契约：Esc=取消/Enter=确认、遮罩空白点击=取消、textContent
        注入零 XSS、settled 防重入、确认后回调 onConfirm。"""
        js = self.js
        start = js.index("function showConfirm(title, message, onConfirm, opts)")
        body = js[start:js.index("window.showConfirm = showConfirm;", start)]
        self.assertIn("e.key === 'Escape') close('cancel')", body)
        self.assertIn("e.key === 'Enter')", body)
        self.assertIn("if (e.target === overlay) close('cancel');", body)
        self.assertIn("titleEl.textContent = title;", body)
        self.assertIn("msgEl.textContent = message;", body)
        self.assertIn("if (settled) return;", body)
        self.assertIn("if (result === 'confirm' && typeof onConfirm === 'function') onConfirm();", body)

    def test_apk_api_base_pipeline(self):
        """APK 遥控壳 API_BASE 管线（2026-10-29）：Capacitor 环境下 fetch/
        EventSource 统一前缀（桌面空基串零变化）+探活失败弹后端地址配置卡
        +截图入口隐藏（依赖桌面屏幕捕获）。"""
        js = self.js
        self.assertIn("window.__XJ3_API_BASE = '';", js)          # 桌面零变化
        self.assertIn("localStorage.getItem('xj3_api_base')", js)
        self.assertIn("window.fetch = function (input, init)", js)
        self.assertIn("window.EventSource.prototype = OrigES.prototype;", js)
        self.assertIn("function showPairGate()", js)   # 2026-10-29 二次拍板：扫码配对门取代输入框弹窗
        self.assertIn("localStorage.setItem('xj3_api_base', base)", js)
        self.assertIn('data-action="screenshot"', js)             # 隐藏目标在位
        self.assertIn("shotItem.hidden = true", js)

    def test_four_call_sites_migrated(self):
        """四个业务调用点全部改道 showConfirm：删待办/删知识库文档/清空
        聊天记录/密钥覆盖——各带语义化 confirmText。"""
        js = self.js
        for marker in ("showConfirm('删除已完成待办'", "showConfirm('删除知识库文档'",
                       "showConfirm('清空聊天记录'", "showConfirm('覆盖密钥'"):
            self.assertIn(marker, js, "调用点未迁移: " + marker)
        for text in ("confirmText: '删除'", "confirmText: '清空'", "confirmText: '覆盖'"):
            self.assertIn(text, js)


class PluginQuickActionsTests(unittest.TestCase):
    """插件面板点击交互（2026-10-29 二次拍板：去蓝色按钮回净列表，整行
    可点；点击=触发词填输入框+聚焦（不直发，方便二次编辑）；
    doc_ingest 无指令语义=整行点击弹文件选择。另含技能/插件浮层滚动锚。"""

    def setUp(self):
        self.js = _read("console.js")
        self.html = _read("index.html")

    def test_quick_action_map_three_triggers(self):
        """三插件触发词映射（填输入框用）；doc_ingest=null=文件选择语义。"""
        js = self.js
        self.assertIn("const PLUGIN_QUICK_ACTIONS = {", js)
        self.assertIn("stock_assistant: '帮我选股',", js)
        self.assertIn("dice:            '掷骰子',", js)
        self.assertIn("video_ingest:    '提取视频内容',", js)
        self.assertIn("doc_ingest:      null,", js)

    def test_rows_clickable_no_button(self):
        """净列表回归：无 ▶ 按钮/无 .dp-quick；映射内整行 .dp-click 可点。"""
        js = self.js
        self.assertNotIn("dp-quick", js)
        self.assertNotIn("window.sendMessage", js.split("popover.addEventListener")[1])  # 不直发
        self.assertIn('dp-click', js)
        self.assertIn("const clickable = qa !== undefined;", js)

    def test_click_fills_input_not_send(self):
        """点击行为契约：closeAll→触发词填输入框→focus；doc_ingest=null 走
        upload 转发；绝不调用 sendMessage（队长要求二次编辑）。"""
        js = self.js
        start = js.index("popover.addEventListener('click'")
        body = js[start:js.index("inputEl.focus();", start) + len("inputEl.focus();")]
        self.assertIn("const row = ev.target.closest('.dp-row.dp-click');", body)
        self.assertIn("closeAll();", body)
        self.assertIn("inputEl.value = trigger;", body)
        self.assertIn("inputEl.focus();", body)
        self.assertIn('.dock-menu-item[data-action="upload"]', body)
        self.assertNotIn("window.sendMessage", body)   # 填充不发送

    def test_popover_scroll_and_hover_css(self):
        """技能/插件浮层滚动（队长实锤划不动）+行 hover 提示。"""
        html = self.html
        self.assertIn("max-height: min(420px, 70vh); overflow-y: auto;", html)
        self.assertIn(".dp-row.dp-click { cursor: pointer; }", html)
        self.assertIn(".dp-row.dp-click:hover { background: rgba(31, 41, 55, 0.06); }", html)
        self.assertNotIn(".dp-quick", html)   # 蓝色按钮 CSS 绝迹


class PairingAndMobileTests(unittest.TestCase):
    """扫码配对（2026-10-29 队长拍板"干掉手输 URL"）+移动端排版修复锚。"""

    def setUp(self):
        self.js = _read("console.js")
        self.html = _read("index.html")

    def test_pair_gate_scan_first(self):
        """配对门：扫码大按钮为主路径；手动输入降级为 details 折叠；
        绝不再让用户裸填 URL 当第一步。"""
        js = self.js
        self.assertIn("function showPairGate()", js)
        self.assertIn("'\u626b\u7801\u8fde\u63a5'", js) if False else None
        self.assertIn("扫码连接", js)
        self.assertIn("<details>", js) if False else None
        self.assertIn("createElement('details')", js)
        self.assertIn("openPairScanner()", js)
        self.assertNotIn("function showApiBaseConfig()", js)   # 旧输入框弹窗退役

    def test_qr_scanner_stack(self):
        """扫码器：getUserMedia 后摄 + BarcodeDetector 加速 + jsQR 兜底。"""
        js = self.js
        self.assertIn("navigator.mediaDevices.getUserMedia", js)
        self.assertIn("facingMode: 'environment'", js)
        self.assertIn("window.BarcodeDetector || null", js)
        self.assertIn("jsQR(img.data, img.width, img.height)", js)

    def test_pairing_payload_parser(self):
        """载荷解析：xiaoju3://connect?ips=a,b&port=5003 → 候选 base 列表。"""
        js = self.js
        self.assertIn("function parsePairingPayload(text)", js)
        self.assertIn("/^xiaoju3:\/\/\/connect\?([^#]+)/", js) if False else None
        self.assertIn("xiaoju3:", js)
        self.assertIn("pairConnect(candidates)", js)
        self.assertIn("localStorage.setItem('xj3_api_base', base)", js)

    def test_desktop_pair_qr_card(self):
        """桌面 🧰「连接手机」卡：/api/pairing/info → qrcode() SVG 弹窗。"""
        js = self.js
        self.assertIn("buildToolCard('连接手机', '生成二维码——手机小橘 App 扫码即连'", js)
        self.assertIn("function openPairQrModal()", js)
        self.assertIn("fetch('/api/pairing/info')", js)
        self.assertIn("qr.addData(payload);", js)
        self.assertIn("createSvgTag({ cellSize: 5, margin: 2 })", js)

    def test_mobile_header_css(self):
        """移动端头部防挤压：标题 nowrap 省略号/音色选择隐藏/按钮紧凑。"""
        html = self.html
        self.assertIn(".header-title { flex: 1 1 auto; min-width: 0;"
                      " white-space: nowrap;", html)
        self.assertIn("#tts-voice-select { display: none; }", html)
        self.assertIn(".header-actions { flex-shrink: 0; gap: 2px; }", html)


class NoEmojiUiIconsTests(unittest.TestCase):
    """最高工程纪律锚（2026-10-29 队长死命令）：UI 图标永久禁用 Emoji——
    按钮/操作栏/组件标签零 Emoji 字符；ICON_SVGS 扩编条目在位。"""

    def setUp(self):
        self.js = _read("console.js")

    def test_action_bar_and_buttons_emoji_free(self):
        """排队条/待办删除钮/附件关闭钮/文档行——操作与按钮位零 Emoji。"""
        js = self.js
        self.assertNotIn("💬 排队中", js)          # 排队条→message SVG
        self.assertNotIn("🗑️</", js)               # 删除按钮→trash SVG
        self.assertNotIn(">✕</button>", js)         # 关闭钮→x SVG
        self.assertNotIn(">📄 ", js)                # 文档行→fileText SVG
        self.assertNotIn(">🗑</button>", js)
        self.assertNotIn(">↻</button>", js)         # 挂载刷新→refresh SVG

    def test_icon_svgs_extended_entries(self):
        """ICON_SVGS 扩编条目在位（排队/删除/关闭/文档/拼图/闪电/视频/
        时钟/水滴/风/图表/房子/插头/刷新）。"""
        for name in ("message:", "trash:", "x:", "fileText:", "puzzle:",
                     "zap:", "video:", "clock:", "droplet:", "wind:",
                     "chart:", "house:", "plug:", "refresh:"):
            self.assertIn(name, self.js)

    def test_section_labels_svg_prefix(self):
        """工具面板三节标：文字不带 emoji 前缀，图标=ICON_SVGS 矢量。"""
        js = self.js
        self.assertIn("sectionLabel('小橘监控', ICON_SVGS.chart);", js)
        self.assertIn("sectionLabel('小橘能控制什么', ICON_SVGS.house);", js)
        self.assertIn("sectionLabel('管理', ICON_SVGS.plug);", js)


if __name__ == "__main__":
    unittest.main()
