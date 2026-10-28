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


class QualityGuardEdgeTests(unittest.TestCase):
    """质量门边界补强（2026-10-28 长程批任务 3a：严丝合缝）。"""

    def setUp(self):
        from global_task_reviewer import QualityGuard
        self.g = QualityGuard()

    def test_empty_and_none_text(self):
        self.assertEqual(self.g.audit(""), [])
        self.assertEqual(self.g.audit(None), [])

    def test_multiple_rules_one_hit_each(self):
        text = ("综上所述这是个好东西。如果还有其他问题需要帮助，"
                "请随时告诉我！")
        v = self.g.audit(text)
        names = [n for n, _, _ in v]
        self.assertIn("AI 味总结", names)
        self.assertIn("套话收尾", names)
        # 每规则只记一处（审计定位用，不刷屏）
        self.assertEqual(len(names), len(set(names)))

    def test_severity_passthrough_custom_rule(self):
        self.g.add_rule("硬禁词", r"机密词", severity="abort")
        v = self.g.audit("这句话含机密词请处理")
        self.assertIn(("硬禁词", "abort"), [(n, s) for n, s, _ in v])

    def test_echo_below_threshold_not_flagged(self):
        # 首句与原话重合不足 0.8：只复述部分关键词不算复读
        v = self.g.audit("你问的是天气和心情两件事呢。",
                         user_msg="你今天心情怎么样")
        self.assertNotIn("复读原话", [n for n, _, _ in v])

    def test_echo_ignores_punctuation(self):
        # 原话带标点/空格照样命中（判据先去标点）
        v = self.g.audit("你今天心情怎么样？挺好的喵。",
                         user_msg="你，今天！心情怎么样？？？")
        self.assertTrue(any(n == "复读原话" for n, _, _ in v))

    def test_rules_instances_isolated(self):
        from global_task_reviewer import QualityGuard, DEFAULT_QUALITY_RULES
        base_len = len(DEFAULT_QUALITY_RULES)
        g2 = QualityGuard()
        self.g.add_rule("临时规则", r"XYZZY")
        self.assertEqual(len(g2.rules), base_len)      # 他实例不受染
        self.assertEqual(len(DEFAULT_QUALITY_RULES), base_len)  # 默认表不受染

    def test_long_text_first_sentence_echo(self):
        # 复读判定只看首句——首句复读即报，后续正文不影响
        text = ("你今天心情怎么样？另外今天天气不错，花也开了，"
                "适合出门走走看看风景什么的。")
        v = self.g.audit(text, user_msg="你今天心情怎么样")
        self.assertTrue(any(n == "复读原话" for n, _, _ in v))

    def test_empty_user_msg_skips_echo(self):
        self.assertEqual(
            [n for n, _, _ in self.g.audit("你今天心情怎么样？")],
            [])


class FalsifyTests(unittest.TestCase):
    """证伪思维（2026-10-28 吸收白帽挖洞思维）：先说清被推翻的标准再走。"""

    def setUp(self):
        from global_task_reviewer import TaskLedger
        self.led = TaskLedger()
        self.led.start_task("f1", "原始请求")

    def test_rule_verdict_ex_parses_falsify(self):
        from global_task_reviewer import rule_verdict_ex
        out = {}
        def cloud(prompt):
            out["prompt"] = prompt
            return "CONTINUE\n证伪条件：如果连续两次返回空数据就说明接口选错了"
        verdict, falsify = rule_verdict_ex("req", "chain", "next",
                                           cloud_chat_fn=cloud)
        self.assertEqual(verdict, "CONTINUE")
        self.assertIn("空数据", falsify)
        self.assertIn("证伪条件", out["prompt"][0]["content"])  # system 段带证伪问法

    def test_abort_has_no_falsify(self):
        from global_task_reviewer import rule_verdict_ex
        verdict, falsify = rule_verdict_ex(
            "req", "chain", "next", cloud_chat_fn=lambda p: "ABORT")
        self.assertEqual(verdict, "ABORT")
        self.assertEqual(falsify, "")

    def test_cloud_fail_returns_continue_empty(self):
        from global_task_reviewer import rule_verdict_ex
        def boom(p):
            raise RuntimeError("云端挂")
        verdict, falsify = rule_verdict_ex("req", "chain", "next",
                                           cloud_chat_fn=boom)
        self.assertEqual(verdict, "CONTINUE")
        self.assertEqual(falsify, "")

    def test_ledger_falsify_store_and_read(self):
        self.led.set_falsify("f1", "返回空就推翻")
        self.assertEqual(self.led.get_falsify("f1"), "返回空就推翻")
        self.assertEqual(self.led.get_falsify("nope"), "")
