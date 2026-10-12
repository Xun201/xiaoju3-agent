# -*- coding: utf-8 -*-
"""chain_of_thought 模块锚（#326）——VARIANTS + normalize + strip_pollution。"""
import unittest
import chain_of_thought as cot


class NormalizeTests(unittest.TestCase):
    def test_chinese_colon(self):
        t = cot.normalize("思考：需要分析\n计划：执行")
        self.assertIn("[思考] 需要分析", t)
        self.assertIn("[计划] 执行", t)

    def test_english_colon(self):
        t = cot.normalize("Think: analyze\nPlan: do it")
        self.assertIn("[思考] analyze", t)
        self.assertIn("[计划] do it", t)

    def test_plain_text_untouched(self):
        self.assertEqual(cot.normalize("普通正文"), "普通正文")


class StripPollutionTests(unittest.TestCase):
    def test_xml_think_stripped(self):
        self.assertEqual(cot.strip_pollution("<think>推理</think>正文"), "正文")

    def test_square_bracket_stripped(self):
        self.assertEqual(cot.strip_pollution("[think]推理[/think]正文"), "正文")

    def test_action_json_stripped(self):
        self.assertEqual(
            cot.strip_pollution('{"action": "show_image"}正文'), "正文")

    def test_full_pollution_stripped(self):
        t = cot.strip_pollution(
            "[think]推理[/think][plan]步骤[/plan]"
            '{"action": "show_image"}结果')
        self.assertEqual(t, "结果")

    def test_clean_text_passthrough(self):
        self.assertEqual(cot.strip_pollution("干净文本"), "干净文本")


class ParseThinkingFieldTests(unittest.TestCase):
    def test_with_thinking_field(self):
        th, ct = cot.parse_thinking_field(
            {"thinking": "推理过程", "content": "答案"})
        self.assertEqual(th, "推理过程")
        self.assertEqual(ct, "答案")

    def test_without_thinking_field(self):
        th, ct = cot.parse_thinking_field({"content": "只有答案"})
        self.assertEqual(th, "")
        self.assertEqual(ct, "只有答案")

    def test_none_message(self):
        th, ct = cot.parse_thinking_field(None)
        self.assertEqual(th, "")
        self.assertEqual(ct, "")


if __name__ == "__main__":
    unittest.main()
