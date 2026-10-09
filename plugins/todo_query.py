# -*- coding: utf-8 -*-
"""待办查询意图处理器（intent_router「todo_query」→ 本模块 list_reply）。

直查共享待办库返回格式化 pending 清单，零模型参与——本地小模型对
「查待办」会幻觉工具名并直出原始 JSON（10-08 晚实锤
{"action":"get_todo_list"}，该名全仓零命中=纯编造；格式迁移幻觉=
control_ha_device 正例的内层参数键 "action" 被升格为顶层键），意图
直达绕开模型不可靠边界。只读：本处理器不做任何增删改。

⚠️ 动态引用插件：本模块经 intent_router 字符串引用（importlib），必须
同步列 xiaoju3.spec hiddenimports（AGENTS.md 开发纪律，冻结包铁律）。
"""
from agent_state.state_manager import state_manager


def list_reply(**_):
    """返回 pending 待办格式化清单（生效档标注，最多 15 条防刷屏）。"""
    rows = state_manager.get_todos(status="pending", limit=16) or []
    if not rows:
        return "✅ 当前没有待办，清清爽爽～"
    shown = rows[:15]
    lines = [
        f"{i}. [{r.get('effective_priority') or r.get('priority') or '?'}] "
        f"#{r.get('id')} {str(r.get('content') or '').strip()}"
        for i, r in enumerate(shown, 1)]
    tail = ("\n（还有更多——发 /todos 或看控制台待办面板）"
            if len(rows) > 15 else "")
    return f"📋 当前待办（前 {len(shown)} 条）：\n" + "\n".join(lines) + tail
