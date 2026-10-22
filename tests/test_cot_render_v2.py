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
# 二轮拍板（2026-10-22）：直出思维流（对标 DeepSeek，折叠卡家族整体退役）
# ---------------------------------------------------------------------------

class ThinkLiveDirectTests(unittest.TestCase):
    """直出思维流契约：🧠 标签行+灰色小号思考行直接外冒，无箭头无折叠无
    二次点击；正文黑色粗体续流；流式与最终/历史/刷新共用同一 DOM 形态。"""

    @classmethod
    def setUpClass(cls):
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def test_live_block_builder(self):
        """buildThinkLiveBlock：🧠 标签行 + think-live-line 逐段行（splitThink
        StageLines 剥前缀），全 textContent 注入免 XSS。"""
        js = self.console_js
        start = js.index("function buildThinkLiveBlock")
        body = js[start:js.index("function buildThinkFallbackBlock", start)]
        self.assertIn("className = 'think-live'", body)
        self.assertIn("className = 'think-live-label'", body)
        self.assertIn("textContent = '🧠 思考过程'", body)
        self.assertIn("className = 'think-live-line'", body)
        self.assertIn("splitThinkStageLines(thinkText)", body)
        self.assertIn("row.textContent = seg.text", body)

    def test_collapsed_family_fully_retired(self):
        """折叠卡家族整体退役（反锚）：打字机/折叠链/开合/骨架构建器/
        think-pending 全部不存在——绝不折叠、绝无二次点击。"""
        js = self.console_js
        for token in ("startThinkTypewriter", "scheduleThinkCollapse",
                      "animateThinkCollapse", "toggleThinkCard",
                      "buildThinkCardEl", "buildThinkLineEl",
                      "hideBubbleUntilThinkDone", "showBubbleNow",
                      "THINK_TYPE_MS", "THINK_COLLAPSE_DELAY_MS",
                      "THINK_COLLAPSE_MS", "think-pending",
                      "animateThink"):
            self.assertNotIn(token, js)
        html = self.index_html
        for token in ("think-collapsed", "think-card", "think-pending",
                      "thinkLineFadeIn"):
            self.assertNotIn(token, html)

    def test_live_css_direct_out(self):
        """直出样式：灰色小号思考行 + 🧠 标签呼吸 + 骨架占位线 + 正文粗体
        （answer 正常黑字粗体续流）；错开淡入仅历史批渲染挂 .msg-enter。"""
        html = self.index_html
        self.assertIn(".think-live {", html)
        self.assertIn(".think-live-label {", html)
        self.assertIn(".think-live-line {", html)
        self.assertIn(".message.bot-message .bubble-content {\n            font-weight: 600;", html)
        self.assertIn(".message.msg-enter { animation: msgEnter 0.32s ease-out both; }", html)
        # 平衡换行微操：标签 balance / 正文 pretty
        self.assertIn("text-wrap: balance;", html)
        self.assertIn("text-wrap: pretty;", html)

    def test_adoption_channel_renamed_to_live(self):
        """done 收养通道改 thinkLiveEl：最终消息收养直出块（不重建）；
        done 无折叠调度（scheduleThinkCollapse 已退役）。"""
        js = self.console_js
        self.assertIn("adopted ? { thinkLiveEl: adopted } : null", js)
        self.assertIn("options.thinkLiveEl.classList.contains('think-live')", js)
        self.assertNotIn("scheduleThinkCollapse", js)

    def test_duration_label_on_live_block(self):
        """A1 耗时显示落直出块标签：已思考（用时 X 秒）。"""
        js = self.console_js
        self.assertIn("已思考（用时 ' + secs + ' 秒）", js)
        self.assertIn("const st = thinkCard && thinkCard.querySelector('.think-live-label');", js)


# ---------------------------------------------------------------------------
# 任务 2：1.5s 延迟折叠 + 300ms 过渡 + 点击再展开（2026-10-22 已随折叠卡退役）
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 任务 4：桌宠下线只留加速球
# ---------------------------------------------------------------------------

class PetOnlineRegressionTests(unittest.TestCase):
    """桌宠完整形态回归（2026-10-02）：desktop-pet.js 重新挂载。

    2026-10-01 曾按"右下角唯一悬浮元素"口径注释停载（任务 4）；本次恢复
    加载，最小化=桌宠缩球（body.xiaoju3-pet-minimized 才 display），控制台
    永不缩（PET_BALL_FIX_DESIGN）。"""

    @classmethod
    def setUpClass(cls):
        cls.index_html = _read("index.html")
        cls.console_js = _read("console.js")
        cls.pet_js = _read("desktop-pet.js")

    def test_desktop_pet_script_enabled(self):
        """desktop-pet.js 重新挂载：去掉 HTML 注释后（浏览器实际加载面）
        存在指向 desktop-pet.js 的 script 标签；console.js 仍正常加载。"""
        stripped = _strip_html_comments(self.index_html)
        self.assertIsNotNone(re.search(r"<script[^>]*desktop-pet\.js", stripped))
        self.assertIn('<script src="/console/desktop-pet.js"></script>', stripped)
        self.assertIn('<script src="/console/console.js"></script>', stripped)

    def test_mount_comment_updated_to_regression(self):
        """挂载点注释同步口径：旧的下线注释行已移除，注明回归日期与
        新口径（最小化=桌宠缩球，球跟桌宠原位）。"""
        html = self.index_html
        self.assertNotIn(
            "<!-- <script src=\"/console/desktop-pet.js\"></script> -->", html)
        self.assertIn("桌宠完整形态回归", html)
        self.assertIn("最小化=桌宠缩球", html)

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
        小橘半身像 /assets/pet/normal_half.png、最小化态显示规则（新类名）。"""
        html = self.index_html
        self.assertIn('id="xiaoju3-ball"', html)
        self.assertIn('src="/assets/pet/normal_half.png"', html)
        self.assertIn("#xiaoju3-ball {", html)
        self.assertIn("body.xiaoju3-pet-minimized #xiaoju3-ball", html)
        self.assertIn('id="console-settings-entry"', html)   # 齿轮设置入口（#264 B2d②；缩球入口=桌宠右键菜单「缩小」）

    def test_ball_logic_kept_in_console_js(self):
        """加速球交互逻辑（console.js）：可拖拽（位移平方>9 阈值、
        setPointerCapture）、球跟桌宠原位重放（getPos）、点击恢复互切。"""
        js = self.console_js
        section = _extract_span(js, "缩成加速球", "initConsoleBall();") \
            + js[js.index("initConsoleBall();"):]
        self.assertIn("function initConsoleBall", section)
        self.assertIn("const BALL_SIZE = 60", section)
        self.assertIn("if (dx * dx + dy * dy > 9) moved = true;", section)
        self.assertIn("setPointerCapture", section)
        self.assertIn("setPetMinimized(false);   // 未拖动＝点击恢复桌宠",
                      section)
        self.assertIn("getElementById('console-settings-entry')", section)   # #264 B2d②：齿轮=设置 tab

    def test_console_never_hides_and_new_class_anchors(self):
        """口径①反向锚（PET_BALL_FIX_DESIGN §6）：控制台隐藏规则不得回流
        （旧类名 index.html 全文件禁绝）；新类两锚=桌宠 .xiaoju-root 隐藏 +
        球显示。"""
        html = self.index_html
        self.assertNotIn("xiaoju3-minimized >", html)          # 旧隐藏规则禁回流
        self.assertNotIn("xiaoju3-minimized", html)            # 旧类名全文件退役
        self.assertIn(
            "body.xiaoju3-pet-minimized #xiaoju3-ball { display: block; }", html)
        self.assertIn(
            "body.xiaoju3-pet-minimized .xiaoju-root { display: none; }", html)

    def test_no_other_floating_pet_elements(self):
        """静态 HTML 口径：页面 img 仅剩加速球头像一张（桌宠形象由
        desktop-pet.js 运行时自建 .xiaoju-root 节点直挂 document.body，
        不新增静态节点）；孤儿空挂载点 #xiaoju3-root 已清理（2026-10-03
        真机教训：注释称"注入点"但实现从未使用），markup 侧不得回流。"""
        html = self.index_html
        stripped = _strip_html_comments(html)
        imgs = re.findall(r'<img[^>]*src="([^"]+)"', stripped)
        self.assertEqual(imgs, ["/assets/pet/normal_half.png"])   # 唯一静态图片=球头像
        self.assertNotIn('id="xiaoju3-root"', stripped)           # 孤儿挂载点禁回流
        # 加速球元素仍引用头像（资产保留在仓库且前端仍用）
        ball = re.search(r'<div id="xiaoju3-ball".*?</div>', html, flags=re.S)
        self.assertIsNotNone(ball)
        self.assertIn("/assets/pet/normal_half.png", ball.group(0))

    def test_hide_selector_matches_real_pet_node(self):
        """成对锁锚（2026-10-03 真机教训，本轮修复核心）：CSS 隐藏选择器
        必须与桌宠真实节点配对——桌宠是 desktop-pet.js 运行时自建的
        .xiaoju-root 节点（root.className 赋类 + document.body 直挂，非静态
        挂载点）；隐藏规则用 .xiaoju-root。谁改一边此锚必炸。"""
        html = self.index_html
        js = self.pet_js
        self.assertIn(
            "body.xiaoju3-pet-minimized .xiaoju-root { display: none; }", html)
        self.assertIn("root.className = 'xiaoju-root';", js)      # 创建侧：类名
        self.assertIn("document.body.appendChild(root)", js)      # 挂载侧：body 直挂
        self.assertNotIn("xiaoju3-root", _strip_html_comments(html))   # 旧 ID 禁回流（史档注释豁免）

    def test_position_initialized_only_once(self):
        """出生位只定一次锚（拖拽回弹修复）：initPosition 带 positionInitialized
        标志（先判后置）——换图 load（拖拽切全身像/松手切回半身像）不再重置
        坐标；隐藏态守卫在先（隐藏态不初始化也不置位）。"""
        js = self.pet_js
        self.assertIn("let positionInitialized = false;", js)
        guard_idx = js.index("if (positionInitialized) return;")
        set_idx = js.index("positionInitialized = true;")
        disp_idx = js.index("getComputedStyle(root).display === 'none'")
        self.assertLess(disp_idx, guard_idx)   # 隐藏态守卫在先（不初始化也不置位）
        self.assertLess(guard_idx, set_idx)    # 标志先判后置


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
        self.assertIn("#1f2937", js)                       # 深色兜底块背景
        self.assertIn('console.log("RENDERING_THINK_LIVE...")', js)
        self.assertIn('console.log("RAW_REPLY:", res.data.reply)', js)
        self.assertIn('console.log("PARSED_THINK:"', js)

    def test_render_entry_guard_untouched(self):
        """渲染入口仅由 think !== null 守卫（三条路径不变）：实时回复、
        刷新重生成（syncThinkCard）、历史回放。"""
        js = self.console_js
        self.assertIn("if (thinkParts.think !== null)", js)
        self.assertIn("syncThinkCard(msgEl, thinkParts.think)", js)
        self.assertIn("if (thinkText === null) return;", js)

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



class ThinkDurationDisplayTests(unittest.TestCase):
    """A1（#326 前置侦察）锚：思考耗时显示——首个 think 增量记时刻，
    done 收口算差写入直出思维流块标签"🧠 已思考（用时 X 秒）"。"""

    def test_think_start_ts_recorded_on_first_delta(self):
        src = _read("console.js")
        self.assertIn("let thinkStartTs = null;", src)
        self.assertIn("thinkStartTs = Date.now();", src)   # 首增量记时刻
        self.assertIn("st.textContent = '🧠 思考中…';", src)   # 流式期块态

    def test_duration_display_in_final_label(self):
        src = _read("console.js")
        self.assertIn("已思考（用时 ' + secs + ' 秒）", src)
        self.assertIn("querySelector('.think-live-label')", src)


if __name__ == "__main__":
    unittest.main()
