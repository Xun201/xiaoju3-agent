# -*- coding: utf-8 -*-
"""plugins/context_manager 单元测试：前情提要压缩逻辑。

全部离线可跑：用替身 brain 模块（注入 sys.modules）mock 双脑
ask_local / ask_cloud，覆盖"本地成功 / 本地失败转云端 / 双脑不可用"。
"""
import contextlib
import io
import os
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

        # 发给压缩模型的提示词：≤100 字要求（2026-10-28 递归摘要升级）+ 仅旧消息文本
        prompt = brain.local_calls[0]
        self.assertEqual(prompt[0]["role"], "system")
        self.assertIn("100字以内的前情提要", prompt[0]["content"])
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


class RecursiveSummaryTests(unittest.TestCase):
    """递归摘要（2026-10-28 上车）：旧【前情提要】并入再浓缩，条目单份。"""

    def test_old_summary_folded_into_prompt(self):
        brain = FakeBrain(local_reply="合并后的新摘要")
        msgs = make_messages(15)
        # 历史第 2 条是旧前情提要（上次压缩随历史落盘的形态）
        msgs.insert(1, {"role": "system", "content": "【前情提要】：旧要点甲"})
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs, max_messages=0)
        # 输入含旧提要+合并指令
        prompt = brain.local_calls[0]
        self.assertIn("旧前情提要：旧要点甲", prompt[1]["content"])
        self.assertIn("合并", prompt[1]["content"])
        # 输出单份提要条目，旧提要条目不再出现
        summaries = [m for m in result
                     if isinstance(m, dict) and m.get("role") == "system"
                     and str(m.get("content", "")).startswith("【前情提要】")]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["content"], "【前情提要】：合并后的新摘要")
        self.assertNotIn("【前情提要】：旧要点甲",
                         [str(m.get("content", "")) for m in result[2:]])

    def test_old_summary_only_no_old_messages(self):
        # 除旧提要外无其他旧消息 → 无可压缩内容，原样返回
        brain = FakeBrain()
        msgs = [{"role": "system", "content": "你是小橘3号。"},
                {"role": "system", "content": "【前情提要】：旧要点"}]
        msgs += [{"role": "user", "content": f"消息{i}"} for i in range(15)]
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs, max_messages=0, keep_recent=15)
        self.assertIs(result, msgs)
        self.assertEqual(len(brain.local_calls), 0)


class TokenBudgetTests(unittest.TestCase):
    """Token 预算门（2026-10-28 上车）：条数触发退役的替代判定。"""

    def test_estimate_tokens_mixed(self):
        from plugins.context_manager import estimate_tokens
        # 10 个汉字 + 4 开销 = 14
        self.assertEqual(estimate_tokens(
            [{"role": "user", "content": "一二三四五六七八九十"}]), 14)
        # 10 个 ASCII 字符 ≈ 3 + 4 = 7
        self.assertEqual(estimate_tokens(
            [{"role": "user", "content": "abcdefghij"}]), 7)
        self.assertEqual(estimate_tokens([]), 0)
        self.assertEqual(estimate_tokens(None), 0)

    def test_over_token_budget_explicit(self):
        from plugins.context_manager import over_token_budget
        hist = [{"role": "user", "content": "汉" * 40}]   # 40+4=44
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_TOKENS": "60"}):
            self.assertTrue(over_token_budget(hist, threshold=0.70))  # 44/60≈0.73
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_TOKENS": "100"}):
            self.assertFalse(over_token_budget(hist, threshold=0.70))
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_TOKENS": "0"}):
            self.assertFalse(over_token_budget(hist))

    def test_dynamic_window_by_engine(self):
        # 动态窗口（2026-10-28 二轮）：cloud=32000 / local=4096，env 均可覆盖
        from plugins.context_manager import (context_window_tokens,
                                             over_token_budget)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XIAOJU3_CONTEXT_WINDOW_TOKENS", None)
            os.environ.pop("XIAOJU3_CONTEXT_WINDOW_CLOUD", None)
            self.assertEqual(context_window_tokens("cloud"), 32000)
            self.assertEqual(context_window_tokens("local"), 4096)
            self.assertEqual(context_window_tokens(None), 4096)  # 未知=保守
        hist = [{"role": "user", "content": "汉" * 300}]   # 304 tokens
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_BUDGET_RATIO": "0.7"}):
            # 304/4096≈0.074：同一段历史 local 不压
            self.assertFalse(over_token_budget(hist, engine="local"))
            # cloud 窗口更大更不压——边界改用小 env 验证分叉
        with mock.patch.dict(os.environ, {
                "XIAOJU3_CONTEXT_WINDOW_TOKENS": "400",
                "XIAOJU3_CONTEXT_WINDOW_CLOUD": "800",
                "XIAOJU3_CONTEXT_BUDGET_RATIO": "0.7"}):
            self.assertTrue(over_token_budget(hist, engine="local"))   # 304/400=0.76
            self.assertFalse(over_token_budget(hist, engine="cloud"))  # 304/800=0.38

    def test_should_compress_hard_cap(self):
        from plugins.context_manager import should_compress
        tiny = [{"role": "user", "content": "短"}] * 130
        self.assertTrue(should_compress(tiny))          # 硬帽保险丝
        small = [{"role": "user", "content": "短"}] * 30
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_TOKENS":
                                          "100000"}):
            self.assertFalse(should_compress(small))    # 条数多但 Token 低

    def test_env_overrides(self):
        from plugins.context_manager import over_token_budget
        hist = [{"role": "user", "content": "汉" * 40}]   # 44 tokens
        with mock.patch.dict(os.environ, {
                "XIAOJU3_CONTEXT_WINDOW_TOKENS": "50",
                "XIAOJU3_CONTEXT_BUDGET_RATIO": "0.9"}):
            self.assertFalse(over_token_budget(hist))    # 44/50=0.88 < 0.9
        # 收紧阈值到 0.8 → 超
        with mock.patch.dict(os.environ, {
                "XIAOJU3_CONTEXT_WINDOW_TOKENS": "50",
                "XIAOJU3_CONTEXT_BUDGET_RATIO": "0.8"}):
            self.assertTrue(over_token_budget(hist))


class ReloadedHistoryTests(unittest.TestCase):
    """重载历史形态（落盘剥 system 后 [0] 即前情提要条目）的递归折叠。"""

    def test_summary_entry_at_head_gets_folded_not_treated_as_header(self):
        brain = FakeBrain(local_reply="二代摘要")
        msgs = [{"role": "system", "content": "【前情提要】：一代要点"}]
        msgs += [{"role": "user" if i % 2 == 0 else "assistant",
                  "content": f"消息{i}"} for i in range(15)]
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs, max_messages=0)
        prompt = brain.local_calls[0]
        self.assertIn("旧前情提要：一代要点", prompt[1]["content"])
        summaries = [m for m in result
                     if isinstance(m, dict) and m.get("role") == "system"
                     and str(m.get("content", "")).startswith("【前情提要】")]
        self.assertEqual(len(summaries), 1)   # 单份，旧条目已折叠
        self.assertNotIn("【前情提要】：一代要点",
                         [str(m.get("content", "")) for m in result])

    def test_real_system_header_preserved_verbatim(self):
        brain = FakeBrain(local_reply="摘要")
        msgs = [{"role": "system", "content": "你是小橘3号。"}]
        msgs += [{"role": "user", "content": f"消息{i}"} for i in range(25)]
        with mock.patch.dict(sys.modules, {"brain": brain}):
            with _quiet_stdout():
                result = compress_context(msgs, max_messages=0)
        self.assertIs(result[0], msgs[0])   # 真 system 原样保留
