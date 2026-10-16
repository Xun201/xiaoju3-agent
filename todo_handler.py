"""待办指令族 handler（#227 批 C.3：todo 本体迁入，2026-10-16）。

数据域标注（#227 批 0 七领域口径）：
- todos.db：灵魂核 **ext**（可镜像但跟人走）——待办=用户轨迹；
- 链接查重 recent_urls（plugins.todo_extractor 内存层）：运行时缓存，非灵魂；
- ONEBOT 完成通知：QQ 通道发送，配置单一来源=xiaoju3.py（CLOUD_KEY/CLOUD_URL/
  ONEBOT_API_URL/ONEBOT_TOKEN 模块级直引——xiaoju3 为纯配置模块无 import 环，
  2026-10-16 grep 验证）。

依赖方向：零 import main（#227 纪律续，test 锚锁行首形态）；
_arg_after 借 permission_handler（memory_handler:17 同包复用先例，防第三副本）；
SHARE_PREFIX 单一来源在本模块（原 main.py:93 随迁；与 run_link_log.SHARE_PREFIX /
plugins.link_logger 一致——三处一致性声明随迁）。
"""
import re
import threading

import requests

from permission import permission_manager
from permission_handler import _arg_after
from plugins.todo_extractor import (check_recent_url, clear_recent_urls,
                                    extract_todos_from_url_sync, mark_url)

# main.py:81 同款别名（本体函数体逐字节迁移的伴生行）
_extract_work_thread = threading.Thread
# main.py:82 同款看门狗常量（随迁）
TODO_EXTRACT_WATCHDOG_S = 180
# main.py:93 随迁（唯一消费者=本模块 handle_todo_command；三处一致性声明见模块头）
SHARE_PREFIX = "https://chat.deepseek.com/share/"
# xiaoju3.py 配置单一来源（无环验证见模块头）
from xiaoju3 import CLOUD_KEY, CLOUD_URL, ONEBOT_API_URL, ONEBOT_TOKEN

# main.py:114 同款 Bearer 头（正档在 main；不抽公共模块——1 行不值得开新文件）
def _onebot_headers():
    """OneBot API 请求头（Bearer 认证；未配置令牌时与参考口径一致传空）。"""
    return {"Authorization": f"Bearer {ONEBOT_TOKEN}"}


from agent_state.state_manager import state_manager


def _notify_todo_done(chat_target):
    """构造待办提取完成回调（docs/TODO_EXTRACT_DESIGN.md §6）。

    chat_target：{"group_id": X} / {"user_id": Y} / 其他（终端路径）→ 仅打印。
    ONEBOT send_group_msg / send_private_msg 为 main.py 既有调用模式；
    通知失败仅打日志，绝不影响提取结果（已入库）。
    """
    def _notify(result):
        if result.get("ok"):
            if result.get("empty_page"):
                # #262（2026-10-07）：失效链接提示页（<EMPTY_PAGE_MIN_CHARS，
                # extractor 跳过提炼直接标记）不再伪装"没发现待办"——明确
                # 告知失效可重新分享；正常 0 条文案保持不变（防互串）。
                body = ("⚠️ 这条链接已失效或内容为空，请检查或重新分享"
                        "（DeepSeek 分享链接几小时后会过期）。")
            else:
                items = result.get("items") or []
                if not items:
                    body = "✅ 链接读完了，这段对话里没有发现待办事项。"
                else:
                    def _fmt_preview(i_item):
                        i, it = i_item
                        if isinstance(it, dict):
                            return f"{i + 1}. [{it.get('priority', 'P1')}] {it.get('content', '')}"
                        return f"{i + 1}. {it}"   # 兼容 str 条目（防御形态）
                    preview = "\n".join(map(_fmt_preview, enumerate(items[:5])))
                    body = (f"✅ 待办提取完成！新增 {result.get('inserted', 0)} 条"
                            f"（跳过重复 {result.get('skipped', 0)} 条）：\n{preview}\n"
                            f"（全部见 /todos 或控制台待办面板）")
        else:
            body = f"❌ 待办提取失败：{result.get('error') or '未知原因'}"
        target = chat_target or {}
        if not target.get("group_id") and not target.get("user_id"):
            print(body)
            return
        try:
            if target.get("group_id"):
                requests.post(f"{ONEBOT_API_URL}/send_group_msg",
                              json={"group_id": target["group_id"], "message": body},
                              timeout=10, headers=_onebot_headers())
            else:
                requests.post(f"{ONEBOT_API_URL}/send_private_msg",
                              json={"user_id": target["user_id"], "message": body},
                              timeout=10, headers=_onebot_headers())
        except Exception as e:
            print(f"⚠️ 待办完成通知发送失败: {e}")
    return _notify


def handle_todo_command(raw_message, message, user_id, group_id, steps=None):
    """待办指令族共享分发（2026-10-04 Bug 1 修复）。

    /todo_from_link 与 /todos 的门禁与逻辑原先内联在 handle_message——
    控制台 /api/chat 直连 smart_ask 绕过该指令链，斜杠指令被模型解释
    （/todos 曾被误映射到 read_core_memory 吃 Lv.4 拒绝）。抽成本模块
    函数后 QQ（handle_message）与控制台（dashboard /api/chat）两条
    路径共用同一份门禁与逻辑，LV1/LV2 门禁自动对两路生效。

    steps: 可选列表出参——调用方传列表则按序收到指令处理步骤（控制台
    过程卡片用，尾巴 3；QQ 链路不传：<think> 包装会在 QQ 回复链路被剥
    除，过程信息对 QQ 无承载 UI）。

    返回回复文本；非待办指令返回 None（调用方继续原链路）。
    """
    steps = steps if steps is not None else []

    if "/todo_from_link" in message:
        steps.append("收到指令 /todo_from_link")
        if permission_manager.level_value() < 2:
            steps.append("门禁拒绝：需要 Lv.2，当前 " + permission_manager.current_level)
            return ("❌ 权限不足，待办提取需要 Lv.2（普通用户）权限。"
                    "请先 /register <密码> 注册升级。")
        steps.append("门禁通过（Lv.2 及以上）")
        # 从清洗前原文提取链接：标点清洗会剥掉 URL 里的 : . 等字符（同 /gen_log 口径）
        todo_url = _arg_after(raw_message, "/todo_from_link")
        if not todo_url.startswith(SHARE_PREFIX):
            steps.append("链接格式校验未通过")
            return "⚠️ 请提供正确的 DeepSeek 分享链接，格式：/todo_from_link https://chat.deepseek.com/share/..."
        steps.append("链接格式校验通过")
        if check_recent_url(todo_url):
            steps.append("24 小时查重：该链接近期已提取过")
            return "⚠️ 这条链接 24 小时内已提取过，发 /todos 查看已有待办。"
        steps.append("24 小时查重通过")
        mark_url(todo_url)   # 受理即登记；失败由 todo_extractor unmark 放行重试

        def run_todo_extraction(target_url):
            print(f"🚀 收到待办提取指令，开始后台处理链接: {target_url}")
            chat_target = {"group_id": group_id} if group_id else {"user_id": user_id}
            notify_done = _notify_todo_done(chat_target)
            try:
                result_holder = {}

                def _inner():
                    result_holder["r"] = extract_todos_from_url_sync(
                        target_url, CLOUD_KEY, CLOUD_URL, notify=notify_done)

                # #260 看门狗：提取整体 deadline（模块常量，测试可注入缩短）
                # ——抓取+提炼任一环卡死（如云端慢滴连接）时强杀并通知用户
                work = _extract_work_thread(target=_inner, daemon=True)
                work.start()
                work.join(timeout=TODO_EXTRACT_WATCHDOG_S)
                if work.is_alive():
                    print(f"❌ [待办提取] 看门狗超时（180s）: {target_url} — 强杀，通知用户")
                    from plugins.todo_extractor import unmark_url
                    try:
                        unmark_url(target_url)   # 放行重试
                    except Exception:
                        pass
                    try:
                        notify_done({"ok": False,
                                     "error": "提取超时（3 分钟看门狗触发），请稍后重发链接"})
                    except Exception as ne:
                        print(f"⚠️ [待办提取] 超时通知失败: {ne}")
                else:
                    # #260 可观测性：成功路径也留痕（此前"提炼 0 条+静默完成"
                    # 在日志上与挂死不可区分，排查成本翻倍）
                    r = result_holder.get("r") or {}
                    print(f"✅ [待办提取] 结束: {target_url} "
                          f"ok={r.get('ok')} 新增 {r.get('inserted', 0)} 条"
                          f"（跳过 {r.get('skipped', 0)}）")
                    if not r.get("ok"):
                        print(f"⚠️ [待办提取] 结果失败且未见通知: {target_url} → 兜底通知")
                        try:
                            notify_done(r or {"ok": False, "error": "提取失败，请重试"})
                        except Exception as ne:
                            print(f"⚠️ [待办提取] 兜底通知失败: {ne}")
            except Exception as e:
                print(f"⚠️ 待办提取后台报错: {e}")
                try:
                    notify_done({"ok": False, "error": f"提取失败: {e}"})
                except Exception:
                    pass

        threading.Thread(target=run_todo_extraction, args=(todo_url,),
                         daemon=True).start()
        steps.append("后台提取线程已启动（约 1 分钟），完成后待办面板自动刷新")
        return ("🔄 收到链接啦！小橘3号正在后台阅读并提炼待办（大约需要 1 分钟）。"
                "完成后会通知你，也可发 /todos 查看。")

    if "/todos" in message:
        steps.append("收到指令 /todos")
        if permission_manager.level_value() < 2:
            steps.append("门禁拒绝：需要 Lv.2，当前 " + permission_manager.current_level)
            return ("❌ 权限不足，待办查询需要 Lv.2（普通用户）权限。"
                    "请先 /register <密码> 注册升级。")
        steps.append("门禁通过（Lv.2 及以上）")
        if "/todos clear" in raw_message:
            # 🗑️ 清空全部待办（2026-10-04）：破坏性操作，Lv.3 门禁 + 无状态
            # 二次确认（首次提示、confirm 才真清，不记忆"待确认"状态）
            if permission_manager.level_value() < 3:
                steps.append("门禁拒绝：清空为破坏性操作，需要 Lv.3，当前 "
                             + permission_manager.current_level)
                return ("❌ 安全拒绝：清空待办是破坏性操作，需要 Lv.3（代码编写者）"
                        "权限。请先 /coder_auth <动态密码> 升级。")
            if "/todos clear confirm" in raw_message:
                deleted = state_manager.clear_todos()
                clear_recent_urls()   # 同步清内存防抖层：清空后同链接可重提
                steps.append(f"已清空 {deleted} 条待办（pending+done）")
                return ("🗑️ 已清空全部待办。"
                        f"24 小时提取查重也已重置，任何链接都可以重新提取。")
            pending_count = len(state_manager.get_todos(status="pending", limit=200))
            done_count = len(state_manager.get_todos(status="done", limit=1000))
            steps.append(f"二次确认提示：将清空 pending {pending_count} 条 + done {done_count} 条")
            return (f"⚠️ 将清空全部待办 {pending_count + done_count} 条"
                    f"（未完成 {pending_count} + 已完成 {done_count}），不可恢复。\n"
                    f"确认请回复：/todos clear confirm")
        if "/todos done" in raw_message:
            done_arg = (_arg_after(raw_message, "/todos done") or "").strip()
            try:
                todo_id = int(done_arg)
            except ValueError:
                steps.append("用法校验未通过")
                return "⚠️ 用法：/todos done <编号>（编号见 /todos 列表，形如 #5）"
            todo = state_manager.complete_todo(todo_id)
            if todo:
                steps.append(f"已标记完成 #{todo['id']}")
                return f"✅ 已完成待办 #{todo['id']}：{todo['content']}"
            steps.append(f"未找到未完成的待办 #{todo_id}")
            return f"⚠️ 没有找到未完成的待办 #{todo_id}。"
        # 尾巴 G（2026-10-04）：清单口径重写——取最近 200 条按优先级 P0→P1→P2
        # 分组、组内 id 倒序（最新在前；旧口径 ASC+limit20 恒显最旧 20 条，
        # 新提取条目永远不可见），截断时明示
        todos = state_manager.get_todos(status="pending", limit=200)
        done_count = len(state_manager.get_todos(status="done", limit=1000))
        steps.append(f"查询待办：未完成 {len(todos)} 条 / 已完成 {done_count} 条")
        if not todos:
            return "📋 暂无待办。发 /todo_from_link <DeepSeek分享链接> 让我帮你记。"
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
        grouped = sorted(
            todos,
            key=lambda t: (order.get(t.get("priority", "P1"), 1), -t["id"]))
        shown = grouped[:20]
        lines = "\n".join(f"#{t['id']} [{t.get('priority', 'P1')}] {t['content']}"
                          for t in shown)
        tail_note = f"\n（仅显最近 20 条，共 {len(todos)} 条未完成）" if len(grouped) > 20 else ""
        return (f"📋 待办清单（未完成 {len(todos)} 条，最新在前）：\n{lines}{tail_note}\n"
                f"（已完成 {done_count} 条 · 回复 /todos done <编号> 标记完成）")

    return None
