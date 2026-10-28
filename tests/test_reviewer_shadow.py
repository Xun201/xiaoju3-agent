# -*- coding: utf-8 -*-
"""全局任务审查员·影子模式接线测试（2026-10-28 上车）。

队长红线：**只观察不拦截**——本测试网锁死三条：
1. _reviewer_observe 无论 verdict 如何只返回日志串（绝不改控制流）；
2. 环境开关 XIAOJU3_REVIEWER_SHADOW_MODE=0 时三函数全旁路零动作；
3. 账本跨轮累积（单轮单工具架构下不清链）+ FIFO 驱逐防膨胀。
"""
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import brain  # noqa: E402
from global_task_reviewer import TaskLedger  # noqa: E402


class LedgerAccumulationTests(unittest.TestCase):
    """跨轮累积三件套：touch 不清链 / chain_summary 格式 / FIFO 驱逐。"""

    def test_touch_keeps_chain_and_updates_request(self):
        led = TaskLedger()
        led.start_task("s1", "第一句")
        led.record("s1", "ha_get_state")
        led.touch("s1", "第二句")
        st = led._tasks["s1"]
        self.assertEqual(st.orig_request, "第二句")
        self.assertEqual(len(st.chain), 1)   # 链没被清——影子数据靠它

    def test_touch_first_time_equals_start(self):
        led = TaskLedger()
        led.touch("s1", "首次")
        self.assertEqual(led.orig_request_of("s1"), "首次")

    def test_chain_summary_format(self):
        led = TaskLedger()
        led.start_task("s1", "req")
        led.record("s1", "web_search", ok=True)
        led.record("s1", "ha_call", ok=False)
        self.assertEqual(led.chain_summary("s1"),
                         "web_search(ok)/ha_call(FAIL)")

    def test_fifo_eviction(self):
        led = TaskLedger(max_sessions=2)
        led.start_task("a", "r")
        led.start_task("b", "r")
        led.start_task("c", "r")     # a 被逐出
        self.assertNotIn("a", led._tasks)
        self.assertIn("c", led._tasks)


class ShadowObserveTests(unittest.TestCase):
    """brain._reviewer_observe：只观察口径 + 环境开关。"""

    def setUp(self):
        brain._reviewer_ledger.evict("ut")
        self.addCleanup(brain._reviewer_ledger.evict, "ut")

    def test_mechanical_loop_triggers_and_logs(self):
        # 同会话连记 3 条同工具同参 → 第 4 次前必触发
        for _ in range(3):
            brain._reviewer_record("ut", "web_search", {"query": "天气"},
                                   ok=True)
        with mock.patch.dict(os.environ,
                             {"XIAOJU3_REVIEWER_SHADOW_CLOUD": "1"}):
            with mock.patch.object(brain, "rule_verdict",
                                   return_value="ABORT"):
                log = brain._reviewer_observe("ut", "web_search",
                                              {"query": "天气"})
        self.assertIsInstance(log, str)
        self.assertIn("🛡️[影子审查]", log)
        self.assertIn("Trigger: T2", log)
        self.assertIn("Action: INTERRUPT", log)   # 只是日志，不是拦截

    def test_shadow_cloud_off_by_default(self):
        # 影子期默认不调云（正常聊天序列不该被加 2-3s 云延迟）
        for _ in range(3):
            brain._reviewer_record("ut", "web_search", {"query": "天气"},
                                   ok=True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XIAOJU3_REVIEWER_SHADOW_CLOUD", None)
            with mock.patch.object(
                    brain, "rule_verdict",
                    side_effect=AssertionError("影子期不该调云")):
                log = brain._reviewer_observe("ut", "web_search",
                                              {"query": "天气"})
        self.assertIsInstance(log, str)
        self.assertIn("Trigger: T2", log)
        self.assertIn("Action: PASS", log)
        self.assertIn("SHADOW", log)

    def test_tside_skips_cloud(self):
        brain._reviewer_ledger.start_task("ut", "开灯")
        with mock.patch.object(brain, "rule_verdict",
                               side_effect=AssertionError("T-SIDE 不发云")):
            log = brain._reviewer_observe("ut", "control_ha_device",
                                          {"entity_id": "light.x", "action": "turn_on"})
        self.assertIsInstance(log, str)
        self.assertIn("Trigger: T-SIDE", log)
        self.assertIn("Action: PASS", log)

    def test_observe_never_raises_never_blocks(self):
        # 云端故障/账本异常 → 仍返回字符串（PASS 兜底），绝不抛、绝不拦截
        brain._reviewer_ledger.start_task("ut", "req")
        for _ in range(3):
            brain._reviewer_record("ut", "web_search", {"query": "x"},
                                   ok=True)
        with mock.patch.dict(os.environ,
                             {"XIAOJU3_REVIEWER_SHADOW_CLOUD": "1"}):
            with mock.patch.object(brain, "rule_verdict",
                                   side_effect=RuntimeError("云端炸了")):
                log = brain._reviewer_observe("ut", "web_search",
                                              {"query": "x"})
        self.assertIsInstance(log, str)
        self.assertIn("Action: PASS", log)

    def test_shadow_off_full_bypass(self):
        brain._reviewer_ledger.start_task("ut", "req")
        for _ in range(3):
            brain._reviewer_ledger.record("ut", "web_search", "q", ok=True)
        env = {"XIAOJU3_REVIEWER_SHADOW_MODE": "0"}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(brain._reviewer_observe("ut", "web_search",
                                                      {"query": "x"}))
            brain._reviewer_record("ut", "ha_call", {}, ok=False)
            brain._reviewer_touch("ut", "新消息")
        # 关闭期间链与账本零变化
        self.assertEqual(len(brain._reviewer_ledger._tasks["ut"].chain), 3)
        self.assertEqual(brain._reviewer_ledger.orig_request_of("ut"), "req")

    def test_default_is_on(self):
        # 缺省（环境变量未设）= 影子开启
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XIAOJU3_REVIEWER_SHADOW_MODE", None)
            self.assertTrue(brain._reviewer_shadow_on())
            os.environ["XIAOJU3_REVIEWER_SHADOW_MODE"] = "1"
            self.assertTrue(brain._reviewer_shadow_on())

    def test_record_after_failure_marks_ok_false(self):
        brain._reviewer_ledger.start_task("ut", "req")
        brain._reviewer_record("ut", "ha_call", {}, ok=False)
        self.assertEqual(brain._reviewer_ledger.chain_summary("ut"),
                         "ha_call(FAIL)")


if __name__ == "__main__":
    unittest.main()
