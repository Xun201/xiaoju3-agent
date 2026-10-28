# -*- coding: utf-8 -*-
"""摘要事实沉淀（RAG 兜底第三层，2026-10-28 上车）：compress_context 摘要
**成功**后，从被压旧段提取关键事实（主人偏好/计划/约定，第三人称
KEY=VALUE ≤5 条，双脑降级链），去重写入 long_term.db 的 summary_facts
类——被压缩掉的细节可被 recall/Hindsight 检索找回。

设计=设计报告 §三（_dev/design_context_multitable.md）；原型
_dev/summary_to_memory.py 已毕业入本模块（薄壳留存）。

铁律：
- 只在双脑成功路径提取（降级摘要"由于系统原因"本身不可靠，防污染记忆库）
- 任何失败静默返回 0——RAG 兜底绝不拖垮压缩主链
- 开关 XIAOJU3_SUMMARY_FACTS_ENABLED（缺省 1=开）；测试态 conftest 哨兵
  置 0 防污染真实库，接线测试显式开 + 临时 base_dir 自管
"""
import os
import re

FACT_CATEGORY = "summary_facts"
MAX_FACTS = 5

#: 与 brain._COMPRESS_FAILED_MARKS 同口径（双脑不可用的降级摘要标记）
FAILED_MARKS = ("由于系统原因", "⚠️")

_EXTRACT_SYSTEM = (
    "你是记忆提取助手。下面是一段即将被压缩归档的对话。提取其中值得长期"
    "记住的关键事实：主人的偏好/计划/约定/重要实体（如\"明天下午要去开会\""
    "\"喜欢吃微辣的\"）。关于主人的必须用第三人称\"主人\"，严禁写\"我\"。"
    "每行一条，格式严格为 KEY=VALUE（KEY 两三个字，VALUE 一句话），最多"
    f"{MAX_FACTS} 条。没有值得记的就只输出：无")

_LINE_RE = re.compile(r"^([\u4e00-\u9fffA-Za-z0-9_]{1,6})=(.+)$")


def enabled():
    return os.environ.get("XIAOJU3_SUMMARY_FACTS_ENABLED", "1") not in \
        ("0", "false", "False", "off")


def _sm(base_dir=None):
    """取状态外置层：缺省生产单例；显式 base_dir=隔离实例（测试）。"""
    if base_dir is not None:
        from agent_state.state_manager import StateManager
        return StateManager(base_dir=base_dir)
    from agent_state.state_manager import state_manager
    return state_manager


def _default_chat(prompt):
    """双脑降级链：本地优先，失败转云端（与 compress_context 同款）。"""
    from brain import ask_local, ask_cloud
    try:
        return ask_local(prompt)
    except Exception:
        return ask_cloud(prompt)


def extract_facts(old_messages, chat_fn=None):
    """从被压缩的旧消息段提取关键事实，返回 [(key, value)]。

    只认 user/assistant 行（system 前情提要条目自然跳过）；异常/空/"无"
    一律返回 []——提取失败绝不产生垃圾记忆。"""
    lines = []
    for m in old_messages or []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            content = str(m.get("content", "")).strip()
            if content:
                lines.append(f"{m['role']}: {content[:200]}")
    if not lines:
        return []
    text = "\n".join(lines)[:2000]
    prompt = [{"role": "system", "content": _EXTRACT_SYSTEM},
              {"role": "user", "content": text}]
    try:
        out = str((chat_fn or _default_chat)(prompt) or "")
    except Exception:
        return []
    if "<think>" in out:
        out = out.split("</think>", 1)[-1]
    facts = []
    for line in out.strip().splitlines():
        line = line.strip().lstrip("-• ")
        if not line or line == "无":
            continue
        m = _LINE_RE.match(line)
        if m:
            facts.append((m.group(1), m.group(2).strip()))
        if len(facts) >= MAX_FACTS:
            break
    return facts


def persist_facts(facts, base_dir=None, dedupe=True):
    """写入 long_term.db（category=summary_facts）。dedupe=与最近 50 条
    精确比对去重。返回实写条数。"""
    if not facts:
        return 0
    sm = _sm(base_dir)
    if dedupe:
        try:
            seen = {str(c).strip() for _, c in sm.get_recent_memories(50)}
        except Exception:
            seen = set()
    else:
        seen = set()
    written = 0
    for key, value in facts:
        content = f"{key}={value}"
        if content in seen:
            continue
        sm.save_memory(FACT_CATEGORY, content)
        written += 1
    return written


def on_compress(old_messages, base_dir=None, chat_fn=None):
    """compress_context 摘要成功后的沉淀入口：提取+落库，任何失败静默
    （RAG 兜底绝不拖垮压缩主链）。返回实写条数。"""
    if not enabled():
        return 0
    try:
        facts = extract_facts(old_messages, chat_fn=chat_fn)
        return persist_facts(facts, base_dir=base_dir)
    except Exception as e:
        print(f"⚠️ [summary_facts] 事实提取/落库失败（静默）: {e}")
        return 0


def selftest():
    """内置自检（临时库，绝不碰真实 long_term.db）。"""
    import contextlib
    import io
    import tempfile

    def fake_chat(prompt):
        return ("主人偏好=主人喜欢吃微辣的东西\n"
                "主人计划=明天下午要去开会\n"
                "垃圾行没有等号\n")

    msgs = [{"role": "user", "content": "我明天下午要去开会，晚饭想吃微辣的"},
            {"role": "assistant", "content": "好嘞，帮主人记住了"}]
    facts = extract_facts(msgs, chat_fn=fake_chat)
    assert ("主人计划", "明天下午要去开会") in facts, facts
    assert ("主人偏好", "主人喜欢吃微辣的东西") in facts, facts
    assert extract_facts(msgs, chat_fn=lambda p: "无") == []
    def boom(_):
        raise RuntimeError("双脑全挂")
    assert extract_facts(msgs, chat_fn=boom) == []
    assert extract_facts([], chat_fn=fake_chat) == []
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            assert persist_facts(facts, base_dir=td) == 2
            assert persist_facts(facts, base_dir=td) == 0   # 全重复
    # on_compress 用全新目录（去重是正确行为，同库重放必 0——上面已验）
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            assert on_compress(msgs, base_dir=td, chat_fn=fake_chat) == 2
            assert on_compress(msgs, base_dir=td, chat_fn=fake_chat) == 0
            assert on_compress(msgs, base_dir=td, chat_fn=boom) == 0
    # 开关门
    with _gate_off_cm():
        assert on_compress(msgs, base_dir="x:", chat_fn=fake_chat) == 0
    print("SUMMARY_FACTS_SELFTEST_OK")


def _gate_off_cm():
    """测试用：临时关闸（还原原值）。"""
    import contextlib
    import os

    @contextlib.contextmanager
    def cm():
        old = os.environ.get("XIAOJU3_SUMMARY_FACTS_ENABLED")
        os.environ["XIAOJU3_SUMMARY_FACTS_ENABLED"] = "0"
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("XIAOJU3_SUMMARY_FACTS_ENABLED", None)
            else:
                os.environ["XIAOJU3_SUMMARY_FACTS_ENABLED"] = old
    return cm()


if __name__ == "__main__":
    selftest()
