# -*- coding: utf-8 -*-
"""修 B 锚：出口否定感知兜底（design_fix_no_fake_completion 方案 A+B）。

冒烟 R2 实锤：模型把诚实拒绝写进思考卡、正文剥空 → brain 兜底注入
"操作已完成。"=正文虚假完成。本文件锁：否定感知守卫/真完成回归/
双空回归/prompt 补条。
"""
import brain
import prompts


# 1 R2 原样形态：思考卡含诚实拒绝 + 正文剥空 → 诚实文案（非"操作已完成"）
def test_r2_form_gets_honest_body():
    raw = ('[思考] 主人要删桌面上一个测试文件，但我的工具里只有列目录、读文件、'
           '写文件，没有删除功能，不能假装删了。\n'
           '[计划] 1. 说明我没有删除工具；2. 列出我实际能做的事，让主人决定。'
           '这个我真干不了——我手上的工具只能列目录、读文件、写文件。')
    out = brain._seal_bare_cot(raw)
    assert "操作已完成" not in out
    assert brain.NO_ABILITY_BODY_PLACEHOLDER in out


# 2 真完成场景回归：思考无否定+不可回补 → 原兜底"操作已完成。"逐字节不变
def test_true_complete_keeps_default_placeholder():
    out = brain._wrap_think("[思考] 工具执行成功。\n[计划] 完成。", "")
    assert "操作已完成。" in out
    assert brain.NO_ABILITY_BODY_PLACEHOLDER not in out


# 3 回补路径不受守卫影响：思考可回补时正文=思考内容（守卫不触发）
def test_promotion_path_unaffected():
    out = brain._wrap_think("[思考] 操作执行成功。", "")
    assert "<think>[思考] 操作执行成功。</think>操作执行成功。" == out


# 4 双空回归：两侧全空 → 思考占位符+"操作已完成。"（无否定可能，行为不变）
def test_double_blank_regression():
    out = brain._wrap_think(None, None)
    assert brain.CHAT_THINKING_PLACEHOLDER in out
    assert "操作已完成。" in out


# 5 body 非空：守卫不触发，正文原样
def test_nonempty_body_passthrough():
    out = brain._wrap_think("[思考] 没有删除功能。", "这个我真干不了。")
    assert "这个我真干不了。" in out
    assert brain.NO_ABILITY_BODY_PLACEHOLDER not in out


# 6 否定词表参数化：逐词命中守卫（不可回补形态=含 [计划]，回补优先于守卫
#    ——可回补时诚实内容直接升正文，无需守卫，见锚 3）
def test_negation_words_parameterized():
    for word in ("没有", "不能", "无法", "干不了", "做不到", "不具备",
                 "无权", "不支持"):
        out = brain._wrap_think(
            f"[思考] 工具执行成功，{word}删除工具。\n[计划] 如实说明。", "")
        assert brain.NO_ABILITY_BODY_PLACEHOLDER in out, word


# 7 拒绝文案锁定（措辞=对外口径）
def test_no_ability_wording_locked():
    assert brain.NO_ABILITY_BODY_PLACEHOLDER == (
        "这件事我做不到——我没有对应的能力或工具。（详情见上方思考）")


# 8 方案 B：SYSTEM_PROMPT 补条在位（正文与思考必须一致）
def test_prompt_consistency_rule_present():
    content = prompts.SYSTEM_PROMPT["content"]
    assert "正文与思考必须说同一件事" in content
    assert "正文为空比说谎好" in content
