# -*- coding: utf-8 -*-
"""桌宠双版本状态机 + 内存进度条 + Edge-TTS 前端 单元测试（纯静态断言 + 可选 node 实跑，离线零依赖）。

覆盖（并行组 M3，2026-10-01；独立文件，不动 test_dashboard.py）：
- 任务 5 桌宠双版本状态机（desktop-pet.js）：PET_STATE_IMAGES 常量表
  （normal_half / normal_full / happy_full 预留），默认 normal_half（吸附
  右下角露上半身），拖拽中切 normal_full，释放吸附回边缘切回 normal_half；
  onerror 自动回退链（状态图 → 半身 → 官方 JPG → SVG 兜底气泡）不裂图；
  翻转吸附修复（updateFacingByPosition）调用点覆盖拖拽/吸附/resize；
  mix-blend-mode: multiply 去白底保留（对透明 PNG 无副作用）；
- 任务 7 内存进度条（index.html 结构 + console.js 驱动）：与 CPU 完全一致
  的 stat-bar-bg/stat-bar-fill 视觉进度条，>80% 变红 #e0433f、正常绿
  #2fa24c，由 /api/status 的 memory 字段驱动（2s 轮询）；
- 任务 6 前端 Edge-TTS 播放（console.js）：优先 POST /api/tts {text, voice}
  → 200 audio/mpeg blob → Audio 播放；网络/4xx/5xx/超时 → 自动降级既有
  浏览器 speechSynthesis（音色回退链与 emoji 剔除零回退）；音色下拉 =
  Edge 音色常量表（与后端 xiaoju3_dashboard.EDGE_VOICES 口径一致）+
  "浏览器 TTS（降级）"项；localStorage 键 xiaoju3_tts_voice 协议锁定：
  值为 Edge 音色名 → Edge 链（voice 参数即该值）；值含"浏览器"字样
  （浏览器项写入的哨兵值 '浏览器TTS（降级）'，同时阻断后端回填覆盖）、
  值为浏览器音色名等非 Edge 音色名、或两者皆空 → 浏览器降级链；
  /api/status 的 tts_voice 经既有 adoptBackendTTSVoice 在 localStorage
  为空时写回（Edge 初始默认衔接）。

测试方式：静态断言（源码标记切片）+ 素材文件存在性 + node --check 语法
门（无 node 自动跳过）+ node 实跑音色键值协议（提取真实源码片段喂桩）。
零回退哨兵：splitThinkBlock / RAW_REPLY 等诊断日志 / CQ 表情 / 系统消息
工具栏 / emoji 剔除 / WebAudio 音效在本轮改动中不受影响。
"""
import os
import shutil
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


def _node_available():
    return shutil.which("node") is not None


# ---------------------------------------------------------------------------
# 任务 5：桌宠双版本状态机（desktop-pet.js）
# ---------------------------------------------------------------------------

class PetDualStateImagesTests(unittest.TestCase):
    """双版本状态图常量表与默认态。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("desktop-pet.js")

    def test_pet_state_images_table(self):
        """PET_STATE_IMAGES 常量表：normal_half / normal_full / happy_full
        （情绪扩展预留位）三键齐全，路径均指向 /assets/pet/。"""
        js = self.js
        start = js.index("const PET_STATE_IMAGES = {")
        block = js[start:js.index("};", start)]
        for key in ("normal_half", "normal_full", "happy_full"):
            self.assertIn(key + ":", block)
        self.assertIn("'/assets/pet/normal_half.png'", block)
        self.assertIn("'/assets/pet/normal_full.png'", block)
        self.assertIn("'/assets/pet/happy_full.png'", block)

    def test_default_state_is_normal_half(self):
        """默认半身像：PET_DEFAULT_STATE = 'normal_half'，img 初始 src 取
        表内默认态（吸附右下角只露上半身）。"""
        js = self.js
        self.assertIn("const PET_DEFAULT_STATE = 'normal_half'", js)
        self.assertIn("img.src = PET_STATE_IMAGES[PET_DEFAULT_STATE]", js)
        # 初始状态变量与默认态一致
        self.assertIn("let petState = PET_DEFAULT_STATE", js)

    def test_drag_switches_to_full(self):
        """拖拽中切全身：pointermove 内超过拖拽阈值（位移平方>9）触发
        setPetState('normal_full')——点击（未超阈值）不换装。"""
        js = self.js
        move = js.index("addEventListener('pointermove'")
        seg = js[move:js.index("addEventListener('pointerup'", move)]
        self.assertIn("dx * dx + dy * dy > 9", seg)
        self.assertIn("setPetState('normal_full')", seg)
        # 全身切换在阈值判断块内（先判阈值再换装）
        self.assertLess(seg.index("dx * dx + dy * dy > 9"),
                        seg.index("setPetState('normal_full')"))

    def test_release_snaps_back_to_half(self):
        """释放并吸附到边缘后切回半身：pointerup 内 snapToEdge 之后
        setPetState('normal_half')。"""
        js = self.js
        up = js.index("addEventListener('pointerup'")
        seg = js[up:js.index("addEventListener('resize'", up)]
        self.assertIn("snapToEdge();", seg)
        self.assertIn("setPetState('normal_half')", seg)
        self.assertLess(seg.index("snapToEdge();"),
                        seg.index("setPetState('normal_half')"))

    def test_onerror_fallback_chain_no_broken_image(self):
        """onerror 回退链（绝不裂图）：状态图失败 → 回退 normal_half →
        官方 JPG（/assets/DSniang1.jpg 兜底）→ SVG 兜底气泡（img-ok 移除）；
        失败 URL 记入 Set 防死循环。"""
        js = self.js
        self.assertIn("img.addEventListener('error'", js)
        err = js.index("img.addEventListener('error'")
        seg = js[err:js.index("img.addEventListener('load'", err)]
        self.assertIn("failedStateUrls.add", seg)                    # 失败登记防循环
        self.assertIn("setPetState('normal_half')", seg)             # ① 回退半身
        self.assertIn("img.src = PET_FALLBACK_IMAGE", seg)           # ② 官方 JPG 兜底
        self.assertIn("refreshImgMode()", seg)                       # ③ SVG 兜底气泡
        # 兜底常量与既有素材可达性哨兵（test_dashboard 口径）：官方 JPG 保留在链上
        self.assertIn("const PET_FALLBACK_IMAGE = '/assets/DSniang1.jpg'", js)
        self.assertNotIn("DSniang1.png", js)

    def test_emotion_extension_interface(self):
        """情绪扩展接口：setPetState 按表挂载（未登记状态拒绝），对外暴露
        window.xiaoju3SetPetState；root.dataset.petState 记录当前状态。"""
        js = self.js
        start = js.index("function setPetState")
        body = js[start:js.index("window.xiaoju3SetPetState", start)]
        self.assertIn("if (!url) return false", body)                # 未登记拒绝
        self.assertIn("root.dataset.petState = next", body)          # 状态可观测
        self.assertIn("window.xiaoju3SetPetState = setPetState", js)

    def test_flip_snap_regression_kept(self):
        """翻转吸附修复零回退：面向由中心 x 相对屏幕中线判定，调用点覆盖
        拖拽（pointermove）/ 吸附后重算（pointerup）/ resize / 初始化。"""
        js = self.js
        self.assertIn("function updateFacingByPosition()", js)
        self.assertIn("window.innerWidth / 2", js)
        # 拖拽、pointerup、resize、initPosition 四处调用（≥4 处 + 1 处定义）
        self.assertGreaterEqual(js.count("updateFacingByPosition()"), 4)

    def test_multiply_blend_kept_for_png(self):
        """mix-blend-mode: multiply 去白底保留（对透明背景 PNG 无副作用），
        且声明在 .xiaoju-root（fixed 容器堆叠上下文口径不变）。"""
        marker = "style.textContent = `"
        start = self.js.index(marker) + len(marker)
        style = self.js[start:self.js.index("`;", start)]
        self.assertIn("mix-blend-mode: multiply", style)

    def test_pet_assets_on_disk(self):
        """素材存在性：assets/pet/normal_half.png 与 normal_full.png 已生成
        （占位 = DSniang1.jpg 字节副本，浏览器按内容解析、扩展名无关）。"""
        for name in ("normal_half.png", "normal_full.png"):
            path = os.path.join(PROJECT_ROOT, "assets", "pet", name)
            self.assertTrue(os.path.isfile(path), path)
            self.assertGreater(os.path.getsize(path), 0, path)
        with open(os.path.join(PROJECT_ROOT, "assets", "DSniang1.jpg"), "rb") as f:
            jpg = f.read()
        with open(os.path.join(PROJECT_ROOT, "assets", "pet", "normal_half.png"), "rb") as f:
            self.assertEqual(f.read(), jpg, "占位图应为 DSniang1.jpg 字节副本")

    def test_assets_md_dual_state_doc(self):
        """ASSETS.md：双版本机制说明 + 用户指引（即梦 AI 透明背景 PNG 替换、
        文件名不变）；既有透明化说明段落零回退。"""
        md = _read(os.path.join("assets", "ASSETS.md"))
        self.assertIn("双版本状态机说明", md)
        self.assertIn("PET_STATE_IMAGES", md)
        self.assertIn("assets/pet/normal_half.png", md)
        self.assertIn("assets/pet/normal_full.png", md)
        self.assertIn("透明背景 PNG", md)          # 用户指引：绝对无白边做法
        self.assertIn("即梦 AI", md)
        self.assertIn("字节副本", md)               # 占位口径如实记录
        # 既有透明化说明（test_pet_desktop 口径）不被本轮改动破坏
        self.assertIn("透明化说明", md)
        self.assertIn("mix-blend-mode", md)
        self.assertIn("透明通道 PNG", md)
        self.assertIn("文件名保持不变", md)


# ---------------------------------------------------------------------------
# 任务 7：内存进度条（index.html 结构 + console.js 驱动）
# ---------------------------------------------------------------------------

class MemoryProgressBarTests(unittest.TestCase):
    """内存占用与 CPU 完全一致的视觉进度条（核实结论：结构/驱动/阈值
    齐全，本轮以测试锁定，防回归）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")
        cls.js = _read("console.js")

    def _stat_item(self, text_id):
        """提取含指定 id 的 stat-item 块（进度条结构所在）。"""
        html = self.html
        start = html.index('id="%s"' % text_id)
        start = html.rindex("<div class=\"stat-item\">", 0, start)
        return html[start:html.index("</div>\n        </div>", start)]

    def test_mem_bar_structure_matches_cpu(self):
        """index.html：内存与 CPU 同构的 stat-bar-bg/stat-bar-fill 进度条
        结构（mem-text/mem-bar id 与 cpu-* 对齐）。"""
        for token in ('id="mem-text"', 'id="mem-bar"',
                      'id="cpu-text"', 'id="cpu-bar"'):
            self.assertIn(token, self.html)
        cpu_item = self._stat_item("cpu-text")
        mem_item = self._stat_item("mem-text")
        for structural in ('class="stat-label"', 'class="stat-bar-bg"',
                           'class="stat-bar-fill"', 'style="width: 0%;"'):
            self.assertIn(structural, cpu_item, structural)
            self.assertIn(structural, mem_item, structural)

    def test_mem_bar_css_shared_with_cpu(self):
        """进度条样式为 CPU/内存共用同一组类（缺样式环节不存在）：
        .stat-bar-bg 底槽 + .stat-bar-fill 填充 + width/background 过渡。"""
        css = self.html[self.html.index("<style>"):self.html.index("</style>")]
        self.assertIn(".stat-bar-bg", css)
        self.assertIn(".stat-bar-fill", css)
        fill = css[css.index(".stat-bar-fill"):css.index(".stat-value")]
        self.assertIn("width", fill)
        self.assertIn("background-color", fill)

    def test_mem_bar_driven_by_api_status_memory(self):
        """console.js：fetchStatus 消费 /api/status 的 memory 字段渲染
        mem-text/mem-bar（2s 轮询，加载即请求一次）。尾巴 H：经 applyBar
        三档变色（与 CPU 同一阈值常量、独立判定）。"""
        js = self.js
        self.assertIn("fetch('/api/status')", js)
        self.assertIn("setInterval(fetchStatus, 2000)", js)
        start = js.index("function fetchStatus")
        body = js[start:js.index("// ==================== 2.", start)]
        self.assertIn("getElementById('mem-text')", body)
        self.assertIn("getElementById('mem-bar')", body)
        self.assertIn("memText.textContent = d.memory + '%'", body)
        self.assertIn("applyBar(memBar, d.memory)", body)

    def test_mem_bar_three_level_thresholds(self):
        """尾巴 H：三档阈值常量与三档 CSS 类（<60 绿 / 60–85 黄 / >85 红）。"""
        js = self.js
        self.assertIn("const BAR_THRESHOLDS = { mid: 60, high: 85 };", js)
        self.assertIn("barEl.classList.add('bar-' + level)", js)
        css = self.html[self.html.index("<style>"):self.html.index("</style>")]
        for cls in (".stat-bar-fill.bar-low", ".stat-bar-fill.bar-mid",
                    ".stat-bar-fill.bar-high"):
            self.assertIn(cls, css)

    def test_mem_bar_threshold_red(self):
        """尾巴 H 三档口径：高档红 #e0433f、低档绿 #2fa24c——内存与 CPU
        同一阈值常量（BAR_THRESHOLDS），经 applyBar 统一驱动。"""
        js = self.js
        self.assertIn("const BAR_COLORS = { low: '#2fa24c', mid: '#eab308', high: '#e0433f' };", js)
        self.assertIn("applyBar(memBar, d.memory)", js)
        self.assertIn("applyBar(cpuBar, d.cpu)", js)


# ---------------------------------------------------------------------------
# 任务 6 前端：Edge-TTS 播放链路与降级（console.js）
# ---------------------------------------------------------------------------

class EdgeTTSFrontendTests(unittest.TestCase):
    """Edge-TTS 优先、浏览器 speechSynthesis 自动降级的朗读链路。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_edge_voice_table(self):
        """Edge 音色常量表：晓晓-温柔女声（zh-CN-XiaoxiaoNeural）居首
        （后端默认），小艺/晓伊（zh-CN-XiaoyiNeural）在表，表内 voice id
        与后端 xiaoju3_dashboard.EDGE_VOICES 对齐。"""
        js = self.js
        start = js.index("const EDGE_TTS_VOICES = [")
        block = js[start:js.index("];", start)]
        self.assertIn("'zh-CN-XiaoxiaoNeural'", block)   # 默认音色必须收录
        self.assertIn("晓晓-温柔女声", block)
        self.assertIn("'zh-CN-XiaoyiNeural'", block)
        self.assertIn("zh-CN-XiaomoNeural", block)       # 后端表内其余音色对齐
        self.assertIn("zh-CN-XiaoqiuNeural", block)
        self.assertLess(block.index("zh-CN-XiaoxiaoNeural"),
                        block.index("zh-CN-XiaoyiNeural"))   # 默认居首

    def test_tts_fetch_call_contract(self):
        """POST /api/tts 契约：fetch 携带 body JSON {text, voice}，voice
        参数取当前 Edge 音色；非 2xx 抛错走降级；blob 接收。"""
        js = self.js
        self.assertIn("fetch('/api/tts'", js)
        start = js.index("function requestEdgeTTS")
        body = js[start:js.index("function playAudioBlob", start)]
        self.assertIn("method: 'POST'", body)
        self.assertIn("JSON.stringify({ text: text, voice: voice })", body)
        self.assertIn("if (!res.ok) throw", body)        # 4xx/5xx → 失败
        self.assertIn("res.blob()", body)

    def test_blob_audio_playback(self):
        """blob → Audio 播放：URL.createObjectURL + new Audio + play，
        播完/出错释放对象 URL；Audio 单例防连点叠音。"""
        js = self.js
        start = js.index("function playAudioBlob")
        body = js[start:js.index("function speakWithBrowserTTS", start)]
        for token in ("URL.createObjectURL", "new Audio()", "edgeAudio.play()",
                      "URL.revokeObjectURL", "edgeAudio.pause()"):
            self.assertIn(token, body)

    def test_browser_tts_fallback_chain_kept(self):
        """降级链零回退：speakWithBrowserTTS 保留清队列防连点、utter.lang、
        回退链音色（pickTTSVoice）、无音色不设 utter.voice。"""
        js = self.js
        start = js.index("function speakWithBrowserTTS")
        body = js[start:js.index("window.toggleLike", start)]
        for token in ("window.speechSynthesis.cancel()", "new SpeechSynthesisUtterance(text)",
                      "utter.lang = 'zh-CN'", "pickTTSVoice()",
                      "if (voice) utter.voice = voice;", "speechSynthesis.speak(utter)"):
            self.assertIn(token, body)

    def test_playmsg_edge_first_auto_fallback(self):
        """playMsg：Edge 模式 → requestEdgeTTS → playAudioBlob，.catch 自动
        降级 speakWithBrowserTTS（网络/4xx/5xx/超时/播放失败全覆盖）；浏览器
        模式原链直走。"""
        js = self.js
        start = js.index("window.playMsg = function")
        body = js[start:js.index("const EDGE_TTS_TIMEOUT_MS", start)]
        self.assertIn("resolveTTSMode()", body)
        self.assertIn("plan.mode !== 'edge'", body)
        self.assertIn("requestEdgeTTS(speakText, plan.voice)", body)
        self.assertIn(".catch(() => speakWithBrowserTTS(speakText))", body)

    def test_emoji_strip_before_both_channels(self):
        """朗读文本先经 emoji 剔除再进链路（剔除在 playMsg 入口统一做，
        两条链路共用）；stripEmojiForTTS 全文件仍只有定义 + playMsg 两处
        （test_cot_frontend 口径锁定）。"""
        js = self.js
        self.assertEqual(js.count("stripEmojiForTTS("), 2)
        start = js.index("window.playMsg = function")
        self.assertIn("stripEmojiForTTS(text)", js[start:])

    def test_edge_tts_timeout(self):
        """超时容错：AbortController 8s 超时（超时即失败 → 自动降级），
        无 AbortController 的旧浏览器静默跳过（不崩）。"""
        js = self.js
        self.assertIn("EDGE_TTS_TIMEOUT_MS = 8000", js)
        start = js.index("function requestEdgeTTS")
        body = js[start:js.index("function playAudioBlob", start)]
        self.assertIn("typeof AbortController === 'function'", body)
        self.assertIn("ctrl.abort()", body)

    def test_voice_selector_edge_list_plus_browser_item(self):
        """音色下拉升级：Edge 音色列表 + "浏览器 TTS（降级）"项（值含"浏览
        器"字样的哨兵值，走降级链且阻断后端回填）；选中项按键值协议回显；
        既有挂载点/写回/回显机制零回退。"""
        js = self.js
        start = js.index("function refreshVoiceSelector")
        end = js.index("if (window.speechSynthesis)", start)
        body = js[start:end]
        self.assertIn("EDGE_TTS_VOICES.forEach", body)          # Edge 音色组
        self.assertIn("browserOpt.value = '浏览器TTS（降级）'", body)   # 协议②哨兵值
        self.assertIn("isEdgeTTSVoice(storedVoice)\n            ? storedVoice : '浏览器TTS（降级）'",
                      body)                                     # 回显回落浏览器项
        # 既有机制哨兵（test_cot_frontend 口径）
        for token in (".chat-header .header-actions", "createElement('select')",
                      "listZhVoices()", "addEventListener('change'",
                      "localStorage.setItem(TTS_VOICE_KEY, name)",
                      "localStorage.removeItem(TTS_VOICE_KEY)", "pickTTSVoice()"):
            self.assertIn(token, body)


class TTSVoiceKeyProtocolTests(unittest.TestCase):
    """localStorage 键值协议（xiaoju3_tts_voice）与后端 tts_voice 衔接。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_key_unchanged(self):
        """键沿用 xiaoju3_tts_voice（既有回退链/写回链零回退）。"""
        self.assertIn("const TTS_VOICE_KEY = 'xiaoju3_tts_voice'", self.js)

    def test_protocol_resolution_order(self):
        """协议实现：resolveTTSMode 先取 localStorage（getStoredTTSVoiceName）
        再 /api/status 下发值（backendTTSVoice），命中 Edge 音色名 → Edge 链
        （voice = 该值）；否则浏览器降级链（pickTTSVoice）。"""
        js = self.js
        start = js.index("function resolveTTSMode")
        body = js[start:js.index("// 音色下拉菜单", start)]
        i_stored = body.index("getStoredTTSVoiceName()")
        i_backend = body.index("backendTTSVoice")
        i_edge = body.index("isEdgeTTSVoice(stored)")
        self.assertLess(i_stored, i_backend)          # localStorage 优先
        self.assertLess(i_backend, i_edge)            # Edge 命中判定在后
        self.assertIn("mode: 'edge', voice: stored", body)
        # 2026-10-01 协议口径升级：browser 分支返回音色名称字符串（对象解包 .name）
        self.assertIn("mode: 'browser', voice: (v && v.name) ? v.name : v", body)

    def test_is_edge_voice_membership(self):
        """isEdgeTTSVoice：按 EDGE_TTS_VOICES 表内音色名精确匹配。"""
        js = self.js
        start = js.index("function isEdgeTTSVoice")
        body = js[start:js.index("function resolveTTSMode", start)]
        self.assertIn("EDGE_TTS_VOICES.some(v => v.name === name)", body)

    def test_browser_keyword_routes_to_fallback(self):
        """值含"浏览器"字样 → 降级链：浏览器项写入哨兵值 '浏览器TTS（降级）'
        （真值同时阻断 adoptBackendTTSVoice 在 2s 轮询中回填覆盖用户选择），
        协议在代码注释中显式声明。"""
        js = self.js
        self.assertIn("含\"浏览器\"字样", js)          # 协议注释锁定
        self.assertIn("'浏览器TTS（降级）'", js)       # 哨兵值（选项 value 与回显）
        start = js.index("function resolveTTSMode")
        body = js[start:js.index("// 音色下拉菜单", start)]
        self.assertIn("if (stored && isEdgeTTSVoice(stored))", body)  # 非表内值直接走 browser

    def test_backend_tts_voice_initial_default_kept(self):
        """/api/status 的 tts_voice（.env TTS_VOICE）仍经 adoptBackendTTSVoice
        在 localStorage 为空时写回——后端配置 Edge 音色名即成为 Edge 初始默认。"""
        js = self.js
        self.assertIn("adoptBackendTTSVoice(d.tts_voice)", js)
        start = js.index("function adoptBackendTTSVoice")
        body = js[start:js.index("const EDGE_TTS_VOICES", start)]
        self.assertIn("!getStoredTTSVoiceName()", body)
        self.assertIn("localStorage.setItem(TTS_VOICE_KEY, val)", body)


# ---------------------------------------------------------------------------
# node 实跑（可选）：语法门 + 音色键值协议行为锁定
# ---------------------------------------------------------------------------

@unittest.skipUnless(_node_available(), "环境无 node，跳过 JS 实跑（静态断言已覆盖）")
class NodeLiveRunTests(unittest.TestCase):
    """node 实跑：JS 语法门 + 提取真实源码片段验证键值协议行为。"""

    def _run_node(self, script):
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8")

    def test_js_syntax_gate(self):
        """node --check：console.js 与 desktop-pet.js 语法合法（非法 JS 会让
        整个前端瘫痪，此处提前现形）。"""
        for name in ("console.js", "desktop-pet.js"):
            proc = subprocess.run(["node", "--check",
                                   os.path.join(PROJECT_ROOT, name)],
                                  capture_output=True, timeout=60)
            self.assertEqual(proc.returncode, 0,
                             "%s: %s" % (name, proc.stderr.decode("utf-8", "replace")))

    def test_voice_key_protocol_behavior(self):
        """键值协议行为（提取真实 resolveTTSMode/isEdgeTTSVoice/EDGE_TTS_VOICES
        片段 + 桩替代 localStorage 与浏览器音色链）：
        - Edge 音色名（localStorage 或后端 tts_voice）→ Edge 链且 voice 带上；
        - 含"浏览器"字样的哨兵值 / 浏览器音色名 / 全空 → 浏览器降级链；
        - localStorage 优先于后端下发值。"""
        js = _read("console.js")
        chunk = js[js.index("const EDGE_TTS_VOICES"):js.index("// 音色下拉菜单")]
        script = (
            "var getStoredTTSVoiceName = function () { return __stored; };\n"
            + "var pickTTSVoice = function () { return 'stub-browser-voice'; };\n"
            + chunk + "\n"
            + "var cases = [\n"
            + "  // [stored, backendTTSVoice, 期望 mode, 期望 voice]\n"
            + "  ['zh-CN-XiaoxiaoNeural', '',                   'edge',    'zh-CN-XiaoxiaoNeural'],\n"
            + "  ['zh-CN-XiaoyiNeural',  'zh-CN-XiaomoNeural',  'edge',    'zh-CN-XiaoyiNeural'],\n"
            + "  [null,                  'zh-CN-XiaomoNeural',  'edge',    'zh-CN-XiaomoNeural'],\n"
            + "  [null,                  '',                    'browser', 'stub-browser-voice'],\n"
            + "  ['浏览器TTS（降级）',    'zh-CN-XiaomoNeural',  'browser', 'stub-browser-voice'],\n"
            + "  ['Google 普通话',        '',                    'browser', 'stub-browser-voice'],\n"
            + "];\n"
            + "var bad = [];\n"
            + "cases.forEach(function (c) {\n"
            + "  __stored = c[0]; backendTTSVoice = c[1];\n"
            + "  var plan = resolveTTSMode();\n"
            + "  if (plan.mode !== c[2] || plan.voice !== c[3]) {\n"
            + "    bad.push(JSON.stringify({ stored: c[0], backend: c[1],\n"
            + "                              got: plan.mode + '/' + plan.voice,\n"
            + "                              want: c[2] + '/' + c[3] }));\n"
            + "  }\n"
            + "});\n"
            + "console.log(JSON.stringify({ ok: bad.length === 0, bad: bad }));\n"
        )
        out = json_loads(self._run_node(script))
        self.assertTrue(out["ok"], msg=str(out["bad"]))


def json_loads(text):
    """标准库 json 的薄封装（保持用例主体简洁）。"""
    import json
    return json.loads(text)


# ---------------------------------------------------------------------------
# 零回退哨兵：思维链 / CQ 表情 / 诊断日志 / 工具栏 / 音效不受本轮改动影响
# ---------------------------------------------------------------------------

class FrontendNoRegressionSentinelTests(unittest.TestCase):
    """并行改动零回退哨兵（splitThinkBlock 全部容错 / 诊断日志 / CQ 表情 /
    系统消息工具栏 / emoji 剔除 / WebAudio 音效 / 余额气泡）。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.pet_js = _read("desktop-pet.js")
        cls.index_html = _read("index.html")

    def test_console_cot_and_diagnostic_sentinels(self):
        js = self.console_js
        for token in ("function splitThinkBlock", "RAW_REPLY:", "PARSED_THINK:",
                      "RENDERING_THINK_CARD", "CoT Render Error",
                      "think-card", "startThinkTypewriter",
                      "BARE_ACTION_RE", "loadHistory", "showToast",
                      "escapeHtml", "active-like", "active-dislike",
                      "mountSystemToolbar", "source-badge"):
            self.assertIn(token, js)
        self.assertNotIn("alert(", js)           # 不回退到 alert 占位
        self.assertNotIn("开发中", js)

    def test_console_cq_and_tts_strip_sentinels(self):
        js = self.console_js
        for token in ("CQ_FACE_EMOJI", "[CQ:face,id=", "renderCQFace",
                      "TTS_EMOJI_RE", "/^zh/i.test(String(v.lang || ''))",
                      "isFemaleZhVoice", "TTS_FEMALE_HINTS", "voiceschanged"):
            self.assertIn(token, js)

    def test_pet_specs_sentinels(self):
        js = self.pet_js
        for token in ("window.__xiaoju3Pet", "mix-blend-mode: multiply",
                      "SNAP_THRESHOLD = 24", "snapToEdge", "facing-right",
                      "xiaoju-flip", "scaleX(-1)", "PET_LINES", "img-ok",
                      "xiaoju-overlay", "xiaoju-pop", "dx * dx + dy * dy > 9",
                      "scaleY(0.88) scaleX(1.05)", "createOscillator",
                      "今日已用", "5003"):
            self.assertIn(token, js)
        self.assertNotIn("5005", js)

    def test_no_external_resources(self):
        """离线优先：index.html 无外网 script/link 引用，前端 JS 无外网
        fetch/资源引用（xmlns 命名空间等 W3C 标准串除外）。"""
        self.assertNotIn('<script src="http', self.index_html)
        self.assertNotIn('href="http', self.index_html)
        for js in (self.console_js, self.pet_js):
            self.assertNotIn("fetch('http", js)
            self.assertNotIn('fetch("http', js)
            self.assertNotIn('src = "http', js)
            self.assertNotIn("src = 'http", js)


if __name__ == "__main__":
    unittest.main()
