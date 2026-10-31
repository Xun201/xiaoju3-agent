# -*- coding: utf-8 -*-
"""流式思维卡/直出思维流 node 运行时烟雾（2026-10-22 救火教训固化）。

背景：757f321 把 ensureThinkCard() 调用提到 fetch 之前而函数本体仍声明在
.then 回调内层作用域 → 运行时 ReferenceError 同步炸掉发送链（界面假死）。
node --check 只查语法、静态锚只查子串——都查不出作用域/未定义标识符类
事故。本测试用最小 DOM 桩在 node 里【真跑】console.js 全文件 + 真打一轮
SSE 事件序列 + 走完 legacy 回退，是本类事故的唯一可靠自动门。

纯计算子进程（stdin 管道、无网络——fetch 为桩、无临时文件；环境无 node 跳过）。
"""
import json
import os
import shutil
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARNESS = r'''
// ==================== 最小 DOM 桩（仅覆盖 console.js 实际使用面） ====================
function makeEl(tag) {
  var el = {
    tagName: String(tag || 'div').toUpperCase(),
    children: [], parentNode: null, className: '',
    style: {}, dataset: {}, attrs: {}, textContent: '',
    isConnected: false
  };
  el.classList = {
    _owner: el,
    add: function (c) { if (!this.contains(c)) el.className = (el.className + ' ' + c).trim(); },
    remove: function (c) { el.className = (' ' + el.className + ' ').replace(' ' + c + ' ', ' ').trim(); },
    contains: function (c) { return (' ' + el.className + ' ').indexOf(' ' + c + ' ') !== -1; },
    toggle: function (c) { this.contains(c) ? this.remove(c) : this.add(c); return this.contains(c); }
  };
  el.appendChild = function (c) { c.parentNode = el; el.children.push(c); c.isConnected = true; return c; };
  el.removeChild = function (c) {
    var i = el.children.indexOf(c);
    if (i >= 0) el.children.splice(i, 1);
    c.parentNode = null; c.isConnected = false;
    return c;
  };
  el.insertBefore = function (c, ref) {
    c.parentNode = el; c.isConnected = true;
    var i = ref ? el.children.indexOf(ref) : -1;
    if (i >= 0) el.children.splice(i, 0, c); else el.children.push(c);
    return c;
  };
  el.remove = function () { if (el.parentNode) el.parentNode.removeChild(el); };
  el.contains = function (n) { while (n) { if (n === el) return true; n = n.parentNode; } return false; };
  el.prepend = function (c) { el.insertBefore(c, el.children[0] || null); };
  el.querySelectorAll = function (sel) {
    var cls = String(sel).replace(/^\./, '').split(/[ .\[]/)[0];
    var out = [];
    (function walk(n) {
      n.children.forEach(function (c) {
        if (cls && c.classList.contains(cls)) out.push(c);
        walk(c);
      });
    })(el);
    return out;
  };
  el.querySelector = function (sel) { return el.querySelectorAll(sel)[0] || null; };
  el.setAttribute = function (k, v) { el.attrs[k] = v; };
  el.getAttribute = function (k) { return el.attrs[k] === undefined ? null : el.attrs[k]; };
  el.removeAttribute = function (k) { delete el.attrs[k]; };
  el.closest = function () { return null; };
  el.addEventListener = function () {};
  Object.defineProperty(el, 'innerHTML', {
    get: function () { return el._html || ''; },
    set: function (html) {
      el._html = String(html); el.children = [];
      var re = /class="([^"]+)"/g, m, seen = {};
      while ((m = re.exec(el._html))) {
        m[1].split(/\s+/).forEach(function (c) {
          if (c && !seen[c]) { seen[c] = 1; var k = makeEl('div'); k.classList.add(c); k.parentNode = el; el.children.push(k); }
        });
      }
    }
  });
  return el;
}
var __els = {};
global.document = {
  createElement: function (t) { return makeEl(t); },
  getElementById: function (id) { if (!__els[id]) __els[id] = makeEl('div'); return __els[id]; },
  querySelector: function () { return makeEl('div'); },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  documentElement: makeEl('html'),
  body: makeEl('body')
};
global.window = { addEventListener: function () {}, location: { href: '' } };
global.navigator = {
  language: 'zh-CN',
  clipboard: { writeText: function () { return Promise.resolve(); } }
};
global.localStorage = { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} };

// ==================== fetch 桩（脚本化场景） ====================
var __mode = 'idle';
global.__result = { syncThrow: '', streamDone: false, legacyDone: false, errors: [] };
global.fetch = function (url) {
  if (url === '/api/history') return new Promise(function () {});   // 挂起不结算
  if (__mode === 'stream-ok' && url === '/api/chat/stream') {
    var frames = [
      'event: think\ndata: {"delta":"[思考] 用户在打招呼"}\n\n',
      'event: think\ndata: {"delta":"，直接回应即可"}\n\n',
      'event: answer\ndata: {"delta":"你好呀！"}\n\n',
      'event: done\ndata: {"reply":"<think>[思考] 用户在打招呼，直接回应即可</think>你好呀！我是小橘3号","source":"🏠 本地"}\n\n'
    ];
    return Promise.resolve({
      ok: true,
      body: { getReader: function () {
        var i = 0;
        return { read: function () {
          if (i < frames.length) { var v = frames[i++]; return Promise.resolve({ done: false, value: new TextEncoder().encode(v) }); }
          return Promise.resolve({ done: true, value: undefined });
        } };
      } }
    });
  }
  if (__mode === 'stream-reject' && url === '/api/chat/stream') {
    return Promise.resolve({ ok: false, body: null });   // 触发 legacy 回退
  }
  if (__mode === 'stream-reject' && url === '/api/chat') {
    return Promise.resolve({
      json: function () { return Promise.resolve({ code: 200, data: {
        reply: '<think>[思考] 旧路</think>旧路回复正常渲染', source: '⚙️ 指令' } }); }
    });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

// ==================== 载入被测源码 ====================
'''

FOOTER = r'''
// ==================== 驱动：真发一条消息并轮询收口 ====================
function runScenario(mode, cb) {
  __mode = mode;
  var historyEl = document.getElementById('chat-history');
  historyEl.children.length = 0;   // 清场
  document.getElementById('chat-input').value = '你好';
  try {
    window.sendMessage();
  } catch (e) {
    global.__result.syncThrow = String(e && e.message || e);
    cb(); return;
  }
  var waited = 0;
  (function poll() {
    waited += 25;
    var bots = historyEl.children.filter(function (c) {
      return String(c.className).indexOf('bot-message') !== -1; });
    if (mode === 'stream-ok') {
      // 收口判据：思维流块已摘呼吸态且标签换耗时（textContent 真实可读）
      var live = null;
      bots.forEach(function (b) {
        var l = b.querySelectorAll('.think-live')[0];
        if (l) live = l;
      });
      var label = live && live.querySelectorAll('.think-live-label')[0];
      var done = live && !live.classList.contains('think-live-waiting')
        && String((label || {}).textContent || '').indexOf('已思考') !== -1;
      if (done || waited > 4000) { global.__result.streamDone = !!done; cb(); return; }
    } else {
      // legacy 判据：回复文本进了气泡 innerHTML（桩限性：模板文本存 _html）
      var legacyOk = bots.some(function (b) {
        return String(b._html || '').indexOf('旧路回复正常渲染') !== -1; });
      if (legacyOk || waited > 4000) { global.__result.legacyDone = legacyOk; cb(); return; }
    }
    setTimeout(poll, 25);
  })();
}

var results = {};
runScenario('stream-ok', function () {
  var historyEl = document.getElementById('chat-history');
  var bots = historyEl.children.filter(function (c) {
    return String(c.className).indexOf('bot-message') !== -1; });
  var liveBlocks = [];
  bots.forEach(function (b) {
    b.querySelectorAll('.think-live').forEach(function (l) { liveBlocks.push(l); });
  });
  var r = global.__result;
  results.stream = {
    syncThrow: r.syncThrow,
    finalRendered: r.streamDone,
    liveBlockCount: liveBlocks.length,
    liveWaiting: liveBlocks.some(function (l) { return l.classList.contains('think-live-waiting'); }),
    skeletonLeft: liveBlocks.some(function (l) { return l.querySelectorAll('.think-skeleton-line').length > 0; }),
    label: (liveBlocks[0] && liveBlocks[0].querySelectorAll('.think-live-label')[0] || {}).textContent || '',
    lines: (function () { var l = liveBlocks[0]; if (!l) return [];
      return l.querySelectorAll('.think-live-line').map(function (x) { return x.textContent; }); })(),
    botHtmlJoined: bots.map(function (b) { return String(b._html || ''); }).join('|||')
  };
  runScenario('stream-reject', function () {
    results.legacy = {
      syncThrow: global.__result.syncThrow,
      finalRendered: global.__result.legacyDone
    };
    console.log('__XJ3_SMOKE__' + JSON.stringify(results));
    process.exit(0);   // 桩环境残留定时器（轮询等）会挂住事件循环，显式退场
  });
});
'''


class StreamCardRuntimeSmokeTests(unittest.TestCase):
    """真跑 console.js：作用域/未定义标识符/DOM 误用的唯一可靠自动门。"""

    def test_stream_and_legacy_runtime_smoke(self):
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过运行时烟雾")
        core = open(os.path.join(PROJECT_ROOT, "xj3_network_core.js"),
                    encoding="utf-8").read()
        src = open(os.path.join(PROJECT_ROOT, "console.js"), encoding="utf-8").read()
        script = HARNESS + "\n" + core + "\n" + src + "\n" + FOOTER
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         "node 运行时烟雾失败：\n" + proc.stderr.decode("utf-8", "replace"))
        out = proc.stdout.decode("utf-8", "replace")
        self.assertIn("__XJ3_SMOKE__", out, "驱动未输出结果标记：\n" + out[-800:])
        results = json.loads(out[out.index("__XJ3_SMOKE__") + len("__XJ3_SMOKE__"):])

        # 场景 1：SSE 流式全链——同步阶段零异常（757f321 假死雷在此现形）
        s = results["stream"]
        self.assertEqual(s["syncThrow"], "",
                         "发送链同步抛错（作用域/未定义标识符类事故）：%s" % s["syncThrow"])
        self.assertTrue(s["finalRendered"], "流式 done 后最终消息未渲染完成")
        self.assertEqual(s["liveBlockCount"], 1, "最终消息应恰好收养一个思维流块")
        self.assertFalse(s["liveWaiting"], "收口后呼吸态未摘除（无缝接管失败）")
        self.assertFalse(s["skeletonLeft"], "收口后骨架占位线未清（无缝接管失败）")
        self.assertIn("已思考（用时", s["label"], "收口标签未换耗时口径")
        self.assertTrue(any("用户在打招呼" in ln for ln in s["lines"]),
                        "思考行未直出（前缀应剥除、文本应保留）")
        # 严格分流：正文只进气泡（innerHTML 模板），绝不进思维流块
        self.assertIn("我是小橘3号", s["botHtmlJoined"], "正文未渲染进气泡")
        for ln in s["lines"]:
            self.assertNotIn("我是小橘3号", ln, "正文漏进思维流块（分流被破坏）")

        # 场景 2：流端点失败 → legacy 回退正常渲染（回退链无死锁）
        l = results["legacy"]
        self.assertEqual(l["syncThrow"], "", "回退场景同步抛错：%s" % l["syncThrow"])
        self.assertTrue(l["finalRendered"], "legacy 回退后回复未渲染")


if __name__ == "__main__":
    unittest.main()
