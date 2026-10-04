# -*- coding: utf-8 -*-
"""插件：帮助菜单（分类展示所有可用指令，含等级门禁标注）。

2026-10-04 分类化改版（用户需求：/help 分类展示所有可用指令）：
- 组织方式从"按等级分段"改为"按功能分类"（对话直达/待办/权限/记忆/
  系统/主人级/智能家居），每条指令带【最低等级】标注；
- 可见性沿用 2026-10-02 口径（tests/test_main.py 既有锚锁定）：低等级
  不出现高等级段（Lv.2 菜单无"主人级"字样）；/sudo 为兼容保留指令、
  不进菜单（完整清单见 docs/COMMANDS_REFERENCE.md）；
- 未达等级以底部"升级指引"一行带过：/register → /coder_auth →
  /lv4_auth 三级通道自解释。

2026-10-04 纯文本化（修排版 + 二次确认口径）：
- 去 Markdown 符号（段标题 ** 与指令名反引号）——控制台与 QQ 均按
  纯文本渲染（前端 textContent 注入、QQ 文本消息不解析 Markdown），
  符号必然裸露；
- /todos clear 的 confirm 二次确认步骤不进菜单（直接发带 confirm 的
  消息会跳过安全提示一步清空）——菜单只展示 /todos clear；
- /lv4_auth confirm 保留：它是完成授权的必经步骤（无码无法授权），
  属必要文档而非绕过。

消费方：main.py（QQ 指令分发，"菜单/帮助/指令"同别名）、xiaoju3.py
（CLI 兜底同源）——get_help_menu(current_level) 签名不变；插件缺席时
两处各有内置兜底菜单。
"""

# 等级序数值（与 permission.LEVEL_ORDER 同口径；此处本地定义避免反向依赖）
_LEVEL_ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}


def _section(title, lines):
    """渲染一个分类段：【标题】 + 逐行条目（纯文本，无 Markdown 符号）。"""
    return "【" + title + "】\n" + "\n".join(lines)


def get_help_menu(current_level):
    """按当前权限等级，返回分类指令手册（Lv.4 可见全部段）。"""
    lv = _LEVEL_ORDER.get(current_level, 0)
    parts = ["📋 小橘3号 指令菜单", ""]

    # 💬 对话直达（所有等级：自然语言即能力，无需记指令）
    parts.append(_section("💬 对话直达 · 无需指令", [
        "· 直接聊天：双脑问答（本地优先 / 云端兜底）",
        "· 发 DeepSeek 分享链接：自动总结网页内容",
        "· “帮我搜…”：联网搜索（天气请带城市区县）",
        "· “记一下账 / 花了30元”：记账本",
        "· “把对话导出成电子书”：EPUB 电子书",
        "· “记住…”：长期记忆",
    ]))

    # 📋 待办（Lv.2 起；清空为 Lv.3 破坏性操作，confirm 二次确认不进菜单）
    if lv >= 2:
        parts.append(_section("📋 待办", [
            "· /todos：待办清单（P0-P5 优先级分组）",
            "· /todos done <编号>：标记完成",
            "· /todo_from_link <分享链接>：链接提取待办（后台约 1 分钟）",
            "· /todos clear：清空全部待办【Lv.3 · 需二次确认】",
        ]))

    # 🔑 权限（升级通道全级可查；Lv.4 段仅 Lv.4 可见）
    perm = [
        "· /register <密码>：注册 / 更新注册【Lv.2】",
        "· /coder_auth <6位动态密码>：激活 Lv.3（持久生效）",
        "· /name <昵称>：认领称呼【Lv.2】",
    ]
    if lv >= 3:
        perm.append("· /lv4_auth confirm <6位动态密码>：双因子授权主人级")
    if lv >= 4:
        perm.append("· /lv4_revoke：撤销主人级权限（立即生效）")
    parts.append(_section("🔑 权限", perm))

    # 🧠 记忆（灵魂备份 Lv.3 / 恢复 Lv.4）
    if lv >= 3:
        mem = ["· /soul_export [路径]：灵魂备份（打包导出）【Lv.3】"]
        if lv >= 4:
            mem.append("· /soul_import <zip路径>：灵魂恢复【Lv.4】")
        parts.append(_section("🧠 记忆", mem))

    # ⚙️ 系统（基础全员；熔断 Lv.2 / 日志 Lv.3）
    sys_lines = [
        "· /help（菜单 / 帮助 / 指令）：本手册",
        "· /creator：创作者署名",
        "· /clear（/reset）：清空会话记忆",
        "· /set_location <城市> [区县]：位置记忆（仅存本地）",
        "· /clear_location：清除位置记录",
    ]
    if lv >= 2:
        sys_lines.append("· /reset_fuse：重置工具熔断【Lv.2】")
    if lv >= 3:
        sys_lines.append("· /gen_log <分享链接>：提取开发日志【Lv.3】")
    parts.append(_section("⚙️ 系统", sys_lines))

    # 🛡️ 主人级（Lv.4 专属段：低等级不可见，口径同 2026-10-02）
    if lv >= 4:
        parts.append(_section("🛡️ 主人级 · Lv.4", [
            "· /lv4_auth：查看类 Root 警告（敏感操作清单 + 撤销途径）",
            "· /approve / /deny：裁决儿童操作请求（在线成人）",
            "· /send_image <图片路径>：QQ 发图",
            "· 能力：危险设备控制 / ADB 手机接管 / restart_service 重启自身",
        ]))

    # 🏠 智能家居（Lv.3 起可用；多品牌插件开发中）
    if lv >= 3:
        parts.append(_section("🏠 智能家居 · 能力", [
            "· “开灯 / 空调调到26度”：安全家居六类控制【Lv.3】",
            "· 危险设备（门锁/燃气）【Lv.4】",
            "· 多品牌智能家居插件开发中，敬请期待",
        ]))

    # 升级指引（未满级一行带过：下一级通道 + 解锁内容）
    if lv == 1:
        parts.append("🔸 升级指引：/register <密码> → Lv.2（待办 / 认称呼）")
    elif lv == 2:
        parts.append("🔸 升级指引：/coder_auth <动态密码> → Lv.3"
                     "（改代码 / 日志 / 灵魂备份 / 安全家居）")
    elif lv == 3:
        parts.append("🔸 升级指引：/lv4_auth confirm <动态密码> → 主人级"
                     "（危险设备 / ADB / 发图 / 灵魂导入）")

    parts.append("")
    parts.append(f"你当前的权限等级：{current_level}")
    return "\n".join(parts)
