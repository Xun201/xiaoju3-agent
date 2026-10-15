# -*- coding: utf-8 -*-
"""#264 B2a 设置 tab 前端锚（源码级静态断言，仓库前端锚惯例）。

覆盖：
- index.html：tab-settings 按钮 + settings-pane（缺省 hidden）+ 保存/刷新
  按钮 + 渲染挂载点，且 pane 位于记录区与输入区之间（与终端页同构）；
- console.js：switchChatTab 注册表化（CHAT_TABS 映射 + 条目声明，非
  if/else 链——为 B2b 密钥页/B2c 开发者暗开关预留扩展位）；
- loadSettings：GET /api/settings + 竞态守卫 + 交渲染函数；
- saveSettings：POST {updates} + 403 → showToast 权限不足；
- renderSettingsItems：遍历 items 渲染、零键名硬编码（新增键零前端改动）。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _fn_body(src, name):
    """按花括号配对提取函数源码（function name(...) { ... }）。"""
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


class SettingsTabHtmlTests(unittest.TestCase):
    """index.html 结构锚。"""

    def test_tab_button_and_pane_present(self):
        """#264 B2d③ B 方案：tab 栏**无**「设置」按钮（入口=⚙️齿轮/桌宠
        菜单「设置」），settings-pane 保留（缺省 hidden）且含 ←返回/保存/
        刷新按钮与挂载点；pane 位于记录区与输入区之间（与终端页同构平级）。"""
        html = _read("index.html")
        self.assertNotIn('id="tab-settings"', html)
        self.assertIn('<div class="settings-pane" id="settings-pane" hidden>', html)
        self.assertIn('id="settings-back"', html)
        self.assertIn('id="settings-save"', html)
        self.assertIn('id="settings-refresh"', html)
        self.assertIn('id="settings-list"', html)
        # pane 位置：记录区（终端）之后、输入区之前——与终端页同构平级
        self.assertLess(html.index('id="settings-pane"'),
                        html.index('class="chat-input-area"'))
        self.assertGreater(html.index('id="settings-pane"'),
                           html.index('id="terminal-history"'))


    def test_gear_entry_replaces_minimize(self):
        """#264 B2d②：右上角 ⌄ → ⚙️ 齿轮=设置入口（title=设置）；旧
        console-minimize 在前端双文件禁绝（缩球入口已迁桌宠右键菜单）。"""
        html = _read("index.html")
        self.assertIn(
            '<button id="console-settings-entry" class="header-btn" title="设置">⚙️</button>',
            html)
        self.assertNotIn("console-minimize", html)
        self.assertNotIn("console-minimize", _read("console.js"))


class SettingsTabJsTests(unittest.TestCase):
    """console.js 行为契约锚（函数体级）。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("console.js")

    def test_switch_tab_is_registry(self):
        """切换=注册表：CHAT_TABS 映射含 settings 条目；switchChatTab 消费
        注册表（CHAT_TABS[tab]），旧 if/else 链（isTerminal 分支）不残留——
        B2b/B2c 新 tab 只加条目不改函数。"""
        self.assertIn("const CHAT_TABS = {", self.js)
        self.assertIn("settings: {", self.js)
        body = _fn_body(self.js, "switchChatTab")
        self.assertIn("CHAT_TABS[tab]", body)
        self.assertNotIn("isTerminal", body)

    def test_load_settings_get_contract(self):
        """loadSettings：GET /api/settings（B1 契约）+ 竞态守卫 + 交渲染。"""
        body = _fn_body(self.js, "loadSettings")
        self.assertIn("fetch('/api/settings')", body)
        self.assertIn("settingsFetchSeq", body)
        self.assertIn("renderSettingsItems(body)", body)

    def test_save_settings_post_contract(self):
        """B2c b 重构后契约：saveSettings 只做收集+danger 分流（danger→
        openTotpDialog），POST 提交移至 submitSettingsUpdates（body 携带
        updates+可选 totp）。"""
        body = _fn_body(self.js, "saveSettings")
        self.assertIn("SETTINGS_STATE.tiers[k] === 'danger'", body)
        self.assertIn("openTotpDialog(updates, dangerKeys)", body)
        self.assertIn("submitSettingsUpdates(updates, null)", body)
        sub = _fn_body(self.js, "submitSettingsUpdates")
        self.assertIn("method: 'POST'", sub)
        self.assertIn("'/api/settings'", sub)
        self.assertIn("if (totp) payload.totp = totp;", sub)

    def test_save_403_shows_toast(self):
        """403 响应 → showToast；totp_invalid → 带旧码重开 TOTP 卡；
        文案分流在 settingsDenyText（含权限不足/所需等级/TOTP 原因）。"""
        sub = _fn_body(self.js, "submitSettingsUpdates")
        self.assertIn("403", sub)
        self.assertIn("showToast", sub)
        self.assertIn("settingsDenyText(body)", sub)
        self.assertIn("openTotpDialog(updates", sub)   # totp_invalid 带旧码重开
        self.assertIn("totp_invalid", sub)
        deny = _fn_body(self.js, "settingsDenyText")
        self.assertIn("权限不足", deny)
        self.assertIn("level_insufficient", deny)

    def test_gear_click_binds_settings_and_pet_menu_regression(self):
        """#264 B2d② 回归：齿轮 click → switchChatTab('settings')；
        setPetMinimized 仍经 __xiaoju3Console 桥被桌宠菜单「缩小」调用
        （入口迁移≠功能删除）。"""
        js = _read("console.js")
        self.assertIn("getElementById('console-settings-entry')", js)
        self.assertIn("switchChatTab('settings')", js)
        self.assertIn("setPetMinimized: setPetMinimized", js)
        self.assertIn("b.setPetMinimized(true)", _read("desktop-pet.js"))

    def test_dev_mode_tap_and_totp_dialog(self):
        """#264 B2c：a 连点 7 次暗入口（按级分流 toast+🛠️ 会话徽标+审计）
        + b TOTP 卡（后果文案按项+6 位码+body.totp）+ c danger 组红标题。"""
        cjs = _read("console.js")
        # a 连点：计数 7 次触发+3s 重置+按级 toast+徽标+审计
        self.assertIn("function handleDevTap()", cjs)
        self.assertIn("if (devTapCount < 7) return;", cjs)
        self.assertIn("setTimeout(function () { devTapCount = 0; }, 3000)", cjs)
        # B2c 持久化拍板：解锁仪式（未解锁→unlocked+on 同写）/已解锁指路/
        # 徽标统一挂摘 applyDevBadges
        self.assertIn("开发者模式开关已在下方（设置页底部）", cjs)
        # 2026-10-13 拍板 B：解锁 toast 文案改 🔓（视觉反馈三件套之一）
        self.assertIn("🔓 开发者模式已解锁（设置页底部展开「开发者模式」）", cjs)
        self.assertIn("api.set_dev_pref(true, true)", cjs)
        self.assertIn("权限不足（Lv.' + level + '）", cjs)
        self.assertIn("function applyDevBadges(on)", cjs)
        self.assertIn("aboutLabel.textContent += ' 🛠️'", cjs)
        self.assertIn("权限不足（Lv.' + level + '）", cjs)
        self.assertIn("function applyDevBadges(on)", cjs)
        self.assertIn("aboutLabel.textContent += ' 🛠️'", cjs)
        self.assertIn("cardVer.textContent += ' 🛠️'", cjs)
        self.assertIn("aboutLabel.textContent = aboutLabel.textContent.replace(' 🛠️', '')", cjs)
        self.assertIn("api.dev_audit('dev_mode enter tap7 level=' + level)", cjs)
        self.assertIn("api.dev_audit('tap7 already-unlocked level=' + level)", cjs)
        self.assertIn("api.dev_audit('dev_mode ' + (on ? 'enter' : 'exit') + ' ' + (reason || ''))", cjs)   # 开关路径
        # b TOTP 卡：结构+后果文案+6 位码校验+body.totp+totp_invalid 重开
        self.assertIn("function openTotpDialog(updates, dangerKeys, prefill)", cjs)
        self.assertIn("🛠️ 高危操作验证", cjs)
        self.assertIn("DANGER_CONSEQUENCES", cjs)
        self.assertIn("改主模型会影响所有对话的模型调用", cjs)
        self.assertIn("if (!/^\\d{6}$/.test(code))", cjs)
        self.assertIn("closeTotpDialog();", cjs)
        self.assertIn("submitSettingsUpdates(updates, code);", cjs)
        # c danger 组标题红色
        self.assertIn("title.style.color = 'var(--color-danger, #e0433f)'", cjs)
        # B2c 收尾（用户拍板）：admin 组藏进开发者模式（dev_mode_on=false
        # 跳过渲染=藏显 UI 门；能不能改仍由后端 level 管=双门）
        self.assertIn("const devOn = DEV_STATE.mode_on === true;", cjs)
        self.assertIn("if (tier === 'admin' && !devOn) return;", cjs)
        self.assertIn("const DEV_STATE = { unlocked: false, mode_on: false };", cjs)
        # Python 侧审计接线
        py = _read("desktop_launcher.py")
        self.assertIn("def dev_audit(self, detail", py)
        self.assertIn('_audit({"action": "dev_mode"', py)

    def test_settings_about_entry_and_version_relocation(self):
        """#264 B2c 收尾（用户拍板）：①删右上角 header 版本号（前后端字面
        禁绝，/api/status 能力保留→window.__xiaoju3Version）②设置页底部
        改「关于」列表条目（左标题右箭头，click 弹 openAbout 卡）③连点
        入口迁居关于卡内版本号（事件委托，藏得更深=暗入口语义）。"""
        html = _read("index.html")
        self.assertNotIn('id="header-version"', html)
        self.assertNotIn('id="settings-version"', html)
        self.assertIn('id="settings-about"', html)   # 关于条目
        self.assertIn('class="settings-about-arrow"', html)   # 右箭头
        self.assertIn('.settings-about-row:hover', html)   # hover 高亮
        # B2c 修正（参照小米列表页）：普通一项——无独立块间距/分隔线，与
        # 上方表单项视觉连续
        self.assertIn('.settings-about-row { margin-top: 0;', html)
        # B2c 沉底修正：settings-list 去 chat-history 双类（后者 flex:1 撑满
        # 剩余空间把关于条目推底——真凶非 margin，是 flex 挤压）
        self.assertIn('<div class="settings-list" id="settings-list">', html)
        self.assertIn('<div class="settings-list" id="settings-list">', html)   # 无 chat-history 前缀（双类一刀切曾连滚动一起删）
        # 滚动恢复+自然排列双锚（B2c 修正）：容器 flex:1+overflow-y 占满可滚，
        # 内部项 flex-column 自然排列（不 space-between=关于不沉底）
        self.assertIn("overflow-y: auto;", html)
        self.assertIn("gap: 14px;", html)
        self.assertNotIn('border-top: 1px solid var(--color-border, #e0e4ec); cursor: pointer', html)
        cjs = _read("console.js")
        self.assertNotIn("header-version", cjs)
        self.assertNotIn("settings-version", cjs)
        self.assertIn("window.__xiaoju3Version = String(d.version)", cjs)   # 版本源保留
        self.assertIn("aboutRow.addEventListener('click', function () { openAbout(); })", cjs)
        self.assertIn("ver.className = 'about-version'", cjs)   # 卡内版本=连点载体
        self.assertIn("e.target.classList.contains('about-version')", cjs)   # 事件委托
        self.assertIn("cardVer.textContent += ' 🛠️'", cjs)   # 徽标挂卡内版本
        # B2c 持久化：开关行（unlocked 才显示/ON-OFF 独立持久化/F5 恢复无重置）
        self.assertIn("function buildDevSwitchRow()", cjs)
        self.assertIn("function applyDevSwitchRow()", cjs)
        self.assertIn("setDevMode(input.checked, 'switch')", cjs)
        self.assertIn("dev_unlocked", cjs)
        self.assertIn("dev_mode_on", cjs)
        self.assertNotIn("localStorage.setItem('xiaoju3_dev", cjs)   # 状态不走 localStorage

    def test_about_row_inside_scroll_container(self):
        """#264 B2c 修正（用户实测贴底不动）：关于条目必须在滚动容器
        （settings-list）**内部**——此前是 settings-pane 直接子项，滚动发生
        在列表内，它在滚动区外=视觉贴底（非 sticky/fixed，grep 零命中）。
        锚=DOM 嵌套关系 + 重渲染保活（innerHTML 清空先摘后挂回）。"""
        html = _read("index.html")
        list_start = html.index('<div class="settings-list" id="settings-list">')
        list_end = html.index('</div>' + chr(10) + '        </div>', list_start)
        seg = html[list_start:list_end]
        self.assertIn('id="settings-about"', seg)   # 关于在滚动容器内部
        cjs = _read("console.js")
        self.assertIn("aboutRow.remove()", cjs)    # 重渲染先摘
        self.assertIn("settingsListEl.appendChild(aboutRow)", cjs)   # 渲染后放回列表尾

    def test_settings_back_binding(self):
        """#264 B2d③ B 方案：设置页「← 返回」→ switchChatTab('console')；
        齿轮入口路径不变（switchChatTab('settings')）。"""
        js = _read("console.js")
        self.assertIn("getElementById('settings-back')", js)
        self.assertIn("settingsBackBtn.addEventListener('click'", js)
        self.assertIn("switchChatTab('console')", js)
        self.assertIn("switchChatTab('settings')", js)

    def test_no_dangling_tab_settings_refs(self):
        """#264 B2d③ 回归修复锚：tabSettingsBtn 残留引用禁绝——const 已删
        而旧 if(tabSettingsBtn) 绑定块曾残留，运行时 ReferenceError 打断
        IIFE 求值、其后齿轮/桥/返回绑定全部失效（node --check 抓不到：语法
        合法运行时才炸）。设置入口=⚙️齿轮（console-settings-entry）必须在线。"""
        js = _read("console.js")
        self.assertNotIn("tabSettingsBtn", js)
        self.assertIn("getElementById('console-settings-entry')", js)
        self.assertIn("settingsEntryBtn.addEventListener('click'", js)

    def test_render_iterates_without_hardcoded_keys(self):
        """渲染=遍历 items（.forEach），零键名硬编码——18 键集增减/扩白名单
        均无需改前端；分档表是唯一事实源（B1 设计取舍）。"""
        body = _fn_body(self.js, "renderSettingsItems")
        self.assertIn(".forEach", body)
        for key in ("USER_CITY", "USER_DISTRICT", "TTS_VOICE",
                    "CHILD_LOCK_ENABLED", "LOCAL_MODEL_SMALL", "DEVICE_TIER",
                    "LOCAL_MODEL", "XIAOJU3_PERSONALITY", "DEEPSEEK_API_KEY"):
            self.assertNotIn(key, body)


def test_help_intercept_case_insensitive():
    """B2c 后补：help 幻觉修复锚（用户发裸 help→先滑 LLM 产幻觉回执）——
    三处拦截词表（dashboard api_chat/_console_slash_intercept/QQ main.py）
    均须大小写不敏感+补裸词 help。"""
    dash = open("xiaoju3_dashboard.py", encoding="utf-8").read()
    main_src = open("main.py", encoding="utf-8").read()
    assert 'user_msg.strip().lower() in ("/help", "help", "菜单", "帮助", "指令")' in dash
    assert 'text.lower() in ("/help", "help", "菜单", "帮助", "指令")' in dash
    # #227 批 0：help 拦截词表迁 system_handler.py（源码锚跟迁）
    sys_src = open("system_handler.py", encoding="utf-8").read()
    assert 'command_text.lower() in ["/help", "help", "菜单", "帮助", "指令"]' in sys_src


if __name__ == "__main__":
    unittest.main()


class PersonaCardFrontendTests(unittest.TestCase):
    """批 4 人格卡前端锚（源码级静态，仓库前端锚惯例）：
    容器在位 / 加载契约+置灰预检 / 翻译红线+出界铁律锁。"""

    def test_container_in_settings_pane(self):
        html = _read("index.html")
        self.assertIn('id="persona-card"', html)
        # 位置（批 4 验收 Bug 1 回归锁）：容器必须在 settings-list 滚动
        # 容器**内部**——pane 直下（滚动区外）=页不可滚（关于条目同款
        # bug 复犯实锤 2026-10-15）
        i_list = html.index('id="settings-list"')
        i_card = html.index('id="persona-card"')
        i_keys = html.index('id="keys-pane"')
        self.assertTrue(i_list < i_card < i_keys)

    def test_post_persona_preserves_card(self):
        """批 4 验收 Bug 2 回归锁：POST 错误路径只 toast 保留卡片；
        成功路径用响应 level 重渲染（POST 响应必须带 level）。"""
        js = _read("console.js")
        body = _fn_body(js, "postPersona")
        self.assertIn("code === 403", body)
        self.assertIn("showToast", body)
        # 403/异常分支先 return，绝不落入 renderPersonaCard（防抹卡）
        self.assertLess(body.index("return;"), body.index("renderPersonaCard"))
        self.assertIn("body.level", body)
        # 渲染防御：无 level 字段不进置灰分支（响应形状滑档保险）
        rbody = _fn_body(js, "renderPersonaCard")
        self.assertIn("body.level !== undefined", rbody)

    def test_load_and_locked_contract(self):
        js = _read("console.js")
        self.assertIn("function loadPersonaCard()", js)
        self.assertIn("fetch('/api/persona/state')", js)
        self.assertIn("personaFetchSeq", js)   # 独立竞态守卫（不挤 settings）
        body = _fn_body(js, "renderPersonaCard")
        self.assertIn("level < 3", body)             # 权限预检
        self.assertIn("persona-locked", body)        # 置灰类
        locked_part = body.split("return;")[0]
        self.assertNotIn("addEventListener", locked_part)   # 置灰态零可点

    def test_translation_table_redlines_and_scope_lock(self):
        js = _read("console.js")
        self.assertIn("PERSONA_MODE_PHRASES", js)
        # 翻译红线：标签/临床词零容忍（用户化翻译铁律）
        for bad in ("人格障碍", "心理", "病理", "治疗", "纠正", "依赖型人格"):
            self.assertNotIn(bad, js, bad)
        # 出界铁律锁：人格函数体内禁现三态阶梯/触发层字样（那是别的批）
        for fn in ("renderPersonaCard", "loadPersonaCard"):
            fn_body = _fn_body(js, fn)
            for bad in ("三态阶梯", "checkpoint", "autonomous", "report"):
                self.assertNotIn(bad, fn_body, (fn, bad))


class PetHideOnSettingsTests(unittest.TestCase):
    """桌宠随设置族显隐（批 4 收尾补丁，2026-10-15）：类驱动同缩球态先例，
    settings/keys enter 加类、leave 移类，desktop-pet.js 零改动。"""

    def test_css_pairing_in_index(self):
        html = _read("index.html")
        self.assertIn("body.xiaoju3-settings-open .xiaoju-root"
                      " { display: none; }", html)
        self.assertIn("body.xiaoju3-pet-minimized .xiaoju-root", html)  # 先例同款

    def test_enter_add_leave_remove_both_panes(self):
        js = _read("console.js")
        self.assertEqual(
            js.count("classList.add('xiaoju3-settings-open')"), 2)   # settings+keys
        self.assertEqual(
            js.count("classList.remove('xiaoju3-settings-open')"), 2)

    def test_desktop_pet_js_untouched(self):
        """纯类驱动铁律：desktop-pet.js 零 display 控制改动。"""
        pet = _read("desktop-pet.js")
        self.assertNotIn("xiaoju3-settings-open", pet)
