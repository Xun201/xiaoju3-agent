# -*- coding: utf-8 -*-
"""全局任务审查员骨架单测（2026-10-28 午休施工批）。

覆盖：触发三则（T1 链长/T2 跳族+语义距离/T3 败后续）+高副作用强制+
批量链保护+记账/驱逐+语义距离函数+verdict 骨架。全部纯内存零 IO。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from global_task_reviewer import (  # noqa: E402
    TaskLedger, semantic_distance, tool_family, is_high_side_effect,
    rule_verdict)


class SemanticDistanceTests(unittest.TestCase):
    def test_same_topic_low_distance(self):
        self.assertLess(semantic_distance("帮我打开客厅的灯", "打开客厅灯"),
                        0.5)

    def test_unrelated_high_distance(self):
        self.assertGreater(semantic_distance("帮我打开客厅的灯",
                                             "北京今天天气怎么样"), 0.7)

    def test_empty_handles(self):
        self.assertEqual(semantic_distance("", "x"), 1.0)


class ToolFamilyTests(unittest.TestCase):
    def test_ha_family_by_tool_and_args(self):
        self.assertEqual(tool_family("control_ha_device",
                                     {"entity_id": "light.bedroom"}), "ha")

    def test_unknown_family(self):
        self.assertEqual(tool_family("mystery_tool"), "unknown")

    def test_high_side_effect(self):
        self.assertTrue(is_high_side_effect("control_ha_device"))
        self.assertTrue(is_high_side_effect("write_file"))
        self.assertFalse(is_high_side_effect("get_ha_devices"))
        self.assertFalse(is_high_side_effect("read_file"))


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.led = TaskLedger()

    def test_below_threshold_no_review(self):
        self.led.start_task("s1", "打开台灯")
        self.led.record("s1", "control_ha_device", "light.a", True)
        need, why = self.led.should_review("s1", "get_ha_devices")
        # 第 2 次调用（链 1+1<3），同族，无失败 → 直通
        self.assertFalse(need)

    def test_t1_chain_len_triggers(self):
        self.led.start_task("s1", "帮我查点东西")
        for i in range(2):
            self.led.record("s1", "web_search", f"q{i}", True)
        need, why = self.led.should_review("s1", "web_search")
        self.assertTrue(need)
        self.assertIn("T1", why)

    def test_t2_family_switch_triggers(self):
        self.led.start_task("s1", "看看今天怎么样")
        self.led.record("s1", "web_search", "今日新闻", True)
        need, why = self.led.should_review("s1", "control_ha_device")
        # 第 2 次但跳族（web→ha）→ T2 触发
        self.assertTrue(need)
        self.assertIn("T2", why)

    def test_t3_after_failure_triggers(self):
        self.led.start_task("s1", "随便聊聊")
        self.led.record("s1", "web_search", "q", ok=False)
        need, why = self.led.should_review("s1", "web_search")
        self.assertTrue(need)
        self.assertIn("T3", why)

    def test_side_effect_forces_review_even_first_call(self):
        self.led.start_task("s1", "帮我个忙")
        need, why = self.led.should_review("s1", "restart_service")
        self.assertTrue(need)
        self.assertIn("T-SIDE", why)

    def test_batch_chain_protected(self):
        """合法批量链：请求含列举信号+同族重复 → T1 不触发。"""
        led = TaskLedger()
        led.start_task("s2", "把所有房间的灯都打开")
        led.record("s2", "control_ha_device", "light.a", True)
        led.record("s2", "control_ha_device", "light.b", True)
        need, why = led.should_review("s2", "control_ha_device")
        self.assertFalse(need, why)

    def test_evict_clears_state(self):
        self.led.start_task("s3", "任务")
        self.led.evict("s3")
        need, _ = self.led.should_review("s3", "anything")
        self.assertFalse(need)
        self.led.record("s3", "tool_x")   # 不炸（惰性重建）

    def test_unknown_session_zero_cost(self):
        need, why = self.led.should_review("ghost", "any_tool")
        self.assertFalse(need)


class RuleVerdictTests(unittest.TestCase):
    def test_no_channel_continue(self):
        self.assertEqual(rule_verdict("req", "chain", "tool"), "CONTINUE")

    def test_cloud_abort(self):
        def cloud(messages):
            return "ABORT"
        self.assertEqual(rule_verdict("req", "chain", "tool", cloud), "ABORT")

    def test_cloud_fail_continue(self):
        def cloud(messages):
            raise TimeoutError("云炸了")
        self.assertEqual(rule_verdict("req", "chain", "tool", cloud),
                         "CONTINUE")   # 审查员故障绝不放大成主链故障


if __name__ == "__main__":
    unittest.main()


class MechanicalLoopTests(unittest.TestCase):
    """T2b 机械循环检测（跨语言稳定：指纹=工具+参数，不与中文请求比）。"""

    def test_three_identical_steps_trigger(self):
        # chain_len_trigger 调高与 T1 解耦，专测机械循环逻辑
        led = TaskLedger(chain_len_trigger=99)
        led.start_task("s", "随便处理下这个文件")
        for _ in range(3):
            led.record("s", "read_file", "a.txt", True)
        need, why = led.should_review("s", "read_file")
        self.assertTrue(need)
        self.assertIn("机械循环", why)

    def test_varied_steps_no_trigger(self):
        led = TaskLedger(chain_len_trigger=99)   # 同上，与 T1 解耦
        led.start_task("s", "整理项目")
        led.record("s", "read_file", "a.txt", True)
        led.record("s", "read_file", "b.txt", True)
        led.record("s", "read_file", "c.txt", True)
        need, _ = led.should_review("s", "read_file")
        self.assertFalse(need)


class QualityGuardTests(unittest.TestCase):
    """结果质量审查门（借鉴 hallmark 规则化审查：主观烂→可审计规则）。"""

    def setUp(self):
        from global_task_reviewer import QualityGuard
        self.g = QualityGuard()

    def test_slop_closing_detected(self):
        v = self.g.audit("今天是晴天。如果还有其他问题需要帮助，请随时告诉我！")
        self.assertTrue(any(n == "套话收尾" for n, _, _ in v))

    def test_eval_corpus_detected(self):
        v = self.g.audit("这款游戏让我深刻体会到团队合作的重要性。")
        self.assertTrue(any(n == "评测腔" for n, _, _ in v))

    def test_echo_detected_as_abort(self):
        v = self.g.audit("你今天心情怎么样？还行。", user_msg="你今天心情怎么样")
        names = {n: s for n, s, _ in v}
        self.assertEqual(names.get("复读原话"), "abort")

    def test_clean_text_zero_violation(self):
        self.assertEqual(self.g.audit("在呢喵，尾巴都竖起来了。"), [])

    def test_custom_rule_addable(self):
        self.g.add_rule("禁词测试", r"万万不能说")
        v = self.g.audit("这句话里有万万不能说的词。")
        self.assertTrue(any(n == "禁词测试" for n, _, _ in v))
