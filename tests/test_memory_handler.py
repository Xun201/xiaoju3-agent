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


# B-2 ==================== gen_log ====================

# 7 非本域 → None
def test_gen_log_non_domain_returns_none():
    assert memory_handler.gen_log(
        "今天天气如何", "今天天气如何",
        level_value_cb=lambda: 4) is None


# 8 Lv.3 门：低级只引导不执行
def test_gen_log_gate_denies_low_level():
    reply = memory_handler.gen_log(
        "/gen_log https://chat.deepseek.com/share/abc",
        "/gen_log https://chat.deepseek.com/share/abc",
        level_value_cb=lambda: 1)
    assert "权限不足" in reply and "Lv.3" in reply


# 9 坏链接：前缀校验拒绝
def test_gen_log_bad_link_rejected():
    reply = memory_handler.gen_log(
        "/gen_log https://evil.example.com/x",
        "/gen_log https://evil.example.com/x",
        level_value_cb=lambda: 3)
    assert "请提供正确的 DeepSeek 分享链接" in reply


# 10 受理路径：daemon 线程被创建（Thread 打桩不真跑网络）
def test_gen_log_accept_starts_daemon_thread(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            started["target"], started["args"], started["daemon"] = \
                target, args, daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr(memory_handler.threading, "Thread", FakeThread)
    reply = memory_handler.gen_log(
        "/gen_log https://chat.deepseek.com/share/abc",
        "/gen_log https://chat.deepseek.com/share/abc",
        level_value_cb=lambda: 3)
    assert reply.startswith("🔄")
    assert started["daemon"] is True and started["started"] is True
    assert started["args"] == ("https://chat.deepseek.com/share/abc",)


# B-3 ==================== handle_clear ====================

# 11 四变体全等命中：cb 收 source、回复逐字节
def test_clear_variants_route_to_cb():
    seen = []
    for cmd, src in (("/clear", "web"), ("/reset", "qq"),
                     ("清空记忆", "web"), ("重置记忆", "qq")):
        reply = memory_handler.handle_clear(
            cmd, src, clear_cb=lambda s: seen.append(s))
        assert reply == "✨ 记忆已清空！我现在的大脑非常干净，可以重新开始对话了。"
    assert seen == ["web", "qq", "web", "qq"]


# 12 非变体不误吞：/reset_fuse 与含字样普通对话均返回 None
def test_clear_does_not_swallow_reset_fuse():
    called = []
    assert memory_handler.handle_clear(
        "/reset_fuse", "qq", clear_cb=lambda s: called.append(s)) is None
    assert memory_handler.handle_clear(
        "帮我清空记忆吧", "qq", clear_cb=lambda s: called.append(s)) is None
    assert called == []
