# -*- coding: utf-8 -*-
"""smart_ask_stream 流式决策入口测试（2026-10-05 C1，#244；纯后端不接线）：
流式与同步同输出 / think→answer 事件顺序与拼接一致 / 工具环 tool 事件 /
on_event=None 静默不崩 / 流中断向上抛 / 本地热切换云端。mock 模型全离线。"""
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import brain

_REPLY = "[思考] 看一眼再答\n[计划] 1. 直接回答\n正文回答内容"
_THINK = "看一眼再答"
_BODY = "正文回答内容"

def _events_of(events, etype):
    return [e for e in events if e["type"] == etype]


class SmartAskStreamTests(unittest.TestCase):
    def setUp(self):
        # 本地在线 + high 档（走本地优先路径）；_remember_user_facts 的
        # SQLite 副作用异常天然静默跳过（brain 内部口径），无需隔离
        self.probe = mock.patch.object(brain, "probe_local",
                                       return_value=True)
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.tier = mock.patch.object(brain, "_resolve_tier",
                                      return_value="high")
        self.tier.start()
        self.addCleanup(self.tier.stop)
        self.local_model = mock.patch.object(
            brain, "_local_model_for", return_value="test-model")
        self.local_model.start()
        self.addCleanup(self.local_model.stop)

    def test_stream_sync_same_output_shape(self):
        """流式与同步同输出锚：同一 mock 模型，最终 reply 逐字节一致
        （封口与 <think> 包装同函数——2026-10-05 实测对齐）。"""
        with mock.patch.object(brain, "ask_local", return_value=_REPLY), \
             mock.patch.object(brain, "_ask_local_stream",
                               return_value=_REPLY) as ls:
            sync_reply, sync_src = brain.smart_ask("你好")
            events = []
            stream_reply, stream_src = brain.smart_ask_stream(
                "你好", on_event=events.append)
        self.assertEqual(sync_src, stream_src)
        self.assertEqual(sync_reply, stream_reply)   # 逐字节一致
        self.assertIn("<think>[思考]", stream_reply)  # 原生思考入卡
        self.assertIn(_BODY, stream_reply)
        ls.assert_called_once()   # 走的确实是流式消费器

    def test_event_order_and_delta_concat(self):
        """事件顺序锚：本地流式 think 增量事件先到；delta 拼接 == 完整
        原始回复。"""
        deltas = ["[思考] ", "看一眼\n[计划] 1. 直接回答\n正文", "回答内容"]
        with mock.patch.object(brain, "_ask_local_stream",
                               side_effect=lambda m, ev, **kw: (
                                   [ev({"type": "think", "delta": d})
                                    for d in deltas], "".join(deltas))[1]):
            events = []
            reply, src = brain.smart_ask_stream("你好",
                                                on_event=events.append)
        types = [e["type"] for e in events]
        self.assertEqual(types, ["think", "think", "think"])
        self.assertEqual("".join(e["delta"] for e in events),
                         "".join(deltas))
        self.assertIn(_BODY, reply)

    def test_tool_round_emits_tool_event(self):
        """工具环流式锚：[行动] JSON（_extract_tool_json 可解析形态）→
        tool 事件 + execute_tool 真调 + 汇总轮 answer 事件 + 最终串含
        工具结果。"""
        first = ("[思考] 需要搜索\n[计划] 1. 搜索\n"
                 '[思考2] 占位\n[计划2] 占位\n[行动2] 占位\n'
                 '[行动] {"tool": "web_search", "args": {"query": "测试"}}')
        tool_result = "✅ 搜索结果：小橘3号是桌面智能体"
        summary = "根据搜索，小橘3号是桌面智能体。"
        with mock.patch.object(brain, "_ask_local_stream",
                               side_effect=[first, summary]), \
             mock.patch.object(brain, "execute_tool",
                               return_value=tool_result) as ex:
            events = []
            reply, src = brain.smart_ask_stream("帮我搜测试",
                                                on_event=events.append)
        ex.assert_called_once()
        self.assertEqual([e["type"] for e in events].count("tool"), 1)
        self.assertEqual(
            next(e for e in events if e["type"] == "tool")["name"],
            "web_search")
        self.assertIn("根据搜索", reply)
        self.assertIn("(工具)", src)

    def test_none_on_event_silent(self):
        """无 on_event（None）不崩：静默消费，返回值正常。"""
        with mock.patch.object(brain, "_ask_local_stream",
                               return_value=_REPLY):
            reply, src = brain.smart_ask_stream("你好", on_event=None)
        self.assertIn(_BODY, reply)

    def test_stream_interrupt_raises(self):
        """流中断异常锚：本地流中断且云端兜底也异常（⚠️ 前缀）→ 双脑
        全挂口径返回失败串（与同步版一致，不吞不崩）。"""
        boom = mock.MagicMock(side_effect=ConnectionError("流断了"))
        with mock.patch.object(brain, "_ask_local_stream", boom), \
             mock.patch.object(brain, "_ask_cloud_stream",
                               return_value="⚠️ 云端连接异常: 也挂了"):
            reply, src = brain.smart_ask_stream("你好", on_event=None)
        self.assertEqual(src, "❌ 失败")
        self.assertIn("大脑连接失败", reply)

    def test_local_fail_falls_back_to_cloud_stream(self):
        """本地热切换云端锚：本地流式抛 → 云端流式接管，事件续传、
        来源如实标云端。"""
        boom = mock.MagicMock(side_effect=ConnectionError("本地挂了"))
        with mock.patch.object(brain, "_ask_local_stream", boom), \
             mock.patch.object(brain, "_ask_cloud_stream",
                               return_value=_REPLY) as cloud:
            events = []
            reply, src = brain.smart_ask_stream("你好",
                                                on_event=events.append)
        cloud.assert_called_once()
        self.assertEqual(src, "☁️ 云端")
        self.assertIn(_BODY, reply)

    def test_pre_emission_paths_emit_answer(self):
        """前置拦截路径也发事件（静默期询问/抓取失败），前端不空等。"""
        with mock.patch.object(brain, "_resolve_user_location",
                               return_value=("", "", "none")), \
             mock.patch.object(brain, "_location_in_clear_grace",
                               return_value=True), \
             mock.patch.object(brain, "LOCATION_SENSITIVE_KEYWORDS",
                               ["天气"]), \
             mock.patch.object(brain, "_ask_local_stream"):
            events = []
            reply, src = brain.smart_ask_stream("今天天气",
                                                on_event=events.append)
        self.assertEqual(src, "📍 询问位置")
        self.assertTrue(any(e["type"] == "answer" for e in events))


if __name__ == "__main__":
    unittest.main()
