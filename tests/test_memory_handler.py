# -*- coding: utf-8 -*-
"""memory_handler 单元锚（#227 批 B，分步扩充）。

黄金样本（39 条 tests/data）管端到端等价，本文件管分支组合与回调契约。
"""
import memory_handler


# B-1 ==================== handle_remember ====================

# 1 命中：剥 CQ 后正则提取，cb 收纯净内容、回复透传
def test_remember_match_passes_content():
    got = {}
    reply = memory_handler.handle_remember(
        "记住我爱吃火锅", strip_cq_cb=lambda t: t,
        remember_cb=lambda c: (got.update({"c": c}), f"好的，我记住了：{c}")[1])
    assert reply == "好的，我记住了：我爱吃火锅"
    assert got["c"] == "我爱吃火锅"


# 2 前缀变体：帮我/请/麻烦/你 + 标点均可
def test_remember_prefix_variants():
    for raw in ("帮我记住：带娃吃饭", "请记住 带伞", "你记住，明天开会"):
        got = {}
        memory_handler.handle_remember(
            raw, strip_cq_cb=lambda t: t,
            remember_cb=lambda c: got.update({"c": c}) or "ok")
        assert got["c"], raw


# 3 未命中 → None 且 cb 不被调
def test_remember_no_match_returns_none():
    called = []
    reply = memory_handler.handle_remember(
        "今天天气如何", strip_cq_cb=lambda t: t,
        remember_cb=lambda c: called.append(c))
    assert reply is None and called == []


# 4 strip_cq_cb 真被使用（CQ 码由调用方剥离后正则才命中）
def test_remember_uses_strip_cb():
    got = {}
    memory_handler.handle_remember(
        "[CQ:at,qq=10000]记住小橘的生日", strip_cq_cb=lambda t: t.replace("[CQ:at,qq=10000]", ""),
        remember_cb=lambda c: got.update({"c": c}) or "ok")
    assert got["c"] == "小橘的生日"


# 5 纯空白内容 → 无匹配返回 None（原语义：不回复直落管线；
#   注意单标点"，"按原代码属合法内容会入库——语义逐字节保持）
def test_remember_whitespace_only_returns_none():
    called = []
    reply = memory_handler.handle_remember(
        "记住   ", strip_cq_cb=lambda t: t,
        remember_cb=lambda c: called.append(c))
    assert reply is None and called == []
