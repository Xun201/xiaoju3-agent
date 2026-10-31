# -*- coding: utf-8 -*-
"""移动端断连根治（netfix 2026-10-31 P0-2）回归锚。

背景（三路审查实锤）：APK 内 BASE='' 时同源探活 fetch('/api/health') 被
Capacitor WebViewLocalServer '**' 通配+html5mode 劫持成 200+index.html，
r.json() 必炸 → 永假 → 15s 一轮永久离线死循环；且 v2.2.x 旧壳扫码配对
写的 xj3_api_base 换 mobile 壳后零迁移成孤儿数据。

本文件两类锚：
1) 静态锚（语句形态，非文本子串——docstring/注释误触前科在案）：
   旧键迁移幂等 / 空基址守卫不发虚空请求 / 配对门在位 / 诊断面板单例。
2) node 运行时烟雾（test_streamcard_runtime_smoke.py 同款）：最小 DOM 桩
   真跑 core+mobile.js——空 base+Capacitor 环境零 fetch 且配对门出现、
   pairConnect 落键重载、旧键迁移+二次执行幂等+新键优先、探活失败类别
   透出。环境无 node 跳过。

🔴 红线守望：探活保持 HTTP /api/health 链——mDNS/zeroconfig 禁入
   linkCheck（RS1 的 _dev/relay 演示件与前端网络栈零接线，本批不许接线）。
"""
import json
import os
import shutil
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), encoding="utf-8") as f:
        return f.read()


def _span(text, start_marker, end_marker):
    """语句形态 span 提取（锚函数体/区块，防注释同形词误触）。"""
    i = text.index(start_marker)
    return text[i:text.index(end_marker, i)]


def _code_only(block):
    """剥离注释行（* / // /* 开头）——锚只对语句形态断言，注释里的同形
    词不算数（批 4/心理锚误触前科，2026-10-15 规范）。"""
    lines = []
    for ln in block.splitlines():
        t = ln.strip()
        if t.startswith("*") or t.startswith("/*") or t.startswith("//"):
            continue
        lines.append(ln)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 一、静态锚：BASE 解析链 + 旧键迁移（幂等）
# ---------------------------------------------------------------------------

class BaseMigrationAnchorTests(unittest.TestCase):
    """旧键 xj3_api_base→xj3_mobile_base 迁移：一次性+幂等+不删旧键。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("mobile.js")
        cls.html = _read("mobile.html")

    def test_migration_chain_in_source_and_inline(self):
        """迁移链在 mobile.js 源件与 mobile.html 内联段双在位（三处同步纪律：
        APK 执行的是内联版，内联缺=修复没进包）。"""
        chain = "localStorage.setItem('xj3_mobile_base', legacy)"
        self.assertIn(chain, self.js)
        self.assertIn(chain, self.html)

    def test_migration_idempotent_order(self):
        """幂等锚（语句顺序）：新键 saved 早退必须先于旧键读取——新键已有
        值时永不重迁；且旧键保留不删（回滚旧 APK 配对不丢）。"""
        base_block = _span(self.js, "var BASE = (function () {", "})();")
        saved_at = base_block.index("if (saved) {")
        legacy_at = base_block.index("localStorage.getItem('xj3_api_base')")
        self.assertLess(saved_at, legacy_at,
                        "迁移必须在新键早退之后（否则每次加载重写新键=不幂等）")
        self.assertNotIn("removeItem('xj3_api_base')", self.js,
                         "旧键不得删除（回滚 v2.2.x APK 配对保留）")

    def test_saved_key_precedence(self):
        """新键优先：迁移只在新键为空时发生（回归锚防"旧值复活"）。"""
        base_block = _span(self.js, "var BASE = (function () {", "})();")
        self.assertIn("var saved = localStorage.getItem('xj3_mobile_base');",
                      base_block)
        self.assertIn("if (saved) {", base_block)


# ---------------------------------------------------------------------------
# 二、静态锚：空基址守卫（不发虚空请求）+ 配对门 + 诊断面板
# ---------------------------------------------------------------------------

class EmptyBaseGuardAnchorTests(unittest.TestCase):
    """空 base 兜底=唤起配对门，绝不静默滑进永久离线。"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("mobile.js")
        cls.html = _read("mobile.html")

    def test_linkcheck_empty_base_guard(self):
        """linkCheck 空基址守卫（语句形态）：守卫分支内无任何请求语句，
        直接离线态+配对门——同源探活在 APK 内必吃资产服务器劫持。"""
        block = _span(self.js, "function linkCheck() {", "function startLinkCheck")
        guard_end = block.index("probeBase(BASE)")
        guard = _code_only(block[:guard_end])
        self.assertIn("if (!BASE && inApk()) {", guard)
        self.assertIn("ensurePairGate();", guard)
        self.assertNotIn("fetch(", guard, "守卫分支不得发任何请求")
        self.assertNotIn("probeBase(", guard, "守卫分支不得触发探活")

    def test_guard_is_apk_only(self):
        """浏览器同源托管（/console/mobile.html）BASE='' 是合法形态——
        守卫必须 inApk() 门控，不许把网页端也拉进配对门。"""
        for stmt in ("function loadHistory() {\n        if (!BASE && inApk()) { return; }",
                     "if (!BASE && inApk()) { return; }"):
            self.assertIn(stmt, self.js)
        self.assertIn("function inApk() {", self.js)
        self.assertIn("window.Capacitor", _span(self.js, "function inApk() {", "\n    }"))

    def test_sse_and_send_guards(self):
        """SSE 空基址守卫（esConnect 不建连）+ sendMessage 空基址走草稿箱
        +配对门引导（横幅引导去配对，消息不丢）。"""
        es_block = _span(self.js, "function esConnect() {", "es = new EventSource")
        self.assertIn("if (!BASE && inApk()) { return; }", es_block)
        send_block = _span(self.js, "function sendMessage(text) {", "function sendRaw(")
        self.assertIn("(!BASE && inApk())", send_block)
        self.assertIn("draftPush(text);", send_block)
        self.assertIn("ensurePairGate(true);", send_block)   # 发送动作=无视 dismissal 强制引导

    def test_pair_gate_functions_present(self):
        """配对门四件套（22b0d12 形态回迁）：载荷解析/逐候选探活/扫码器/
        门本体+去重；pairConnect 落键=新键 xj3_mobile_base。"""
        for fn in ("function parsePairingPayload(text) {",
                   "function pairConnect(candidates) {",
                   "function openPairScanner() {",
                   "function showPairGate() {",
                   "function ensurePairGate(force) {"):
            self.assertIn(fn, self.js)
        pair_block = _span(self.js, "function pairConnect(candidates) {",
                           "function openPairScanner()")
        self.assertIn("localStorage.setItem('xj3_mobile_base', base);", pair_block)
        self.assertIn("XJ3Net.probeBase(base)", pair_block)   # 探活唯一实现
        gate_block = _span(self.js, "function ensurePairGate(force) {", "/* ==================== 7.")
        self.assertIn("document.getElementById('mPairGate')", gate_block)
        # 骚扰防回归：用户点「暂不连接」后，15s 周期探活不再自动弹门
        # （IAB 验收现场实锤过每 15s 复弹）；仅发送动作强制重开。
        self.assertIn("pairGateDismissed", gate_block)
        later = _span(self.js, "var laterBtn = document.createElement('button');",
                      "manual.appendChild(summary);")
        self.assertIn("pairGateDismissed = true;", later)

    def test_pairing_payload_contract(self):
        """载荷契约（22b0d12 同款）：xiaoju3://connect?ips=a,b&port=5003 →
        http://a:5003/http://b:5003 候选；http:// 直填兼容。"""
        block = _span(self.js, "function parsePairingPayload(text) {",
                      "function pairConnect(candidates) {")
        self.assertIn("xiaoju3://connect", block)
        self.assertIn("URLSearchParams", block)

    def test_diag_panel_single_and_bound(self):
        """诊断面板：#mCssDiag 单例（双份重复 div 已去重）+三击标题呼出
        +内容含当前基址/最近探活 URL+结果（失败类别透出）。"""
        self.assertEqual(self.html.count('id="mCssDiag"'), 1,
                         "mCssDiag 必须恰好一个（历史双份重复 div 已排雷）")
        self.assertIn("function bindDiagToggle() {", self.js)
        self.assertIn("bindDiagToggle();", _span(self.js, "function init() {", "if (document.readyState"))
        render = _span(self.js, "function diagRender() {", "/* ==================== 1.")
        for token in ("DIAG.base", "DIAG.baseSrc", "DIAG.last.url", "DIAG.last.err"):
            self.assertIn(token, render)

    def test_probe_uses_core_single_impl(self):
        """探活唯一实现锚：mobile.js 不再持有 probeBase 拷贝（防双端漂移
        红线），改经 XJ3Net.probeBase 转发+诊断回调；核心不传 onDiag 时
        行为与旧版等价（2 参调用兼容）。"""
        self.assertIn("return XJ3Net.probeBase(base, 5000, diagRecord);", self.js)
        self.assertNotIn("var ctl = new AbortController();", self.js,
                         "mobile.js 不得残留探活拷贝（唯一实现在核心）")
        core = _read("xj3_network_core.js")
        probe = _span(core, "XJ3Net.probeBase = function (base, timeoutMs, onDiag) {", "/* ---------- 流式对话编排")
        self.assertIn("typeof onDiag !== 'function'", probe)   # 可选回调=2参兼容
        self.assertIn("j.status === 'ok'", probe)              # 判据口径不变
        self.assertIn("timeoutMs || 5000", probe)               # 超时口径不变

    def test_no_mdns_in_linkcheck(self):
        """🔴 红线守望：探活保持 HTTP /api/health——mDNS/zeroconf/SSDP
        禁入移动端网络栈（真机自动发现是后续路线，本批不许接线）。"""
        low = self.js.lower()
        for banned in ("mdns", "zeroconf", "_xiaoju._tcp", "bonjour", "ssdp"):
            self.assertNotIn(banned, low, "红线违例：%s 不得出现在 mobile.js" % banned)
        link = _span(self.js, "function linkCheck() {", "function startLinkCheck")
        self.assertIn("probeBase(BASE)", link)   # 探活链仍是 HTTP /api/health


# ---------------------------------------------------------------------------
# 三、node 运行时烟雾（test_streamcard_runtime_smoke.py 同款模式）
# ---------------------------------------------------------------------------

HARNESS = r'''
// ==================== 最小 DOM 桩（仅覆盖 mobile.js 实际使用面） ====================
function makeEl(tag) {
  var el = {
    tagName: String(tag || 'div').toUpperCase(),
    children: [], parentNode: null, className: '', id: '',
    style: {}, dataset: {}, attrs: {}, textContent: '', value: '',
    hidden: false, disabled: false, isConnected: false,
    scrollTop: 0, scrollHeight: 0, clientHeight: 0
  };
  el.classList = {
    add: function (c) { if (!this.contains(c)) el.className = (el.className + ' ' + c).trim(); },
    remove: function (c) { el.className = (' ' + el.className + ' ').replace(' ' + c + ' ', ' ').trim(); },
    contains: function (c) { return (' ' + el.className + ' ').indexOf(' ' + c + ' ') !== -1; },
    toggle: function (c, force) {
      var want = force === undefined ? !this.contains(c) : !!force;
      if (want) { this.add(c); } else { this.remove(c); }
      return want;
    }
  };
  el.appendChild = function (c) { c.parentNode = el; el.children.push(c); c.isConnected = true; return c; };
  el.removeChild = function (c) {
    var i = el.children.indexOf(c);
    if (i >= 0) { el.children.splice(i, 1); }
    c.parentNode = null; c.isConnected = false;
    return c;
  };
  el.insertBefore = function (c, ref) {
    c.parentNode = el; c.isConnected = true;
    var i = ref ? el.children.indexOf(ref) : -1;
    if (i >= 0) { el.children.splice(i, 0, c); } else { el.children.push(c); }
    return c;
  };
  el.remove = function () { if (el.parentNode) { el.parentNode.removeChild(el); } };
  el.setAttribute = function (k, v) { el.attrs[k] = String(v); if (k === 'id') { el.id = String(v); } };
  el.getAttribute = function (k) { return el.attrs[k] === undefined ? null : el.attrs[k]; };
  el.removeAttribute = function (k) { delete el.attrs[k]; };
  el.addEventListener = function () {};
  el.querySelectorAll = function (sel) {
    var out = [];
    var cls = sel.charAt(0) === '.' ? sel.slice(1) : null;
    var tag = (sel.charAt(0) !== '.' && sel.charAt(0) !== '#')
      ? String(sel).toUpperCase() : null;
    (function walk(n) {
      (n.children || []).forEach(function (c) {
        if ((cls && c.classList.contains(cls)) || (tag && c.tagName === tag)) {
          out.push(c);
        }
        walk(c);
      });
    })(el);
    return out;
  };
  el.querySelector = function (sel) { return el.querySelectorAll(sel)[0] || null; };
  Object.defineProperty(el, 'innerHTML', {
    get: function () { return el._html || ''; },
    set: function (h) { el._html = String(h); el.children = []; }
  });
  return el;
}
function searchTree(root, pred) {
  var out = [];
  (function walk(n) {
    (n.children || []).forEach(function (c) {
      if (pred(c)) { out.push(c); }
      walk(c);
    });
  })(root);
  return out;
}
var __body = makeEl('body');
global.document = {
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) {
    var hit = searchTree(__body, function (e) { return e.id === id; })[0];
    return hit || null;   // 严格查找，不惰性造节点（ensurePairGate 去重语义依赖 null）
  },
  querySelector: function (sel) {
    if (sel.charAt(0) === '#') { return global.document.getElementById(sel.slice(1)); }
    if (sel.charAt(0) === '.') {
      var cls = sel.slice(1);
      return searchTree(__body, function (e) { return e.classList.contains(cls); })[0] || null;
    }
    return searchTree(__body, function (e) { return e.tagName === String(sel).toUpperCase(); })[0] || null;
  },
  querySelectorAll: function (sel) {
    if (sel.charAt(0) === '.') {
      var cls = sel.slice(1);
      return searchTree(__body, function (e) { return e.classList.contains(cls); });
    }
    return [];
  },
  addEventListener: function () {},
  documentElement: makeEl('html'),
  readyState: 'complete',
  body: __body
};
// 预置 mobile.js 启动捕获的静态节点（同真实 mobile.html body 树）
['__mCssDiag_placeholder__'].forEach(function () {});
['mCssDiag', 'mConnBanner', 'mScrim', 'mDrawer', 'mMenuBtn', 'mStream',
 'mScrollBottomBtn', 'mInput', 'mSendBtn', 'mComposer', 'mMicBtn', 'mConnDot',
 'mDrawerConnDot', 'mDrawerConnText', 'mPanel', 'mPanelTitle', 'mPanelBody',
 'mPanelBack', 'mAttachBtn', 'mAttachFile'].forEach(function (id) {
  var e = makeEl('div'); e.id = id; e.setAttribute('id', id); __body.appendChild(e);
});
var __bannerSpan = makeEl('span');
global.document.getElementById('mConnBanner').appendChild(__bannerSpan);
var __title = makeEl('h1'); __title.className = 'topbar-title'; __body.appendChild(__title);

global.__result = { fetchCalls: [], reloads: 0 };
global.window = {
  addEventListener: function () {},
  location: { href: 'http://localhost/', reload: function () { global.__result.reloads += 1; } }
};
if (global.__CAP) { global.window.Capacitor = global.__CAP; }   // 场景前缀预置的 APK 桥桩
global.navigator = {};
// localStorage：真实 Map 语义（迁移幂等断言依赖真读写）
var __store = {};
global.localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; },
  clear: function () { __store = {}; },
  _dump: function () { return JSON.parse(JSON.stringify(__store)); }
};
global.__getStore = function () { return __store; };
if (global.__SEED) {   // 场景前缀预置的初始存储（HARNESS 先于源码执行）
  Object.keys(global.__SEED).forEach(function (k) { __store[k] = String(global.__SEED[k]); });
}
'''

FOOTER_TMPL = r'''
// ==================== 场景驱动（异步结算后统一收口） ====================
setTimeout(function () {
  var results = { scenario: '%(scenario)s', fetchCalls: global.__result.fetchCalls.slice(),
    reloads: global.__result.reloads, storage: global.localStorage._dump(),
    diag: { base: window.__xj3Mobile.diag.base, baseSrc: window.__xj3Mobile.diag.baseSrc,
            env: window.__xj3Mobile.diag.env, last: window.__xj3Mobile.diag.last } };
  results.gatePresent = !!(document.getElementById('mPairGate'));
  results.bannerHidden = !!(document.getElementById('mConnBanner') && document.getElementById('mConnBanner').hidden);
  results.bannerText = __bannerSpan.textContent;
  results.caps = document.body.getAttribute('data-caps');
  results.r1 = (typeof global.__r1 !== 'undefined') ? global.__r1 : null;
  console.log('__XJ3_NETFIX__' + JSON.stringify(results));
  process.exit(0);   // 桩环境残留定时器（15s 探活轮询等）会挂住事件循环，显式退场
}, 120);
'''


def _run_node(scenario_prefix, extra_footer=""):
    """组装 前缀+桩+核心+mobile.js(+可重复执行)+收尾 并跑 node。"""
    core = _read("xj3_network_core.js")
    mjs = _read("mobile.js")
    footer = FOOTER_TMPL % {"scenario": "run"} + extra_footer
    script = scenario_prefix + HARNESS + "\n" + core + "\n" + mjs + "\n" + footer
    proc = subprocess.run(["node"], input=script.encode("utf-8"),
                          capture_output=True, timeout=60)
    return proc


def _parse_marker(proc):
    out = proc.stdout.decode("utf-8", "replace")
    assert "__XJ3_NETFIX__" in out, "驱动未输出结果标记：\nSTDOUT:%s\nSTDERR:%s" % (
        out[-800:], proc.stderr.decode("utf-8", "replace")[-800:])
    return json.loads(out[out.index("__XJ3_NETFIX__") + len("__XJ3_NETFIX__"):])


class MobileNetfixRuntimeSmokeTests(unittest.TestCase):
    """真跑 core+mobile.js：空基址守卫/配对门/迁移幂等/失败类别透出。"""

    def _skip_if_no_node(self):
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过运行时烟雾")

    def test_empty_base_apk_wakes_pair_gate_not_dead_loop(self):
        """队长验收门的回归锚：APK 环境+localStorage 无地址 → 零 fetch（不发
        虚空探活）+配对门出现+横幅示警——不是 15s 一轮的永久离线死循环。"""
        self._skip_if_no_node()
        prefix = (
            "global.fetch = function (url) { global.__result.fetchCalls.push(String(url));"
            " return Promise.resolve({ json: function () { return Promise.resolve({ status: 'ok' }); } }); };\n"
            "global.__CAP = { isNativePlatform: function () { return true; } };\n"
        )
        proc = _run_node(prefix)
        self.assertEqual(proc.returncode, 0,
                         "node 运行时烟雾失败：\n" + proc.stderr.decode("utf-8", "replace"))
        r = _parse_marker(proc)
        self.assertEqual(r["fetchCalls"], [],
                         "空基址+APK 环境发了请求（守卫失效）：%s" % r["fetchCalls"])
        self.assertTrue(r["gatePresent"], "配对门未出现（静默滑进离线=回归）")
        self.assertFalse(r["bannerHidden"], "横幅未示警")
        self.assertIn("未连接主机", r["bannerText"])
        self.assertEqual(r["caps"], "l0")
        self.assertIn("APK", r["diag"]["env"])

    def test_pair_connect_probes_and_saves_base(self):
        """配对门连接链：pairConnect 逐候选探活，首个 ok 落新键+重载——
        '能成功探活局域网'的链路级验证（IAB 端到端另测）。"""
        self._skip_if_no_node()
        prefix = (
            "global.fetch = function (url) { global.__result.fetchCalls.push(String(url));"
            " return Promise.resolve({ json: function () { return Promise.resolve({ status: 'ok' }); } }); };\n"
            "global.__CAP = { isNativePlatform: function () { return true; } };\n"
            "global.__drive = function () { window.__xj3Mobile.pairConnect(['http://10.2.3.4:5003']); };\n"
        )
        extra = "\nglobal.__drive();\n"
        proc = _run_node(prefix, extra)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        r = _parse_marker(proc)
        self.assertEqual(r["storage"].get("xj3_mobile_base"), "http://10.2.3.4:5003",
                         "配对成功未落新键：%s" % r["storage"])
        self.assertGreaterEqual(r["reloads"], 1, "配对成功未触发重载")
        self.assertTrue(any("/api/health" in u for u in r["fetchCalls"]),
                        "配对探活未走 /api/health 链：%s" % r["fetchCalls"])

    def test_legacy_key_migration_idempotent(self):
        """旧键迁移幂等：xj3_api_base 孤儿值一次迁入新键；二次执行（=二次
        加载）不再改写；两键并存时新键优先（旧值不得复活覆盖用户改动）。"""
        self._skip_if_no_node()
        prefix = (
            "global.fetch = function (url) { return Promise.reject(new Error('offline')); };\n"
            "global.__CAP = { isNativePlatform: function () { return true; } };\n"
            "global.__SEED = { 'xj3_api_base': 'http://192.168.1.9:5003' };\n"
        )
        # mobile.js 再执行两遍（二次/三次加载语义），第三遍前把新键改成用户手存值
        mjs = _read("mobile.js")
        core = _read("xj3_network_core.js")
        third = ("global.localStorage.setItem('xj3_mobile_base', 'http://user-saved:5003');\n")
        footer = FOOTER_TMPL % {"scenario": "migration"}
        script = (prefix + HARNESS + "\n" + core + "\n" + mjs + "\n"
                  + "var __first = { base: window.__xj3Mobile.diag.base, src: window.__xj3Mobile.diag.baseSrc,"
                  + " store: global.localStorage._dump() };\n"
                  + core + "\n" + mjs + "\n"
                  + "var __second = { base: window.__xj3Mobile.diag.base, store: global.localStorage._dump() };\n"
                  + third + core + "\n" + mjs + "\n"
                  + "var __third = { base: window.__xj3Mobile.diag.base, store: global.localStorage._dump() };\n"
                  + "global.__phases = { first: __first, second: __second, third: __third };\n"
                  + footer.replace("var results = {", "var results = { phases: global.__phases,"))
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        r = _parse_marker(proc)
        ph = r["phases"]
        # 第一次加载：孤儿旧键 → 迁入新键
        self.assertEqual(ph["first"]["base"], "http://192.168.1.9:5003")
        self.assertEqual(ph["first"]["store"].get("xj3_mobile_base"),
                         "http://192.168.1.9:5003", "旧键值未迁入新键")
        self.assertIn("迁移", ph["first"]["src"])
        # 第二次加载：幂等——新键已就位，来源=已保存地址，旧键保留
        self.assertEqual(ph["second"]["base"], "http://192.168.1.9:5003")
        self.assertEqual(ph["second"]["store"], ph["first"]["store"],
                         "二次执行改写了存储（迁移不幂等）")
        # 第三次加载：新键优先——用户改存的地址不被旧键复活覆盖
        self.assertEqual(ph["third"]["base"], "http://user-saved:5003",
                         "旧键值复活覆盖了用户新键（优先级回归）")

    def test_probe_failure_category_surfaced(self):
        """诊断透出：200+HTML（资产服务器劫持形态）→'返回非 JSON'；网络
        拒连 →'网络错误'——bool 之外失败类别可见（诊断面板数据源）。"""
        self._skip_if_no_node()
        prefix = (
            "global.__probeIdx = 0;\n"
            "global.fetch = function (url) {\n"
            "  global.__result.fetchCalls.push(String(url));\n"
            "  global.__probeIdx += 1;\n"
            "  if (global.__probeIdx === 1) {\n"
            "    return Promise.resolve({ json: function () { return Promise.reject(new SyntaxError('Unexpected token < in JSON')); } });\n"
            "  }\n"
            "  return Promise.reject(new TypeError('fetch failed'));\n"
            "};\n"
            "global.__CAP = { isNativePlatform: function () { return true; } };\n"
            "global.__SEED = { 'xj3_mobile_base': 'http://bad-host:5003' };\n"
            "global.__drive = function () { window.__xj3Mobile.linkCheck(); };\n"
        )
        extra = ("\nsetTimeout(function () {\n"
                 "  global.__r1 = window.__xj3Mobile.diag.last\n"
                 "    ? JSON.parse(JSON.stringify(window.__xj3Mobile.diag.last)) : null;\n"
                 "  global.__drive();   // 第二次探活：网络拒连形态\n"
                 "}, 30);\n")
        proc = _run_node(prefix, extra)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        r = _parse_marker(proc)
        last = r["diag"]["last"]
        self.assertIsNotNone(last, "探活诊断未记录")
        # 第一次探活（init 触发）：200+HTML → '返回非 JSON（疑似本地资产劫持）'
        self.assertIsNotNone(r["r1"], "第一次探活诊断未捕获")
        self.assertIn("非 JSON", r["r1"]["err"],
                      "HTML 劫持形态未归类：%s" % r["r1"]["err"])
        # 第二次探活（__drive 触发）：拒连 → '网络错误'
        self.assertIn("网络错误", last["err"],
                      "拒连形态未归类：%s" % last["err"])
        self.assertFalse(last["ok"])


if __name__ == "__main__":
    unittest.main()
