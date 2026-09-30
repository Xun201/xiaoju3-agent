# -*- coding: utf-8 -*-
"""plugins/context_manager 单元测试：前情提要压缩逻辑。

全部离线可跑：用替身 brain 模块（注入 sys.modules）mock 双脑
ask_local / ask_cloud，覆盖"本地成功 / 本地失败转云端 / 双脑不可用"。
"""
import contextlib
import io
import sys
import unittest
from unittest import mock

from plugins.context_manager import compress_context

FALLBACK_SUMMARY = "（由于系统原因，早期对话记忆已丢失）"


@contextlib.contextmanager
def _quiet_stdout():
    """吞掉压缩器的进度 print（含 emoji），保持测试输出干净。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


class FakeBrain:
    """替身 brain 模块：记录调用，可注入本地/云端行为。"""

    def __init__(self, local_reply="本地摘要", cloud_reply="云端摘要",
                 local_error=None, cloud_error=None):
        self.local_reply = local_reply
        self.cloud_reply = cloud_reply
        self.local_error = local_error
        self.cloud_error = cloud_error
        self.local_calls = []
        self.cloud_calls = []

    def ask_local(self, prompt):
        self.local_calls.append(prompt)
        if self.local_error is not None:
            raise self.local_error
        return self.local_reply

    def ask_cloud(self, prompt):
        self.cloud_calls.append(prompt)
        if self.cloud_error is not None:
            raise self.cloud_error
        return self.cloud_reply


def make_messages(n, system="你是小橘3号。"):
    """构造 n 条消息：第 1 条为 system，其余 user/assistant 交替。"""
    msgs = [{"role": "system", "content": system}]
    for i in range(n - 1):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"消息{i}"})
    return msgs


class CompressContextTest(unittest.TestCase):
    def test_short_history_returned_unchanged(self):
        # 不超过 20 条时不触发压缩，原列表原样返回
        for n in (1, 10, 20):
            msgs = make_messages(n)
            with _quiet_stdout():
                result = compress_context(msgs)
            self.assertIs(result, msgs)
            self.assertEqual(len(result), n)

    def test_long_history_compressed_via_local(self):
        brain = FakeBrain(local_reply="用户讨论了记忆压缩方案")
        msgs = make_messages(25)

        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs)

        # 本地成功：只调本地，不调云端
        self.assertEqual(len(brain.local_calls), 1)
        self.assertEqual(len(brain.cloud_calls), 0)

        # 结构：system 原样 + 前情提要 + 最近 10 条
        self.assertIs(result[0], msgs[0])
        self.assertEqual(result[1],
                         {"role": "system", "content": "【前情提要】：用户讨论了记忆压缩方案"})
        self.assertEqual(result[2:], msgs[-10:])
        self.assertEqual(len(result), 12)

        # 发给压缩模型的提示词：≤50 字要求 + 仅旧消息文本
        prompt = brain.local_calls[0]
        self.assertEqual(prompt[0]["role"], "system")
        self.assertIn("50字以内的前情提要", prompt[0]["content"])
        self.assertIn("user: 消息0", prompt[1]["content"])
        self.assertIn("assistant: 消息13", prompt[1]["content"])
        self.assertNotIn("消息14", prompt[1]["content"])  # 最近消息不参与压缩

    def test_local_failure_falls_back_to_cloud(self):
        brain = FakeBrain(local_error=RuntimeError("本地模型不在线"),
                          cloud_reply="云端兜底摘要")
        msgs = make_messages(25)

        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs)

        self.assertEqual(len(brain.local_calls), 1)
        self.assertEqual(len(brain.cloud_calls), 1)
        self.assertEqual(result[1],
                         {"role": "system", "content": "【前情提要】：云端兜底摘要"})
        self.assertEqual(result[2:], msgs[-10:])
        self.assertEqual(len(result), 12)

    def test_brain_unavailable_uses_fallback_text(self):
        # sys.modules 中置 None 可让 `import brain` 稳定抛 ImportError
        msgs = make_messages(25)
        with mock.patch.dict(sys.modules, {"brain": None}):
            with _quiet_stdout():
                result = compress_context(msgs)

        self.assertIs(result[0], msgs[0])
        self.assertEqual(result[1],
                         {"role": "system", "content": f"【前情提要】：{FALLBACK_SUMMARY}"})
        self.assertEqual(result[2:], msgs[-10:])

    def test_local_and_cloud_both_fail_uses_fallback_text(self):
        brain = FakeBrain(local_error=RuntimeError("本地挂了"),
                          cloud_error=RuntimeError("云端也挂了"))
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(make_messages(25))

        self.assertEqual(len(brain.cloud_calls), 1)
        self.assertEqual(result[1],
                         {"role": "system", "content": f"【前情提要】：{FALLBACK_SUMMARY}"})

    def test_no_old_messages_returns_original(self):
        # keep_recent 覆盖全部非 system 消息时，无旧消息可压缩，原样返回
        msgs = make_messages(21)
        with _quiet_stdout():
            result = compress_context(msgs, max_messages=20, keep_recent=20)
        self.assertIs(result, msgs)

    def test_custom_keep_recent(self):
        brain = FakeBrain()
        msgs = make_messages(30)
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs, keep_recent=5)
        self.assertEqual(len(result), 7)  # system + 前情提要 + 最近 5 条
        self.assertEqual(result[2:], msgs[-5:])


if __name__ == "__main__":
    unittest.main()
