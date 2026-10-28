# -*- coding: utf-8 -*-
"""小橘3号 · 上下文管理（§4）：Token 预算门 + 前情提要递归压缩器。

2026-10-28 原型上车（队长拍板）：
- 触发判定从"按条数 >20"升级为 **Token 预算门**（估算超窗口 70% 才压；
  另留条数硬帽当保险丝，防估算失明）——条数触发退役；
- 压缩升级为**递归摘要**：旧【前情提要】与被压消息合并再浓缩（摘要的
  摘要），system 条目始终单份不增殖（秘书会诊同判：递归摘要主干+双阈值
  +RAG 兜底，ai_consult_log 留痕）；
- 原型与设计报告：_dev/context_manager_prototype.py、
  _dev/design_context_multitable.md。

对 brain 的依赖用函数内延迟导入，避免循环依赖与测试耦合。
"""
import os
import re

#: 【前情提要】system 条目识别锚（与 brain._SUMMARY_PREFIX / main 落盘口径一致）
SUMMARY_ANCHOR = "【前情提要】"

#: 双脑不可用降级摘要标记（与 brain._COMPRESS_FAILED_MARKS 同口径）
FAILED_MARKS = ("由于系统原因", "⚠️")

#: Token 预算三参（环境变量可调）：
#: - 本地窗口 4096 = 链上最弱脑（本地小模型 num_ctx）的安全口径
#: - 云端窗口 32000 = deepseek-chat 64k 预留 50% 余量（秘书会诊：4096 对
#:   纯云端过保守→长对话频繁压缩致"记忆断片"，2026-10-28 二轮上车）
WINDOW_ENV = "XIAOJU3_CONTEXT_WINDOW_TOKENS"
WINDOW_CLOUD_ENV = "XIAOJU3_CONTEXT_WINDOW_CLOUD"
RATIO_ENV = "XIAOJU3_CONTEXT_BUDGET_RATIO"
HARD_CAP_ENV = "XIAOJU3_CONTEXT_HARD_MSG_CAP"
DEFAULT_WINDOW = 4096
DEFAULT_WINDOW_CLOUD = 32000
DEFAULT_RATIO = 0.70
DEFAULT_HARD_CAP = 120      # 保险丝：估算再失明，120 条也必压

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def context_window_tokens(engine=None):
    """按服务引擎取窗口：cloud=32000（DeepSeek 64k 预留余量）/ local=4096
    （最弱脑安全口径）/ None=未知引擎保守按本地。"""
    if engine == "cloud":
        return _env_int(WINDOW_CLOUD_ENV, DEFAULT_WINDOW_CLOUD)
    return _env_int(WINDOW_ENV, DEFAULT_WINDOW)


def budget_ratio():
    return _env_float(RATIO_ENV, DEFAULT_RATIO)


def hard_msg_cap():
    return _env_int(HARD_CAP_ENV, DEFAULT_HARD_CAP)


def estimate_tokens(messages):
    """启发式 Token 估算：CJK≈1 token/字，其余≈0.3 token/字符，每条
    消息 +4 开销。零分词器依赖，宁高勿低；偏差由 30% 余量兜住。"""
    total = 0
    for m in messages or []:
        content = str((m or {}).get("content", "")) if isinstance(m, dict) else str(m or "")
        cjk = len(_CJK_RE.findall(content))
        other = len(content) - cjk
        total += cjk + int(other * 0.3) + 4
    return total


def over_token_budget(messages, engine=None, threshold=None):
    """Token 预算门：估算水位 ≥ 阈值（缺省 70%）→ 需要压缩。engine 决定
    窗口口径（cloud=32000 / local|None=4096）。"""
    window = (context_window_tokens("cloud") if engine == "cloud"
              else context_window_tokens())
    ratio = budget_ratio() if threshold is None else threshold
    if window <= 0:
        return False
    return estimate_tokens(messages) / window >= ratio


def should_compress(messages, engine=None):
    """压缩触发总判定（调用方唯一入口）：Token 预算超 **或** 条数硬帽。
    engine：本轮服务引擎（"cloud"/"local"/None）——动态窗口口径。"""
    if over_token_budget(messages, engine=engine):
        return True
    return len(messages or []) > hard_msg_cap()


def compress_context(messages, max_messages=20, keep_recent=10,
                     summary_chars=100):
    """前情提要递归压缩器。

    触发判定已上移至 should_compress（Token 预算门）——本函数专注执行
    压缩；max_messages 仅作兼容保留的下限保护（调用方传 0 = 无条件压）。

    递归语义：被压旧段若以旧【前情提要】system 条目开头，旧摘要并入本次
    浓缩输入（摘要的摘要），输出仍为单份【前情提要】条目。降级链不变：
    本地脑优先 → 云端 → 失败标记摘要（调用方按标记回退截断）。
    """
    if len(messages) <= max_messages:
        return messages

    print(f"🧠 上下文超预算（{len(messages)} 条 / "
          f"约 {estimate_tokens(messages)} tokens），触发递归压缩...")

    # 头部归位：[0] 是真 system 则保留；[0] 若是前情提要条目（落盘侧剥
    # system 后重载的历史形态）则直接并入折叠——防它被当头部永不折叠
    system_prompt = None
    head = list(messages)
    if head and isinstance(head[0], dict) and head[0].get("role") == "system" \
            and not str(head[0].get("content", "")).startswith(SUMMARY_ANCHOR):
        system_prompt = head.pop(0)

    recent_messages = head[-keep_recent:]
    old_messages = head[:-keep_recent]
    if not old_messages:
        return messages

    # 递归折叠：旧前情提要条目摘出并入输入，条目不增殖
    old_summary = ""
    if (old_messages and isinstance(old_messages[0], dict)
            and old_messages[0].get("role") == "system"
            and str(old_messages[0].get("content", "")).startswith(SUMMARY_ANCHOR)):
        old_summary = str(old_messages[0]["content"]).replace(
            SUMMARY_ANCHOR + "：", "").strip()
        old_messages = old_messages[1:]
        if not old_messages:
            return messages

    old_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_messages])
    if old_summary:
        user_content = (f"旧前情提要：{old_summary}\n以下是之后的新增对话：\n"
                        f"{old_text}\n请把旧提要与新增对话合并，浓缩成一段"
                        f"{summary_chars}字以内的前情提要（旧提要里的关键事实"
                        f"不能丢）。")
    else:
        user_content = old_text

    summary_prompt = [
        {"role": "system",
         "content": ("你是一个记忆压缩助手。请把下面的对话内容浓缩成一段"
                     f"{summary_chars}字以内的前情提要，保留关键事实、任务"
                     "目标和重要细节，不要遗漏核心信息。")},
        {"role": "user", "content": user_content}]

    try:
        from brain import ask_local, ask_cloud
        try:
            summary = ask_local(summary_prompt)
        except Exception:
            summary = ask_cloud(summary_prompt)
    except Exception as e:
        print(f"⚠️ 摘要生成失败，直接截断旧记忆: {e}")
        summary = "（由于系统原因，早期对话记忆已丢失）"

    # RAG 兜底第三层（2026-10-28 上车）：仅在双脑**成功**路径沉淀事实——
    # 降级摘要本身不可靠，防污染记忆库；提取/落库失败静默，绝不拖垮主链
    if not any(mark in str(summary) for mark in FAILED_MARKS):
        try:
            from plugins.summary_facts import on_compress as _facts_on
            _facts_on(old_messages)
        except Exception:
            pass

    print(f"✅ 记忆压缩完成！摘要：{summary[:50]}...")

    compressed_messages = ([system_prompt] if system_prompt else [])
    compressed_messages.append({
        "role": "system",
        "content": f"{SUMMARY_ANCHOR}：{summary}"})
    compressed_messages.extend(recent_messages)

    return compressed_messages
