# -*- coding: utf-8 -*-
"""plugins/todo_text · 纯文字记待办（#261，2026-10-07 三拍板）。

"帮我记待办：1.xxx 2.xxx" 等自然语言直达入库：意图路由规则层命中
（intent_router INTENT_PATTERNS todo_text_add 表项）→ 本模块 add_from_message
受理即回 → 后台线程走提炼链判级入库（todo_extractor.extract_todos_from_text_sync，
判级复用 PRIORITY_CRITERIA 同源 prompt，编号/换行/顿号等格式由模型解析）。

拍板口径：走向=意图路由新表项 / 门禁=Lv.2 / 判级=走云端。
门禁拒绝文案用 ⚠️ 前缀（**非 ❌**）——handle_intent_command 对 dispatch 返回
的 ❌ 一律返回 None 落回 brain（消息被模型重新解释=旧病复发），⚠️ 才会作为
⚙️ 指令回复直接送出；与链接链（handle_todo_command 返回 ❌）存在刻意口径差，
锚 tests/test_todo_text.py::test_gate_lv1_rejects_with_warning_prefix 写明。
完成感知：意图路径不带发起者通道上下文（route 只抽消息文本），无 QQ 主动
推送——完成后经控制台待办面板轮询 / `/todos` 查看自然浮现，与 extract_todos
工具路径同口径。
"""
import threading

import main   # permission_manager 单例宿主（dispatch 运行期 import，无循环）
from plugins import todo_extractor
from xiaoju3 import CLOUD_KEY, CLOUD_URL

# DeepSeek 分享链接标记：含链接的"记待办"应走链接提取链（预分流/工具）
_SHARE_MARKER = "chat.deepseek.com/share/"


def add_from_message(text=""):
    """意图路由处理器：受理即回（后台线程判级入库），返回面向用户文案。

    - 门禁 Lv.2（对齐链接链拍板①）：拒绝用 ⚠️ 前缀（见模块 docstring）；
    - 含 DeepSeek 分享链接 → 引导走链接链（纯文字入口不处理链接）；
    - 空内容 → 用法示例。
    """
    text = str(text or "").strip()
    if main.permission_manager.level_value() < 2:
        return ("⚠️ 记待办需要 Lv.2（普通用户）权限。"
                "请先 /register <密码> 注册升级。")
    if _SHARE_MARKER in text:
        return ("⚠️ 检测到 DeepSeek 分享链接——链接提取请直接发链接"
                "或用 /todo_from_link <链接>，纯文字入口不处理链接。")
    if not text:
        return "⚠️ 请把要记的事写出来，例如：帮我记待办：1.周三交周报"
    threading.Thread(target=_run_job, args=(text,), daemon=True).start()
    return ("🔄 已受理！正在按时间尺度判级并入库（约半分钟），"
            "完成后出现在控制台待办面板，随时可发 /todos 查看。")


def _run_job(text):
    """后台线程体：判级入库，结果只进库与 _LAST_JOB（与链接链同语义）。"""
    try:
        result = todo_extractor.extract_todos_from_text_sync(
            text, CLOUD_KEY, CLOUD_URL, notify=None)
        print(f"✅ [纯文字待办] 完成: 新增 {result.get('inserted', 0)} 条"
              f"（跳过 {result.get('skipped', 0)}）")
    except Exception as e:
        print(f"⚠️ [纯文字待办] 后台报错: {e}")
