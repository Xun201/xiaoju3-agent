# -*- coding: utf-8 -*-
"""内容/比赛领域 handler（#227 批 0：待办族+send_image，2026-10-13）。

v2 领域拆分版（design_227b_boundary_v2.md；v1 单 handler 思路已证伪
删除——10+ 回调注入=一次大爆炸）。分派层逐领域抽取：待办族分派点最
干净（首批样板），send_image 首含实质分派逻辑（Lv.4 门+校验+CQ 拼装）。

领域路线图（v2 §二，后续批逐个填入本文件）：
- ✅ todo：/todo_from_link + /todos 全族（批 0 首批）
- ✅ send_image：/send_image（Lv.4 门+存在性+workspace 校验+CQ 拼装）
- ⬜ soul：/soul_export /soul_import

接口纪律：每 handler ≤4 参数+领域回调由调用方注入；本模块零 import
main（dashboard/多终端可直接复用）。
"""

import os as _os


def handle_todo(raw_message, message, user_id, group_id, todo_cb,
                steps=None):
    """待办指令族领域入口（/todo_from_link 与 /todos 共享分发）。

    todo_cb=main.handle_todo_command（门禁与逻辑本体，QQ 与控制台两路
    共用）；返回回复文本，非待办指令返回 None（调用方继续消息管线）。
    """
    return todo_cb(raw_message, message, user_id, group_id, steps=steps)


def send_image(command_text, raw_message, level_value_cb, is_in_workspace_cb,
               exists_cb=None):
    """/send_image 领域入口（2026-10-02 权限重构：LV4 主人级专属）。

    - level_value_cb/is_in_workspace_cb 由调用方注入（permission_manager
      与 main._is_in_workspace——本模块零 import main）；
    - exists_cb 缺省 os.path.exists（测试可注入）；
    - 返回 CQ 码回复文本，非本领域指令返回 None。
    """
    if not command_text.startswith("/send_image"):
        return None
    exists = exists_cb or _os.path.exists
    if level_value_cb() < 4:
        return ("❌ 权限不足，发图需要 Lv.4（主人级）权限。"
                "请先 /lv4_auth confirm <6位动态密码> 授权。")
    # 从清洗前原文提取路径（清洗会剥掉盘符冒号与扩展名里的点）
    img_path = raw_message.split("/send_image", 1)[-1].strip()
    if not img_path:
        return "❌ 请提供图片路径，格式：/send_image <图片路径>"
    if not exists(img_path):
        return f"❌ 图片不存在：{img_path}"
    if not is_in_workspace_cb(img_path):
        return "❌ 只能发送项目工作区内的图片。"
    # CQ 码发图：随回复链路交回 OneBot 实现端解析发送
    return f"[CQ:image,file=file://{img_path}]"
