# -*- coding: utf-8 -*-
"""RAG 兜底上车测试（2026-10-28）：compress_context 成功路径事实沉淀。

零污染铁律：conftest 哨兵 XIAOJU3_SUMMARY_FACTS_ENABLED=0 缺省关闸；
本文件所有落库断言一律临时 base_dir，绝不碰真实 long_term.db。
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins.summary_facts import (  # noqa: E402
    FACT_CATEGORY, extract_facts, on_compress, persist_facts)
import plugins.summary_facts as sf  # noqa: E402
import plugins.context_manager as cm  # noqa: E402


def _fake_chat_ok(prompt):
    return ("主人偏好=主人喜欢吃微辣的东西\n"
            "主人计划=明天下午要去开会\n垃圾行没有等号\n")


def _msgs():
    return [{"role": "user", "content": "我明天下午要去开会，晚饭想吃微辣的"},
            {"role": "assistant", "content": "好嘞，帮主人记住了"}]


class GateTests(unittest.TestCase):
    """conftest 哨兵缺省关闸：测试环境零碰真实库。"""

    def test_gate_off_by_default_in_tests(self):
        # conftest setdefault 0；本进程内无人开过 → 关
        self.assertFalse(sf.enabled())

    def test_gate_off_blocks_write(self):
        with mock.patch.dict(os.environ,
                             {"XIAOJU3_SUMMARY_FACTS_ENABLED": "0"}):
            self.assertEqual(on_compress(_msgs(), base_dir="x:",
                                         chat_fn=_fake_chat_ok), 0)


class PersistTests(unittest.TestCase):
    """提取/去重/降级全在临时库。"""

    def test_extract_filters_and_caps(self):
        facts = extract_facts(_msgs(), chat_fn=_fake_chat_ok)
        self.assertIn(("主人计划", "明天下午要去开会"), facts)
        self.assertTrue(all("=" in f"{k}={v}" for k, v in facts))
        self.assertEqual(extract_facts([], chat_fn=_fake_chat_ok), [])
        def boom(_):
            raise RuntimeError("双脑全挂")
        self.assertEqual(extract_facts(_msgs(), chat_fn=boom), [])

    def test_persist_and_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(sf, "enabled", return_value=True):
                self.assertEqual(persist_facts(
                    extract_facts(_msgs(), chat_fn=_fake_chat_ok),
                    base_dir=td), 2)
                self.assertEqual(persist_facts(
                    extract_facts(_msgs(), chat_fn=_fake_chat_ok),
                    base_dir=td), 0)   # 去重


class CompressWiringTests(unittest.TestCase):
    """compress_context 成功路径接线：成功沉淀/降级不沉淀。"""

    def _run_compress(self, brain_stub):
        """跑一次 compress_context（隔离 brain+落库），返回 (结果, 库行)。"""
        td = tempfile.mkdtemp(prefix="xj3_facts_")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            td, ignore_errors=True))
        captured = {}

        def fake_sm(base_dir=None):
            from agent_state.state_manager import StateManager
            return StateManager(base_dir=base_dir or td)

        msgs = [{"role": "system", "content": "sys"}]
        msgs += [{"role": "user" if i % 2 == 0 else "assistant",
                  "content": f"我明天下午要开会，消息{i}"}
                 for i in range(15)]
        with mock.patch.dict(sys.modules, {"brain": brain_stub}), \
                mock.patch.object(sf, "_sm", side_effect=fake_sm), \
                mock.patch.object(sf, "enabled", return_value=True):
            out = cm.compress_context(msgs, max_messages=0)
            captured["rows"] = fake_sm().get_recent_memories(50)
        return out, captured["rows"]

    def test_success_path_persists_facts(self):
        class FakeBrain:
            def ask_local(self, prompt):
                return "摘要" if "浓缩" in prompt[0]["content"] else _fake_chat_ok(prompt)
            def ask_cloud(self, prompt):
                raise RuntimeError("不该调云")
        brain = FakeBrain()
        out, rows = self._run_compress(brain)
        self.assertTrue(any("【前情提要】" in str(m.get("content", ""))
                            for m in out))
        facts = [c for cat, c in rows if cat == FACT_CATEGORY]
        self.assertTrue(any("主人计划=" in c for c in facts), rows)

    def test_degraded_summary_persists_nothing(self):
        class DeadBrain:
            def ask_local(self, prompt):
                raise RuntimeError("本地挂")
            def ask_cloud(self, prompt):
                raise RuntimeError("云端挂")
        out, rows = self._run_compress(DeadBrain())
        self.assertTrue(any("由于系统原因" in str(m.get("content", ""))
                            for m in out))
        self.assertEqual([c for cat, c in rows
                          if cat == FACT_CATEGORY], [])   # 降级零沉淀


if __name__ == "__main__":
    unittest.main()
