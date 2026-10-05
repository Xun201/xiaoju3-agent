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


if __name__ == "__main__":
    unittest.main()
