# -*- coding: utf-8 -*-
"""思维链真流式 C2 测试（2026-10-05，#244）：SSE 路由协议/事件顺序/
与旧路同最终态/异常 error 事件/旧 /api/chat 回归 + 前端静态锚（流式
分支/回退路径/渐进渲染/textContent 口径）。mock smart_ask_stream 全离线。"""
import json
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import xiaoju3_dashboard as dashboard


def _parse_sse(body):
    """SSE 文本 → [(event, payload_dict)]。"""
    frames = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        etype, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if data:
            frames.append((etype, json.loads(data)))
    return frames


class ChatStreamSseTests(unittest.TestCase):
    """POST /api/chat/stream：SSE 协议与最终态对齐。"""

    def setUp(self):
        self.client = dashboard.app.test_client()
        tmp = tempfile_dir = __import__("tempfile").mkdtemp(
            prefix="xj3_c2_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            tmp, ignore_errors=True))
        hist = mock.patch.object(
            dashboard, "HISTORY_FILE",
            os.path.join(tmp, "history_console.json"))
        hist.start()
        self.addCleanup(hist.stop)

    def _mock_stream(self, reply="最终回复", source="🏠 本地"):
        """mock smart_ask_stream：吐 think/tool/answer 增量后返回。"""
        def fake_stream(msg, history=None, session_key="default",
                       on_event=None):
            for d in ("[思考] ", "过程"):
                on_event({"type": "think", "delta": d})
            on_event({"type": "tool", "name": "web_search"})
            for d in ("根据", "结果"):
                on_event({"type": "answer", "delta": d})
            return reply, source
        return fake_stream

    def test_sse_protocol_and_final_state(self):
        """协议锚：mimetype=text/event-stream；think/tool/answer/done
        四类事件依序；done 含净化完整 reply + source；且落盘控制台历史。"""
        with mock.patch.object(dashboard.brain, "smart_ask_stream",
                               side_effect=self._mock_stream()), _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "你好"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.mimetype)
        frames = _parse_sse(resp.get_data(as_text=True))
        types = [e for e, _ in frames]
        self.assertEqual(types, ["think", "think", "tool",
                                 "answer", "answer", "done"])
        deltas = "".join(d["delta"] for e, d in frames if e in ("think", "answer"))
        self.assertEqual(deltas, "[思考] 过程根据结果")   # 拼接 == 全量
        done = dict(frames)["done"]
        self.assertEqual(done["reply"], "最终回复")
        self.assertEqual(done["source"], "🏠 本地")
        with open(dashboard.HISTORY_FILE, encoding="utf-8") as f:
            hist = json.load(f)
        self.assertEqual(hist[-1]["content"], "最终回复")   # 落盘与旧路同口径

    def test_error_event_on_exception(self):
        """异常锚：smart_ask_stream 抛 → error 事件（无 done）。"""
        def boom(msg, history=None, session_key="default", on_event=None):
            on_event({"type": "think", "delta": "部分"})
            raise RuntimeError("炸了")
        with mock.patch.object(dashboard.brain, "smart_ask_stream",
                               side_effect=boom), _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "你好"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual(frames[-1][0], "error")
        self.assertIn("炸了", frames[-1][1]["error"])
        self.assertNotIn("done", [e for e, _ in frames])

    def test_empty_message_400(self):
        with _quiet():
            resp = self.client.post("/api/chat/stream", json={"message": ""})
        self.assertEqual(resp.status_code, 400)

    def test_legacy_chat_unaffected(self):
        """回归锚：原 /api/chat 未受影响（同步返回 JSON）。"""
        with mock.patch.object(
                dashboard, "smart_ask",
                return_value=("同步回复", "🏠 本地")), _quiet():
            resp = self.client.post("/api/chat", json={"message": "你好"})
        self.assertEqual(resp.get_json()["data"]["reply"], "同步回复")

    def test_intercept_on_stream_slash_help(self):
        """C3a 修复锚：stream 发 /help → 命中指令拦截，done 单帧返回
        菜单（不进模型）；done 帧格式正确（reply 净化 + source）。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
             _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/help"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])   # 单帧收口
        done = frames[-1][1]
        self.assertIn("指令菜单", done["reply"])
        self.assertEqual(done["source"], "⚙️ 系统")
        ms.assert_not_called()   # 不进模型

    def test_intercept_on_stream_lv4_auth(self):
        """stream 发 /lv4_auth → 权限警告（不进模型）。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
             _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/lv4_auth"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])
        self.assertIn("双因子授权", frames[-1][1]["reply"])
        ms.assert_not_called()

    def test_intercept_on_stream_location_command(self):
        """A' 修复锚（2026-10-07）：stream 发 /set_location（无参=用法
        回显，零副作用）→ 命中位置拦截，done 单帧 ⚙️ 系统，不进模型——
        修前该消息落大脑。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
             _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/set_location"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])
        done = frames[-1][1]
        self.assertIn("用法", done["reply"])
        self.assertEqual(done["source"], "⚙️ 系统")
        ms.assert_not_called()

    def test_intercept_on_stream_child_lock_command(self):
        """A' 修复锚：stream 发 /deny（无待裁决请求=ℹ️ 回显）→ 命中
        儿童锁拦截（is_console=True 成人设备口径与 api_chat 同款），
        done 单帧，不进模型。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
             _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/deny"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])
        done = frames[-1][1]
        self.assertIn("儿童操作请求", done["reply"])
        self.assertEqual(done["source"], "⚙️ 系统")
        ms.assert_not_called()

    def test_intercept_on_stream_creator_command(self):
        """A' 修复锚：stream 发 /creator → 命中署名拦截，done 单帧，
        不进模型（修前落大脑）。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
             _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/creator"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])
        done = frames[-1][1]
        self.assertIn("小橘3号", done["reply"])
        self.assertEqual(done["source"], "⚙️ 系统")
        ms.assert_not_called()

    def test_intercept_on_stream_todo_command(self):
        """A' 修复锚（本次 bug 主案）：stream 发 /todos → 待办族拦截
        （api_chat 806 同款），done 单帧 ⚙️ 指令 + <think> 指令处理卡，
        不进模型——修前此消息落大脑，本地模型幻觉无参 extract_todos
        （用户实收"❌ 缺少参数：需要提供 url"）。"""
        import shutil
        import tempfile
        from agent_state.state_manager import StateManager
        from permission import PermissionManager
        tmp = tempfile.mkdtemp(prefix="xj3_stream_todo_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        sm = StateManager(base_dir=tmp)
        sm.save_todos(["锚点测试待办"], source_url="u1")
        pm = PermissionManager()
        pm.current_level = "Lv.2"
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream(reply="LLM 回复")) as ms, \
                mock.patch.object(dashboard.main, "state_manager", sm), \
                mock.patch.object(dashboard, "state_manager", sm), \
                mock.patch.object(dashboard.main, "permission_manager", pm), \
                _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "/todos"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertEqual([e for e, _ in frames], ["done"])
        done = frames[-1][1]
        self.assertIn("<think>[指令处理]", done["reply"])   # 尾巴 3 指令卡
        self.assertIn("锚点测试待办", done["reply"])        # 清单来自注入的库
        self.assertEqual(done["source"], "⚙️ 指令")
        ms.assert_not_called()

    def test_stream_todo_link_still_reaches_brain(self):
        """A' 回归锚：DeepSeek 分享链接消息仍进 brain（todo_link_mode
        强制云端链路不受新增前置拦截影响）。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream()) as ms, _quiet():
            resp = self.client.post(
                "/api/chat/stream",
                json={"message":
                      "https://chat.deepseek.com/share/reg_anchor"})
        frames = _parse_sse(resp.get_data(as_text=True))
        self.assertIn("think", [e for e, _ in frames])   # 走流式管线
        self.assertEqual([e for e, _ in frames].count("done"), 1)
        ms.assert_called_once()

    def test_stream_normal_message_still_streams(self):
        """回归锚：普通消息仍逐块流式（think/answer 帧在位），拦截
        不误吞正常对话。"""
        with mock.patch.object(
                dashboard.brain, "smart_ask_stream",
                side_effect=self._mock_stream()), _quiet():
            resp = self.client.post("/api/chat/stream",
                                    json={"message": "你好"})
        frames = _parse_sse(resp.get_data(as_text=True))
        types = [e for e, _ in frames]
        self.assertIn("think", types)
        self.assertIn("done", types)
        self.assertEqual(types.count("done"), 1)


def tempfile_dir():
    import tempfile
    return tempfile.mkdtemp(prefix="xj3_c2_")


def _quiet():
    import contextlib
    import io
    return contextlib.redirect_stdout(io.StringIO())


class ChatStreamFrontendAnchorTests(unittest.TestCase):
    """前端静态锚：流式分支/回退路径/渐进渲染/textContent 口径。"""

    def _js(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  encoding="utf-8") as f:
            return f.read()

    def test_stream_branch_and_fallback(self):
        js = self._js()
        self.assertIn("'/api/chat/stream'", js)
        self.assertIn("getReader()", js)
        self.assertIn("sendMessageLegacy", js)     # 回退函数在位
        self.assertIn("sendMessageStream(text, loadingMsg, rotateTimer)",
                      js)
        self.assertIn(".catch(() => sendMessageLegacy", js)   # 失败回退

    def test_progressive_render_anchors(self):
        js = self._js()
        self.assertIn("think-card-header", js)     # 渐进思考卡
        self.assertIn("handleEvent(etype, JSON.parse(payload))", js)
        self.assertIn("textCategory" if False else "answerAcc += (data.delta || '')",
                      js)                          # answer 增量追加
        self.assertIn("escapeHtml(note)" if False else
                      "answerEl.querySelector('.bubble-content').textContent = answerAcc",
                      js)                          # textContent 注入口径
        self.assertIn("appendBotMessage(data.reply, data.source, text)",
                      js)                          # done 走既有单渲染管线

    def test_stream_interrupt_cleanup_and_legacy_guard(self):
        """C3b：半途断流——sendMessageStream 内层闭包清过程件再 rethrow
        （外层 catch 才转 legacy 重答）；legacy 主路径收 loadingMsg
        contains 防御（流式回退时 loadingMsg 可能已被过程卡消费，
        裸 removeChild 会 DOMException → 误落红字、重答不发生）。"""
        js = self._js()
        self.assertIn("return pump().catch", js)         # 内层清理挂钩
        self.assertIn("if (thinkCard && thinkCard.parentNode)", js)
        self.assertIn("if (toolEl && toolEl.parentNode)", js)
        self.assertIn("if (answerEl && answerEl.parentNode)", js)
        self.assertIn(
            "if (history.contains(loadingMsg)) history.removeChild(loadingMsg)",
            js)                                          # 与 1344 catch 分支口径对称
        # 作用域解耦：两分支开头自取 chat-history（裸 history 解析到
        # window.history 内置对象，appendChild/contains 全炸——C2 遗留，
        # "实时卡"从未渲染、回退回复不显示，全靠轮询兜底掩盖）
        self.assertIn(
            "const history = document.getElementById('chat-history');\n        return fetch('/api/chat/stream'",
            js)
        self.assertIn(
            "const history = document.getElementById('chat-history');\n        fetch('/api/chat'",
            js)

    def test_think_append_mode_and_tool_gate(self):
        """C3b：think 渐进 append 模式——完整行 append、末行整刷（chunk
        边收边长，末行必须随增量同步更新）；tool 事件无卡也建卡
        （不再静默丢）。textContent 安全口径不变。"""
        js = self._js()
        self.assertNotIn("thinkBodyEl.textContent = thinkAcc",
                         js)                             # 整刷退役（反锚）
        self.assertIn("thinkBodyEl.appendChild(row)", js)
        self.assertIn("renderedLines", js)
        self.assertIn("lastRowEl.textContent = lines[lines.length - 1] || ''",
                      js)                                # 末行整刷随 chunk 更新
        self.assertIn("ensureThinkCard();   // C3b：无卡也建", js)


if __name__ == "__main__":
    unittest.main()
