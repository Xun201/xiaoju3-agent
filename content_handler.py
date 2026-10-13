# -*- coding: utf-8 -*-
"""内容/比赛领域 handler（#227 批 0 首领域：待办族，2026-10-13）。

v2 领域拆分版（design_227b_boundary_v2.md；v1 单 handler 思路已证伪
删除——10+ 回调注入=一次大爆炸）。本批只抽**分派层**样板：待办族分派
点最干净（一行调用+签名整齐），handle_todo_command 本体仍在 main
（本体搬家=后续批，须逐块黄金 diff）。

领域路线图（v2 §二，后续批逐个填入本文件）：
- ✅ todo：/todo_from_link + /todos 全族（本批）
- ⬜ send_image：/send_image（Lv.4 门+workspace 校验）
- ⬜ soul：/soul_export /soul_import

接口纪律：每 handler ≤4 参数+领域回调由调用方注入；本模块零 import
main（dashboard/多终端可直接复用）。
"""


def handle_todo(raw_message, message, user_id, group_id, todo_cb,
                steps=None):
    """待办指令族领域入口（/todo_from_link 与 /todos 共享分发）。

    todo_cb=main.handle_todo_command（门禁与逻辑本体，QQ 与控制台两路
    共用）；返回回复文本，非待办指令返回 None（调用方继续消息管线）。
    """
    return todo_cb(raw_message, message, user_id, group_id, steps=steps)
