# -*- coding: utf-8 -*-
"""插件：帮助菜单（按权限等级渲染指令菜单）。

2026-10-02 权限重构定稿口径：Lv.1 游客 / Lv.2 普通用户（/register 密码
注册：写文件/列目录）/ Lv.3 代码编写者（/coder_auth TOTP 激活：改代码/
管理插件/安全家居六类 domain）/ Lv.4 主人级（/lv4_auth 授权级 TOTP：
危险设备/ADB 全套/发图/restart_service/装卸组件/核心记忆，授权后操作
不再逐次验证；儿童锁开启时危险家电需在线成人确认）。
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

    # 2. Lv.2 普通用户（2026-10-02 定稿：写文件 / 列目录）
    if level_value >= 2:
        menu += "\n**【普通用户 · Lv.2】**\n"
        menu += "· `/register <密码>`：注册 / 更新注册（Lv.2）\n"
        menu += "· `/reset_fuse`：重置防死循环熔断\n"
        menu += "· 写文件 / 列目录\n"
    else:
        menu += "\n**【升级指引】**\n"
        menu += "· `/register <密码>`：注册升级 Lv.2（普通用户）\n"

    # 3. Lv.3 代码编写者（定稿：改代码 + 管理插件 + 安全家居六类）
    if level_value >= 3:
        menu += "\n**【代码编写者 · Lv.3】**\n"
        menu += "· `/gen_log <DeepSeek分享链接>`：后台提取开发日志\n"
        menu += "· 改代码 / 写文件 / 管理插件\n"
        menu += "· 控制安全家居（灯/开关/传感器/空调/媒体播放器/输入布尔器）\n"
    elif level_value >= 2:
        menu += "\n**【升级指引】**\n"
        menu += "· `/coder_auth <6位动态密码>`：TOTP 激活 Lv.3（代码编写者，持久生效）\n"

    # 4. Lv.4 主人级（定稿：危险设备 + ADB 全套 + 发图 + restart_service）
    if level_value >= 4:
        menu += "\n**【主人级 · Lv.4】**\n"
        menu += "· `/lv4_auth`：查看类 Root 警告（敏感操作清单 + 后果 + 撤销途径）\n"
        menu += "· `/lv4_auth confirm <6位动态密码>`：授权主人级（授权后操作不再逐次验证）\n"
        menu += "· `/lv4_revoke`：撤销主人级权限（立即生效）\n"
        menu += "· 控制危险设备（门锁/阀门/DANGER_ENTITIES 自定义）\n"
        menu += "· ADB 手机接管全套\n"
        menu += "· `/send_image <图片路径>`：发图（LV4）\n"
        menu += "· `restart_service`：重启小橘自身进程（LV4 专属）\n"
        menu += "· 装卸系统组件 / 读取核心记忆\n"

    menu += "\n---\n"
    menu += f"你当前的权限等级：**{current_level}**\n"
    menu += "如需升级权限，请使用上面对应的指令。"

    return menu
