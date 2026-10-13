# -*- coding: utf-8 -*-
"""系统领域 handler（#227 批 0：location/creator/child/help，2026-10-13）。

v2 领域拆分版（design_227b_boundary_v2.md）。四块全为轻分派（转发或
单词匹配+转发），聚合本文件分函数迁出；本体 handle_location_command /
handle_creator_command / handle_child_command / get_help_menu 留 main
与 plugins/help_menu（本体搬家=后续批）。

分派顺序纪律：main 中 location → creator → child → help 的先后即既有
管线序，迁出后调用点保持同序（行为等价由黄金样本守护）。

接口纪律：每 handler ≤3 参数+回调注入；本模块零 import main。
"""


def handle_location(command_text, location_cb):
    """位置指令转发（/set_location /clear_location，本体在 main）。"""
    return location_cb(command_text)


def handle_creator(command_text, creator_cb):
    """创作者署名（/creator 精确匹配——去 CQ 码后 raw_message 形态）。"""
    if command_text == "/creator":
        return creator_cb()
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
