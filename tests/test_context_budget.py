# -*- coding: utf-8 -*-
"""上下文预算门上车测试（2026-10-28）：brain._compress_history 与
main._compress_and_save 的 Token 预算触发 + 影子审查接线行为。

全部离线：ask_local/ask_cloud 用 mock.patch 替身；缓存文件落临时目录。
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import brain  # noqa: E402
import main as main_mod  # noqa: E402


def _tiny(n, text="短"):
    return [{"role": "user", "content": text} for _ in range(n)]


def _fat(n, chars=300):
    return [{"role": "user", "content": "汉" * chars} for _ in range(n)]


class BrainCompressGateTests(unittest.TestCase):
    """brain._compress_history：Token 门主触发 + 条数硬帽保险丝。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # 缓存文件指到临时目录，绝不污染真实 agent_state
        patcher = mock.patch.object(
            brain, "CONTEXT_SUMMARY_FILE",
            os.path.join(self._tmp.name, "context_summary.json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_count_trigger_retired(self):
        # 30 条超短消息：旧条数口径（>20）必压；Token 门下水位极低不动
        msgs = [{"role": "system", "content": "sys"}] + _tiny(30)
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_TOKENS":
                                          "100000",
                                          "XIAOJU3_CONTEXT_WINDOW_CLOUD":
                                          "100000"}):
            with mock.patch.object(brain, "ask_local",
                                   side_effect=AssertionError("不该调用")):
                out = brain._compress_history(msgs, "ut")
        self.assertIs(out, msgs)

    def test_over_budget_compresses_with_summary(self):
        # 窗口拉小制造超预算；ask_local 替身给确定性摘要
        msgs = ([{"role": "system", "content": "sys"}]
                + [{"role": "user", "content": "【当前时间】12:00"},
                   * _fat(6), * _tiny(10)])
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_CLOUD":
                                          "500"}):
            with mock.patch.object(brain, "ask_local",
                                   return_value="测试摘要内容"):
                out = brain._compress_history(msgs, "ut2")
        self.assertIsNot(out, msgs)
        joined = [str(m.get("content", "")) for m in out]
        self.assertTrue(any("【前情提要】" in c for c in joined))
        self.assertTrue(any(c == "【当前时间】12:00" for c in joined),
                        "时间块必须原位保留")
        self.assertEqual(out[-1], msgs[-1], "最近明细保留")

    def test_hard_cap_forces_compress_even_under_budget(self):
        # 130 条超短消息：Token 水位低，但硬帽保险丝必压
        msgs = [{"role": "system", "content": "sys"}] + _tiny(130)
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_CLOUD":
                                          "1000000"}):
            with mock.patch.object(brain, "ask_local",
                                   return_value="硬帽摘要"):
                out = brain._compress_history(msgs, "ut3")
        self.assertIsNot(out, msgs)

    def test_under_budget_short_history_untouched(self):
        msgs = [{"role": "system", "content": "sys"}, {"role": "user",
                                                       "content": "你好"}]
        out = brain._compress_history(msgs, "ut4")
        self.assertIs(out, msgs)


class MainCompressGateTests(unittest.TestCase):
    """main._compress_and_save：同一 Token 门在落盘侧生效。"""

    def test_under_budget_no_compression(self):
        msgs = [{"role": "user", "content": "短"} for _ in range(25)]
        saved = {}
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_CLOUD":
                                          "100000"}):
            with mock.patch.object(main_mod, "save_memory",
                                   side_effect=lambda m, f: saved.update(
                                       n=len(m))):
                main_mod._compress_and_save(msgs, "unused.json")
        self.assertEqual(saved.get("n"), 25)   # 原样落盘，未压缩

    def test_over_budget_compresses_before_save(self):
        msgs = ([{"role": "system", "content": "sys"}]
                + _fat(6) + _tiny(10))
        saved = {}
        with mock.patch.dict(os.environ, {"XIAOJU3_CONTEXT_WINDOW_CLOUD":
                                          "500"}):
            with mock.patch.object(
                    brain, "ask_local", return_value="落盘侧摘要"):
                with mock.patch.object(
                        main_mod, "save_memory",
                        side_effect=lambda m, f: saved.update(msgs=list(m))):
                    main_mod._compress_and_save(msgs, "unused.json")
        persisted = saved.get("msgs") or []
        self.assertTrue(any("【前情提要】" in str(m.get("content", ""))
                            for m in persisted))
        self.assertLess(len(persisted), len(msgs))


if __name__ == "__main__":
    unittest.main()

class DynamicEngineWindowTests(unittest.TestCase):
    """动态窗口（2026-10-28 二轮，秘书会诊）：按服务引擎分叉窗口口径。"""

    def test_no_cloud_key_uses_local_window(self):
        # CLOUD_KEY 缺席 → engine=local：大历史在 4096 口径下必压
        msgs = [{"role": "system", "content": "sys"}] + _fat(3) + _tiny(10)
        with mock.patch.object(brain, "CLOUD_KEY", ""):
            with mock.patch.dict(os.environ, {
                    "XIAOJU3_CONTEXT_WINDOW_TOKENS": "500"}):
                with mock.patch.object(brain, "ask_local",
                                       return_value="本地口径摘要"):
                    out = brain._compress_history(msgs, "ut9")
        self.assertIsNot(out, msgs)

    def test_cloud_key_ignores_local_window(self):
        # CLOUD_KEY 在位 → engine=cloud：同历史在 cloud 窗口下不压（云端
        # 32000 宽口径——本地窗口 env 不再误伤云端长对话）
        msgs = [{"role": "system", "content": "sys"}] + _fat(3) + _tiny(10)
        with mock.patch.object(brain, "CLOUD_KEY", "sk-test"):
            with mock.patch.dict(os.environ, {
                    "XIAOJU3_CONTEXT_WINDOW_TOKENS": "500",
                    "XIAOJU3_CONTEXT_WINDOW_CLOUD": "100000"}):
                with mock.patch.object(brain, "ask_local",
                                       side_effect=AssertionError("不该调用")):
                    out = brain._compress_history(msgs, "ut10")
        self.assertIs(out, msgs)

