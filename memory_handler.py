# -*- coding: utf-8 -*-
"""记忆领域 handler（#227 批 B：remember/gen_log/clear，分步落地）。

v2 领域拆分版（design_227b_boundary_v2.md §二 handler 2；批 B 方案
design_227c_batch_b_memory.md）。三处 inline 分批迁入：
- ✅ B-1 handle_remember：记住xxx 正则匹配（打标+落库本体留 main 回调）
- B-2 gen_log：日志提取（线程随迁；_arg_after 借 permission_handler）
- B-3 handle_clear：清空记忆四变体（全局 messages 不出 main 红线——
  本体 handle_clear_command 留 main）

接口纪律：每入口 ≤4 参数+回调注入；本模块零 import main。
"""

import re

# 记住xxx 触发正则（main 原块逐字节随迁；B-1）
REMEMBER_RE = re.compile(r"(?:帮我|请|麻烦|你)*记住[:：,，、]?\s*(.+)")


def handle_remember(raw_message, strip_cq_cb, remember_cb):
    """长期记忆"记住"触发词（架构 §10 #3，B-1）。

    strip_cq_cb=main._strip_cq；remember_cb(content)->确认/失败文案
    （打标 _memory_emotion_meta+state_manager.save_memory 留 main）。
    未命中或内容为空返回 None（调用方继续管线——原语义：空内容不回复
    直落下一段）。
    """
    match = REMEMBER_RE.search(strip_cq_cb(raw_message))
    if not match:
        return None
    content = match.group(1).strip()
    if not content:
        return None
    return remember_cb(content)
