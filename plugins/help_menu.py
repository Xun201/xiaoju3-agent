# -*- coding: utf-8 -*-
"""插件：帮助菜单（按权限等级渲染指令菜单）。

第二阶段 §7 用户权限新表口径：Lv.1 游客 / Lv.2 普通用户（/register 密码注册）/
Lv.3 代码编写者（/coder_auth TOTP 激活 + /sudo 操作窗口）/ Lv.4 主人级
（/lv4_auth 双因子 + /confirm 高危确认 + /lv4_revoke 撤销）。
继承语义：等级数值 ≥ 所需等级即展示对应菜单段（Lv.4 可见全部）。
"""

# 等级序数值（与 permission.LEVEL_ORDER 同口径；此处本地定义避免反向依赖）
_LEVEL_ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}


def get_help_menu(current_level):
    """根据当前权限等级，返回对应的可用指令菜单（含 Lv.4 主人级行）。"""
    level_value = _LEVEL_ORDER.get(current_level, 0)

    menu = "📋 **小橘3号 指令菜单**\n\n"

    # 1. 所有人可见的基础指令（Lv.1 起）
    menu += "**【基础指令 · 所有人】**\n"
    menu += "· `/help` 或 `菜单`：查看此菜单\n"
    menu += "· 直接聊天：双脑问答、发链接自动总结网页\n"
    menu += "· \"帮我搜...\"：联网搜索\n"
    menu += "· \"记一下账 / 花了30元 / 这个月花了多少\"：记账本\n"
    menu += "· \"把对话导出成电子书\"：EPUB 电子书\n"
    menu += "· \"记住...\"：存入长期记忆\n"

    # 2. Lv.2 普通用户
    if level_value >= 2:
        menu += "\n**【普通用户 · Lv.2+】**\n"
        menu += "· `/register <密码>`：注册 / 更新注册（Lv.2）\n"
        menu += "· `/reset_fuse`：重置防死循环熔断\n"
        menu += "· 读文件 / 列目录 / 控制普通家居（灯、空调、窗帘等）\n"
    else:
        menu += "\n**【升级指引】**\n"
        menu += "· `/register <密码>`：注册升级 Lv.2（普通用户）\n"

    # 3. Lv.3 代码编写者
    if level_value >= 3:
        menu += "\n**【代码编写者 · Lv.3+】**\n"
        menu += "· `/sudo <6位动态密码>`：开启 120 秒写操作窗口（兼容可选）\n"
        menu += "· `/gen_log <DeepSeek分享链接>`：后台提取开发日志\n"
        menu += "· `/send_image <图片路径>`：发送工作区内图片\n"
        menu += "· 写文件 / 写代码（Lv.3 直接可用，无需 /sudo）\n"
    elif level_value >= 2:
        menu += "\n**【升级指引】**\n"
        menu += "· `/coder_auth <6位动态密码>`：TOTP 激活 Lv.3（代码编写者，持久生效）\n"

    # 4. Lv.4 主人级
    if level_value >= 4:
        menu += "\n**【主人级 · Lv.4】**\n"
        menu += "· `/lv4_auth`：查看类 Root 警告（敏感操作清单 + 后果 + 撤销途径）\n"
        menu += "· `/lv4_auth confirm <6位动态密码>`：双因子授权主人级\n"
        menu += "· `/confirm <6位令牌>`：二次确认执行高危设备操作\n"
        menu += "· `/lv4_revoke`：撤销主人级权限（立即生效）\n"
        menu += "· 控制门锁/燃气等高危设备（动态密码+生物认证+二次确认）\n"

    menu += "\n---\n"
    menu += f"你当前的权限等级：**{current_level}**\n"
    menu += "如需升级权限，请使用上面对应的指令。"

    return menu
