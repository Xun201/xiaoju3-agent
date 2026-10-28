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
PERSONA_CATEGORY = "persona_profile"
MAX_FACTS = 5
MAX_PER_DIM = 10          # B/C/D 每维度 cap（FIFO 淘汰最旧）
INJECT_PER_DIM = 5        # 注入时每维取最近 N 条

#: 四维人格维度定义（A/B/C/D）
PERSONA_DIMS = ("tags", "traits", "strategies", "taboos")
_PERSONA_DIM_LABELS = {"tags": "事实标签", "traits": "性格特质",
                       "strategies": "应对策略", "taboos": "绝对雷区"}

#: 与 brain._COMPRESS_FAILED_MARKS 同口径（双脑不可用的降级摘要标记）
FAILED_MARKS = ("由于系统原因", "⚠️")

_EXTRACT_SYSTEM = (
    "你是记忆提取助手。下面是一段即将被压缩归档的对话。提取其中值得长期"
    "记住的关键事实：主人的偏好/计划/约定/重要实体（如\"明天下午要去开会\""
    "\"喜欢吃微辣的\"）。关于主人的必须用第三人称\"主人\"，严禁写\"我\"。"
    "每行一条，格式严格为 KEY=VALUE（KEY 两三个字，VALUE 一句话），最多"
    f"{MAX_FACTS} 条。没有值得记的就只输出：无")

_LINE_RE = re.compile(r"^([\u4e00-\u9fffA-Za-z0-9_]{1,6})=(.+)$")

#: 四维人格提取 prompt（A 事实标签 / B 性格特质 / C 应对策略 / D 绝对雷区）
_PERSONA_EXTRACT_SYSTEM = (
    "你是人格分析助手。下面是一段小橘3号与主人的对话。请从对话中提炼关于"
    "主人的四类深层认知（不是事件复述，是模式总结）：\n"
    'A. tags（事实标签）：主人的属性标签，如"程序员""爱玩明日方舟""喜欢甜食"\n'
    'B. traits（性格特质）：剥离具体事件后主人的性格优缺点/擅长领域，'
    '如"抗压能力偏弱""执行力强"\n'
    'C. strategies（应对策略）：小橘面对主人时的最佳反应策略，'
    '如"遇到Bug先给情绪价值""晚上11点后聊轻松话题"\n'
    'D. taboos（绝对雷区）：主人明确讨厌的事物，'
    '如"讨厌长篇大论的说教"\n\n'
    "输出 JSON（只输出 JSON 本体，不要解释）：\n"
    '{"tags":["…"],"traits":["…"],"strategies":["…"],"taboos":["…"]}\n'
    "某类没有就给空数组。最多每类 5 条。")

_PERSONA_JSON_RE = re.compile(r"\{[\s\S]*\}")


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
        n = persist_facts(facts, base_dir=base_dir)
        # 四维人格沉淀（同一批旧消息，独立提取+落库）
        try:
            extract_and_persist_persona(old_messages, base_dir=base_dir,
                                        chat_fn=chat_fn)
        except Exception:
            pass
        return n
    except Exception as e:
        print(f"⚠️ [summary_facts] 事实提取/落库失败（静默）: {e}")
        return 0


# ==================== 四维人格沉淀库（A/B/C/D） ====================

def extract_persona(old_messages, chat_fn=None):
    """从被压缩旧段提取四维人格认知，返回 {"tags":[], "traits":[], …}。
    失败/空 → 各维空列表。"""
    lines = []
    for m in old_messages or []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            content = str(m.get("content", "")).strip()
            if content:
                lines.append(f"{m['role']}: {content[:200]}")
    if not lines:
        return {d: [] for d in PERSONA_DIMS}
    text = "\n".join(lines)[:2500]
    prompt = [{"role": "system", "content": _PERSONA_EXTRACT_SYSTEM},
              {"role": "user", "content": text}]
    try:
        out = str((chat_fn or _default_chat)(prompt) or "")
    except Exception:
        return {d: [] for d in PERSONA_DIMS}
    if "<think>" in out:
        out = out.split("</think>", 1)[-1]
    m = _PERSONA_JSON_RE.search(out)
    if not m:
        return {d: [] for d in PERSONA_DIMS}
    try:
        import json as _json
        raw = _json.loads(m.group(0))
        return {d: [str(x).strip() for x in raw.get(d, []) if str(x).strip()]
                for d in PERSONA_DIMS}
    except Exception:
        return {d: [] for d in PERSONA_DIMS}


def persist_persona(profile, base_dir=None):
    """写入 long_term.db（category=persona_profile）。B/C/D 累积追加
    （内容去重+cap FIFO），A tags 按 key 前缀覆写。返回实写条数。"""
    if not profile:
        return 0
    sm = _sm(base_dir)
    written = 0
    for dim in PERSONA_DIMS:
        entries = profile.get(dim, [])
        if not entries:
            continue
        if dim == "tags":
            # A tags：按 key 前缀覆写（同 key 新值赢，inject 端 reversed 读=最新优先）
            for entry in entries[-MAX_PER_DIM:]:
                sm.save_memory(PERSONA_CATEGORY, f"[{dim}] {entry}")
                written += 1
        else:
            # B/C/D：累积追加（内容去重+cap FIFO）
            existing = []
            try:
                existing = [c for _, c in sm.get_recent_memories(50)
                            if c.startswith(f"[{dim}] ")]
            except Exception:
                pass
            for entry in entries:
                content = f"[{dim}] {entry}"
                if content in existing:
                    continue
                sm.save_memory(PERSONA_CATEGORY, content)
                existing.append(content)
                written += 1
                if len(existing) >= MAX_PER_DIM:
                    break
    return written


def extract_and_persist_persona(old_messages, base_dir=None, chat_fn=None):
    """一步到位：提取+落库。返回实写条数。"""
    profile = extract_persona(old_messages, chat_fn=chat_fn)
    return persist_persona(profile, base_dir=base_dir)


def read_persona_for_injection(base_dir=None, per_dim=INJECT_PER_DIM):
    """读取 persona_profile 并组装为注入文本（每维度最近 N 条）。
    返回 None=库空/异常（调用方跳过注入）。"""
    try:
        sm = _sm(base_dir)
        recent = sm.get_recent_memories(100)
    except Exception:
        return None
    by_dim = {d: [] for d in PERSONA_DIMS}
    for cat, content in reversed(recent):   # reversed=最新在前
        if cat != PERSONA_CATEGORY:
            continue
        for dim in PERSONA_DIMS:
            if content.startswith(f"[{dim}] "):
                val = content[len(f"[{dim}] "):]
                if val not in by_dim[dim]:
                    by_dim[dim].append(val)
                break
    blocks = []
    labels = {"tags": "事实标签", "traits": "性格特质",
              "strategies": "应对策略", "taboos": "绝对雷区"}
    sections = [
        ("你深知主人的特质", by_dim["tags"] + by_dim["traits"]),
        ("针对主人的状态，你的最佳策略", by_dim["strategies"]),
        ("请绝对避开以下雷区", by_dim["taboos"]),
    ]
    for header, items in sections:
        items = items[-per_dim:]
        if items:
            blocks.append(f"{header}：{'；'.join(items)}。")
    if not blocks:
        return None
    return "【你对她本能的认知】\n" + "\n".join(blocks)


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
    # 四维人格验证
    def persona_chat(prompt):
        return ('{"tags":["程序员","爱玩明日方舟"],'
                '"traits":["抗压能力偏弱","执行力强"],'
                '"strategies":["遇到Bug先给情绪价值"],'
                '"taboos":["讨厌长篇大论的说教"]}')
    profile = extract_persona(msgs, chat_fn=persona_chat)
    assert "程序员" in profile["tags"], profile
    assert "抗压能力偏弱" in profile["traits"], profile
    assert "遇到Bug先给情绪价值" in profile["strategies"], profile
    assert "讨厌长篇大论的说教" in profile["taboos"], profile
    # 空安全
    assert extract_persona(msgs, chat_fn=lambda p: "{}") ==         {d: [] for d in ("tags", "traits", "strategies", "taboos")}
    # 注入文本
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            extract_and_persist_persona(msgs, base_dir=td, chat_fn=persona_chat)
            inject = read_persona_for_injection(base_dir=td)
    assert inject is not None and "本能的认知" in inject, inject
    assert "抗压能力偏弱" in inject
    assert "算秃" not in inject  # sanity
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
