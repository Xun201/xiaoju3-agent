# -*- coding: utf-8 -*-
"""#322 QQ 出口/入口消毒锚（F1+F2，坑库 #20）。

F1 = _strip_llm_pollution：<think> XML + 方括号 [think]/[plan] 变体 +
     幻觉 action JSON 全剥（图片消息混合体直发实锤）。
F2 = _translate_cq_for_brain：CQ 码全类型 → 人类可读描述（裸 CQ 码 =
     幻觉触发源，坑库 #20）。
"""
import os
import unittest

import main


class StripLlmPollutionTests(unittest.TestCase):
    """F1：QQ 出口消毒。"""

    def test_square_bracket_variants_stripped(self):
        t = main._strip_llm_pollution(
            "[think]推理[/think][plan]步骤[/plan]你好呀")
        self.assertEqual(t, "你好呀")

    def test_action_json_stripped(self):
        t = main._strip_llm_pollution(
            '{"action": "show_image", "file": "x"}你好呀')
        self.assertEqual(t, "你好呀")

    def test_mixed_pollution_full_strip(self):
        """实锤混合体（[think]+[plan]+action JSON）一次剥净。"""
        t = main._strip_llm_pollution(
            '[think]分析图片[/think][plan]调用工具[/plan]'
            '{"action": "show_image", "file": "abc.jpg"}好的')
        self.assertEqual(t, "好的")

    def test_xml_think_still_stripped(self):
        """回归：原 XML 形态 <think> 剥除不回退。"""
        t = main._strip_llm_pollution('<think>推理</think>正文')
        self.assertEqual(t, "正文")


class TranslateCqTests(unittest.TestCase):
    """F2：CQ 码全类型 → 人类可读描述。"""

    def test_all_types_translated(self):
        raw = ('[CQ:image,file=a.jpg][CQ:face,id=1][CQ:record,file=b.mp3]'
               '[CQ:video,file=c.mp4][CQ:file,id=d][CQ:at,qq=123] 在吗')
        t = main._translate_cq_for_brain(raw)
        self.assertNotIn("[CQ:", t)
        for kw in ("用户发了一张图片", "用户发了个表情", "用户发了一段语音",
                   "用户发了一个视频", "用户发了一个文件", "用户@了你"):
            self.assertIn(kw, t)

    def test_plain_text_passthrough(self):
        self.assertEqual(main._translate_cq_for_brain("你好"), "你好")


class IntegrationHooksTests(unittest.TestCase):
    """接线锚：QQ 出口用 _strip_llm_pollution；QQ 进 brain 用翻译。"""

    def test_qq_output_hook(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
        self.assertIn("reply = _strip_llm_pollution(reply)", src)
        # 翻译发生在 QQ 进 brain 前（messages_qq.append 之前）
        i_translate = src.index("message = _translate_cq_for_brain(raw_message)")
        i_append = src.index("messages_qq.append", i_translate)
        self.assertLess(i_translate, i_append)


if __name__ == "__main__":
    unittest.main()
