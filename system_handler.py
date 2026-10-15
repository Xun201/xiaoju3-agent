# -*- coding: utf-8 -*-
"""系统领域 handler（#227 批 0：location/creator/child/help，2026-10-13）。

v2 领域拆分版（design_227b_boundary_v2.md）。轻分派+本体聚合本文件；
**批 C.1（2026-10-15）：creator 本体（署名卡+creator.json 读取）已从
main 迁入**——cb 注入退役改内聚直调（G2 彻底改指拍板）。

【数据域审计地图（#319 灵魂物流判据落地，design_227c_batch_c §一）】
- creator：身份署名（creator.json）——**灵魂核 core，不可镜像**（跟人走）；
- location：user_location.json + .env——灵魂核 core，不可镜像（C.2 迁入）；
- child：儿童锁裁决——运行时安全态，非灵魂核（本体暂留 main，全局状态
  网强耦合单列待办，2026-10-15 评估）；
- 镜像只发生在数据层文件，代码层不存在第二份数据（依赖方向纪律）。

分派顺序纪律：main 中 location → creator → child → help 的先后即既有
管线序，迁出后调用点保持同序（行为等价由黄金样本守护）。

接口纪律：每 handler ≤3 参数；本模块零 import main。
"""
import json
import os

import paths  # 双根路径锚（creator.json 等用户数据锚定数据根）


def handle_location(command_text, location_cb):
    """位置指令转发（/set_location /clear_location，本体在 main）。"""
    return location_cb(command_text)


def get_creator_name(base_dir=None):
    """创作者署名（xiaoju3_data/creator.json 存在即激活；缺省返回 ""）。

    只表现署名，不授予任何权限（权限由 LV4 决定）。公开版（无隔离区
    文件）返回空串，所有署名位置自动隐藏。base_dir 仅供测试注入临时
    目录（缺省 = 数据根下 xiaoju3_data）。
    """
    base = base_dir or os.path.join(paths.DATA_ROOT,
                                    "xiaoju3_data")
    path = os.path.join(base, "creator.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str((data or {}).get("name") or "").strip()
    except Exception:
        return ""


def creator_command():
    """/creator 命令本体：返回创作者署名卡（QQ 与网页控制台共用）。

    creator.json 存在 → 署名卡；缺失 → 开源项目链接。不要求任何权限
    （LV1 也可查）。
    """
    name = get_creator_name()
    if name:
        return f"🦊 小橘3号 · 由 {name} 创造与维护"
    return "🦊 小橘3号 · 开源项目（https://github.com/Xun201/xiaoju3-agent）"


def handle_creator(command_text):
    """创作者署名分派（/creator 精确匹配——去 CQ 码后 raw_message 形态）。"""
    if command_text == "/creator":
        return creator_command()
    return None


def handle_child(command_text, user_key, child_cb):
    """儿童锁裁决转发（/approve /deny，无锁时 cb 自回拒绝文案）。"""
    return child_cb(command_text, user_key)


def handle_help(command_text, level_str_cb):
    """指令菜单（裸 help/大小写不敏感——#264 B2c 后补口径）。

    菜单本体 get_help_menu 在 plugins/help_menu（非 main 域，局部 import
    直接用——plugins 包引用合法）。"""
    if command_text.lower() in ["/help", "help", "菜单", "帮助", "指令"]:
        from plugins.help_menu import get_help_menu
        return get_help_menu(level_str_cb())
    return None
