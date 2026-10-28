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
        # 图片类型=剥离（#322 硬门拍板：QQ 无视觉能力，模型知道有图
        # 也只会编造图片内容）；其余类型照旧翻译
        self.assertNotIn("用户发了一张图片", t)
        for kw in ("用户发了个表情", "用户发了一段语音",
                   "用户发了一个视频", "用户发了一个文件", "用户@了你"):
            self.assertIn(kw, t)

    def test_plain_text_passthrough(self):
        self.assertEqual(main._translate_cq_for_brain("你好"), "你好")


class ImageHardGateTests(unittest.TestCase):
    """#322 收尾硬门锚（三锚对应三消息形状，2026-10-12 拍板）：
    纯图=确定性诚实回应（不走 LLM，#278 同构）；图文混合=文字正常
    回应+图从 brain 输入剥离（禁评论图片=防纯编造）；纯文字=不受影响。"""

    def test_pure_image_deterministic_reply(self):
        """纯图（无文字）→ 确定性回应：诚实自曝看不懂，不含催促。"""
        r = main._image_gate_reply("[CQ:image,file=x.png]", "")
        self.assertIsNotNone(r)
        self.assertIn("看不懂图片内容", r)
        self.assertNotIn("已存进小仓库", r)   # 谎报收藏禁绝
        self.assertNotIn("[CQ:", r)

    def test_image_text_mix_strips_image_from_brain_input(self):
        """图文混合 → brain 输入只剩文字（图剥离=禁评论图片的结构性
        实现）；门放行（返回 None 交 brain 正常回应文字）。"""
        t = main._translate_cq_for_brain("[CQ:image,file=x.png]这是什么意思")
        self.assertEqual(t, "这是什么意思")   # 图剥离、文字保留
        self.assertIsNone(
            main._image_gate_reply("[CQ:image,file=x.png]", t))

    def test_image_text_with_ref_words_deterministic(self):
        """#322 v2 扩门：图文混合+指代图词（这图/图片/这张/看图/图里）
        → 确定性诚实回应（图剥离后指代必语义断裂——实测 4/4 反问重发
        不可能的图）。"""
        for text in ("这图里是啥", "图片上是什么", "看看这张",
                     "上面那张啥意思", "帮我看图"):
            r = main._image_gate_reply("[CQ:image,file=x]" + text, text)
            self.assertIsNotNone(r, text)
            self.assertIn("看不懂图片内容", r)
            self.assertNotIn("已存进小仓库", r)

    def test_image_text_unrelated_passes_through(self):
        """#322 v2 对照：图文混合+无关文字（文字本身完整问题）→ 正常
        放行 LLM（门返回 None）。"""
        for text in ("今天天气怎么样", "帮我记个事"):
            self.assertIsNone(
                main._image_gate_reply("[CQ:image,file=x]" + text, text))

    def test_plain_image_regression(self):
        """纯图回归：原硬门文案不变。"""
        r = main._image_gate_reply("[CQ:image,file=x]", "")
        self.assertEqual(r, main._GATE_PURE_IMAGE_REPLY)

    def test_plain_text_unaffected_and_wiring(self):
        """纯文字 → 门返回 None 不受影响；接线锚：handle_message 内
        翻译→硬门→append 顺序正确。"""
        self.assertIsNone(main._image_gate_reply("你好呀", "你好呀"))
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
        i_t = src.index("message = _translate_cq_for_brain(raw_message)")
        i_g = src.index("gate_reply = _image_gate_reply(raw_message, message)",
                        i_t)
        i_a = src.index("messages_qq.append", i_g)
        self.assertLess(i_t, i_g)
        self.assertLess(i_g, i_a)   # 翻译→门→进 brain 顺序锁死


class IntegrationHooksTests(unittest.TestCase):
    """接线锚：QQ 出口用 _sanitize_qq_reply（修 B v2 修 3：消毒+沉默兜底，
    原直调 _strip_llm_pollution 已收编）；QQ 进 brain 用翻译。"""

    def test_qq_output_hook(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
        self.assertIn("reply = _sanitize_qq_reply(reply)", src)
        self.assertNotIn("reply = _strip_llm_pollution(reply)", src)
        # 翻译发生在 QQ 进 brain 前（messages_qq.append 之前）
        i_translate = src.index("message = _translate_cq_for_brain(raw_message)")
        i_append = src.index("messages_qq.append", i_translate)
        self.assertLess(i_translate, i_append)


class RoleNamePrefixTests(unittest.TestCase):
    """角色名前缀剥（2026-10-28 队长真机实锤"小橘：主人…"）：^ 只剥开头，
    正文中间"小橘："不碰（队长口径）；纯标签剥空→沉默兜底。"""

    def test_wake_shape_stripped(self):
        """截图实锤形态：唤醒消息开头"小橘： "剥净。"""
        self.assertEqual(
            main._sanitize_qq_reply("小橘： 主人，你最近喜欢《明日方舟》吗？"),
            "主人，你最近喜欢《明日方舟》吗？")

    def test_variant_labels_stripped(self):
        for raw, want in (("Bot: hello", "hello"),
                          ("AI：你好呀", "你好呀"),
                          ("助手: 在的", "在的"),
                          ("assistant：好的", "好的")):
            self.assertEqual(main._strip_role_name_prefix(raw), want)

    def test_middle_not_touched(self):
        """正文中间的"小橘："不剥（只剥开头）。"""
        self.assertEqual(main._sanitize_qq_reply("我喜欢说小橘：三个字"),
                         "我喜欢说小橘：三个字")
        self.assertEqual(main._strip_role_name_prefix("我叫小橘：这是我名字"),
                         "我叫小橘：这是我名字")

    def test_no_colon_not_stripped(self):
        """无冒号不算标签（防误伤"AI很有趣"这类开头）。"""
        self.assertEqual(main._strip_role_name_prefix("AI很有趣"), "AI很有趣")

    def test_pure_label_falls_back(self):
        """纯标签被剥空 → 诚实兜底文案（非静默）。"""
        self.assertEqual(main._sanitize_qq_reply("小橘："),
                         main.SANITIZED_EMPTY_FALLBACK)

    def test_clean_reply_untouched(self):
        self.assertEqual(main._sanitize_qq_reply("周末想和主人一起玩"),
                         "周末想和主人一起玩")


if __name__ == "__main__":
    unittest.main()
