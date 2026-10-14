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
import threading

from permission_handler import _arg_after   # DB1 拍板：同包私有复用（非 main）

# 记住xxx 触发正则（main 原块逐字节随迁；B-1）
REMEMBER_RE = re.compile(r"(?:帮我|请|麻烦|你)*记住[:：,，、]?\s*(.+)")

# /gen_log 分享链接前缀（main SHARE_PREFIX 同值随迁；DB4 注入带缺省）
DEFAULT_SHARE_PREFIX = "https://chat.deepseek.com/share/"


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


def gen_log(message, raw_message, level_value_cb,
            share_prefix=DEFAULT_SHARE_PREFIX):
    """全自动日志提取（§7，B-2）：Lv.3 门→链接前缀校验→后台 daemon
    线程（闭包惰性 import run_link_log——语义与 main 原块一致）→受理
    文案。'/gen_log' in message 命中（原语义，非 startswith）；非本域
    返回 None。受理路径需 Lv.3 用户态，黄金采不了（DB5）→真机验证项。
    """
    if "/gen_log" not in message:
        return None
    if level_value_cb() < 3:
        return ("❌ 权限不足，开发日志提取需要 Lv.3（代码编写者）权限。\n"
                "请先发送 /coder_auth <6位动态密码> 升级后再试。")
    # 从清洗前原文提取链接：标点清洗会剥掉 URL 里的 : . 等字符，导致前缀校验失效
    log_url = _arg_after(raw_message, "/gen_log")

    if not log_url.startswith(share_prefix):
        return "⚠️ 请提供正确的 DeepSeek 分享链接，格式：/gen_log https://chat.deepseek.com/share/..."

    def run_log_extraction(target_url):
        print(f"🚀 收到指令，开始后台提取链接: {target_url}")
        try:
            import run_link_log
            run_link_log.run_link_log(target_url)
        except Exception as e:
            print(f"⚠️ 提取任务后台报错: {e}")

    threading.Thread(target=run_log_extraction, args=(log_url,),
                     daemon=True).start()
    return "🔄 收到链接啦！小橘3号正在后台努力阅读和总结（大约需要1分钟）。完成后日志会自动保存到 dev_logs 文件夹里！"
