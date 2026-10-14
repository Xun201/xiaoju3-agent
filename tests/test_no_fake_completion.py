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


# ==================== 修 B v2 修 1：澄清反问升正文（2026-10-14 晚冒烟实锤） ====================
# 19:27 生产实锤：模型把"要问用户的话"写在思考卡末段（无否定词），
# 正文被兜底成"操作已完成。"（澄清型虚假完成）。问句升正文=治根不治形。

SMOKE_THINKING = ("[思考] 需要确认具体是哪个文件，才能执行删除操作。\n"
                  "[计划] 请告诉我桌面上具体是哪个测试文件需要删除呢？\n"
                  "哪个文件是你要我帮忙删除的呢？")


def test_v2_clarifying_question_promoted():
    """19:27 私聊轮原样回放：末段澄清问句升为正文（非"操作已完成"）。"""
    r = brain._wrap_think(SMOKE_THINKING, "")
    body = r.split("</think>", 1)[1]
    assert body == "哪个文件是你要我帮忙删除的呢？", r
    assert "操作已完成" not in body
    assert "[思考]" in r.split("</think>")[0]  # 思考卡保留


def test_v2_internal_self_question_not_promoted():
    """内部自问（无收件人词+自计划句式）不升 → 维持占位兜底。"""
    r = brain._wrap_think("[思考] 用户想删文件。\n[计划] 先查注册表。\n我应该先做什么？", "")
    body = r.split("</think>", 1)[1]
    assert "操作已完成。" in body
    assert "我应该先做什么" not in body


def test_v2_negation_priority_unchanged():
    """否定优先契约不变：不可回补形状含否定+尾部问句 → 仍走诚实拒绝文案。"""
    r = brain._wrap_think("[思考] 我没有删除工具，无法操作。\n[计划] 建议用户手动处理。\n你想删哪个文件呢？", "")
    body = r.split("</think>", 1)[1]
    assert "这件事我做不到" in body


def test_v2_plain_statement_not_promoted():
    """末段普通陈述（非问句）不升 → 占位兜底。"""
    r = brain._wrap_think("[思考] 用户想删文件。\n[计划] 需要先确认文件名。", "")
    assert "操作已完成。" in r.split("</think>", 1)[1]


def test_v2_overlong_question_not_promoted():
    """>=200 字超长问句不升（防内部推理误升）。"""
    longq = "你要我删" + "非" * 200 + "常多的文件吗？"
    r = brain._wrap_think(f"[思考] x。\n[计划] y。\n{longq}", "")
    assert "操作已完成。" in r.split("</think>", 1)[1]


def test_v2_normal_chat_zero_change():
    """常规闲聊（正文非空）逐字节零变化（回归闸）。"""
    r = brain._wrap_think("[思考] 主人在打招呼。", "在呢～")
    assert r == "<think>[思考] 主人在打招呼。</think>在呢～"


# ==================== 修 B v3 修 A：能力宣称守卫（2026-10-14 晚重测实锤） ====================
# 22:2x 重测实锤：模型把"我会做"写进思考卡（无否定无问句，"我会打开桌面
# 看看"），正文剥空 → 落"操作已完成。"=虚假完成第三形态。将来时宣称+无
# [行动] 工具执行=宣称必假 → 诚实兜底。

V3_CLAIM_THINKING = ("[思考] 这个任务我能完成，不过得先确认一下文件的位置。\n"
                     "[计划] 我会打开桌面看看。")


def test_v3_capability_claim_honest_fallback():
    """重测实锤原样回放：将来时宣称+正文剥空 → 诚实兜底（非"操作已完成"）。"""
    r = brain._wrap_think(V3_CLAIM_THINKING, "")
    assert r.split("</think>", 1)[1] == brain.HALLUCINATED_TOOL_BODY


def test_v3_completed_tense_untouched():
    """已完成时态（已/任务完成）不受扰：不可回补形状维持真完成占位符。"""
    r = brain._wrap_think("[思考] 已删除桌面的测试文件。\n[计划] 任务完成。", "")
    assert r.split("</think>", 1)[1] == "操作已完成。"


def test_v3_single_think_promotion_untouched():
    """单[思考]前缀真完成提升路径不受扰（既有 ④ 行为零回归）。"""
    r = brain._wrap_think("[思考] 已删除桌面的测试文件。", "")
    assert r.split("</think>", 1)[1] == "已删除桌面的测试文件。"


def test_v3_action_marker_present_not_fired():
    """[行动] 工具执行标记在场 → 守卫不抢（工具环辖区）。"""
    r = brain._wrap_think('[思考] 我会调用删除工具。\n[行动] {"tool": "del"}', "")
    assert "操作已完成。" in r.split("</think>", 1)[1]
    assert "我还没学会" not in r


def test_v3_negation_priority_over_claim():
    """否定优先契约不变：否定+将来时宣称并存 → 仍走诚实拒绝文案。"""
    r = brain._wrap_think("[思考] 我没有删除工具，无法操作。\n[计划] 我会建议主人手动删。", "")
    assert "这件事我做不到" in r.split("</think>", 1)[1]
